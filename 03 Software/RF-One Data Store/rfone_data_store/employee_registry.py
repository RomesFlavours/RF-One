"""RF-One employee review and source ownership over existing canonical identities."""
from datetime import datetime, timezone
from sqlalchemy import select, func
from . import models as m

class RegistryError(ValueError):
    pass

def now():
    return datetime.now(timezone.utc)

def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def audit(db,employee_id,kind,details,account_id=None):
    db.add(m.EmployeeRegistryChange(employee_id=employee_id,kind=kind,details=details,
        account_id=account_id,changed_at=now()))

def ensure_profile(db,employee):
    profile=db.get(m.EmployeeRegistryProfile,employee.id)
    if profile is None:
        profile=m.EmployeeRegistryProfile(employee_id=employee.id,source_name=employee.display_name,
            source_custom_id=employee.custom_id,protect_name=False,protect_code=False,
            protect_status=False,protect_roles=False,needs_review=True,version=1,created_at=now())
        db.add(profile)
        db.flush()
        audit(db,employee.id,'DISCOVERED',{'origin':'CLOVER' if employee.source_employee_id else 'RFONE'})
    return profile

def observe_employee(db,employee,values):
    """Called by every Clover employee upsert. Sparse references cannot erase facts."""
    profile=ensure_profile(db,employee)
    result=dict(values);changed={}
    for field,source_field,protected in [('display_name','source_name','protect_name'),('custom_id','source_custom_id','protect_code')]:
        value=values.get(field)
        if value is not None and (not isinstance(value,str) or value.strip()):
            if getattr(profile,source_field)!=value:
                changed[field]={'before':getattr(profile,source_field),'after':value}
                setattr(profile,source_field,value)
        if getattr(profile,protected):result.pop(field,None)
    if profile.protect_status:result.pop('active',None)
    if changed:
        profile.needs_review=True;profile.version+=1
        audit(db,employee.id,'SOURCE_CHANGED',changed)
    return result

def latest_source_roles(db,employee_id):
    latest=db.scalar(select(func.max(m.EmployeeSourceRole.observed_at)).where(m.EmployeeSourceRole.employee_id==employee_id))
    if latest is None:return []
    return list(db.scalars(select(m.SourceRole.name).join(m.EmployeeSourceRole,
        m.EmployeeSourceRole.source_role_id==m.SourceRole.id).where(
        m.EmployeeSourceRole.employee_id==employee_id,m.EmployeeSourceRole.observed_at==latest).order_by(m.SourceRole.name)))

def observe_roles(db,employee_id,role_names=None):
    employee=db.get(m.Employee,employee_id)
    profile=ensure_profile(db,employee)
    signature=' | '.join(sorted(set(latest_source_roles(db,employee_id) if role_names is None else role_names)))
    if signature!=profile.source_roles_signature:
        before=profile.source_roles_signature;profile.source_roles_signature=signature
        if before is not None:
            profile.needs_review=True;profile.version+=1
            audit(db,employee_id,'SOURCE_ROLES_CHANGED',{'before':before,'after':signature})

def initialize(db):
    count=0
    for employee in db.scalars(select(m.Employee).order_by(m.Employee.id)):
        if db.get(m.EmployeeRegistryProfile,employee.id) is None:count+=1
        ensure_profile(db,employee)
        if db.get(m.EmployeeRegistryProfile,employee.id).source_roles_signature is None:
            observe_roles(db,employee.id)
    return count

def assignments(db,employee_id):
    return list(db.scalars(select(m.EmployeeAssignment).where(
        m.EmployeeAssignment.employee_id==employee_id).order_by(m.EmployeeAssignment.valid_from.desc())))

def save(db,*,employee_id,account_id,version,name,code,status,role_id=None,area_id=None,
         restaurant_id=None,effective_at=None):
    employee=db.scalar(select(m.Employee).where(m.Employee.id==employee_id).with_for_update())
    if employee is None:raise RegistryError('Dipendente non trovato.')
    profile=ensure_profile(db,employee)
    if profile.version!=version:raise RegistryError('La scheda è cambiata. Ricaricala prima di salvare.')
    name=(name or '').strip();code=(code or '').strip() or None
    if not name or len(name)>255:raise RegistryError('Inserisci un nome valido (massimo 255 caratteri).')
    if code and len(code)>64:raise RegistryError('Il codice dipendente può contenere al massimo 64 caratteri.')
    if status not in ('unknown','active','inactive'):raise RegistryError('Stato non valido.')
    active={'unknown':None,'active':True,'inactive':False}[status]
    changes={}
    for field,value in [('display_name',name),('custom_id',code),('active',active)]:
        old=getattr(employee,field)
        if old!=value:changes[field]={'before':old,'after':value}
        setattr(employee,field,value)
    # Saving the reviewed RF-One values explicitly establishes local ownership.
    profile.protect_name=True;profile.protect_code=True;profile.protect_status=True
    if role_id is not None:
        if effective_at is None or effective_at.tzinfo is None:raise RegistryError('Indica la decorrenza locale del ruolo.')
        at=aware(effective_at)
        role=db.get(m.RestaurantRole,role_id);area=db.get(m.OperationalArea,area_id)
        linked=db.scalar(select(m.RestaurantLocation).where(m.RestaurantLocation.restaurant_id==restaurant_id,
            m.RestaurantLocation.location_id==employee.location_id))
        if not linked or not role or not area or role.restaurant_id!=restaurant_id or area.restaurant_id!=restaurant_id:
            raise RegistryError('Ruolo e area devono appartenere al ristorante del dipendente.')
        if role.active is False or area.active is False:raise RegistryError('Ruolo o area non attivi.')
        history=[a for a in assignments(db,employee.id) if a.restaurant_id==restaurant_id]
        current=[a for a in history if a.valid_to is None]
        same=len(current)==1 and current[0].restaurant_role_id==role_id and current[0].operational_area_id==area_id
        if not same:
            if any(aware(a.valid_from)>=at for a in history):
                raise RegistryError('La decorrenza deve essere successiva all’inizio degli incarichi già registrati.')
            if any(a.valid_to is not None and aware(a.valid_to)>at for a in history):
                raise RegistryError('La decorrenza si sovrappone a un incarico storico.')
            for a in current:a.valid_to=at
            db.flush()  # Close before opening: one open role per restaurant.
            db.add(m.EmployeeAssignment(employee_id=employee.id,restaurant_id=restaurant_id,
                operational_area_id=area_id,restaurant_role_id=role_id,location_id=employee.location_id,
                valid_from=at,assignment_source='MANUAL',source_note='RF-One employee registry review'))
            changes['assignment']={'previous_roles':[db.get(m.RestaurantRole,a.restaurant_role_id).name for a in current],
                'role':role.name,'area':area.name,'effective_at':at.isoformat()}
        profile.protect_roles=True
    profile.needs_review=False;profile.reviewed_at=now();profile.reviewed_by=account_id;profile.version+=1
    audit(db,employee.id,'REVIEWED',changes,account_id)
    db.flush()
    return employee
