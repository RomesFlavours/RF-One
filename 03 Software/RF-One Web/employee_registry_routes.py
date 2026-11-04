"""Employee register on the existing RF-One shell and administrator authorization."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select
from rfone_data_store import models as m
from rfone_data_store import employee_registry as svc
from rfone_data_store import people_registry

def parse_local(raw,tz):
    try:
        naive=datetime.fromisoformat(raw)
        if naive.tzinfo is not None:raise ValueError()
        zone=ZoneInfo(tz or 'UTC')
        first=naive.replace(tzinfo=zone,fold=0);second=naive.replace(tzinfo=zone,fold=1)
        if first.utcoffset()!=second.utcoffset():
            raise svc.RegistryError('Orario ambiguo o inesistente per il cambio ora: scegli un altro orario.')
        if first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)!=naive:raise ValueError()
        return first
    except (ValueError,KeyError):
        raise svc.RegistryError('Decorrenza non valida.') from None

def register_employee_registry_routes(app,*,SessionFactory,require_admin,require_csrf,current_account_id):
    @app.get('/employees')
    @require_admin
    def employee_registry_home():
        # One people directory; preserve the specialist employee editor below.
        with SessionFactory() as db:
            if people_registry.available(db):
                return redirect(url_for('people_home'))
        # Preserve the pre-migration shell until the additive upgrade is applied.
        query=request.args.get('q','').strip().casefold();only=request.args.get('view','all')
        with SessionFactory() as db:
            employees=list(db.scalars(select(m.Employee).order_by(m.Employee.display_name,m.Employee.id)))
            profiles={p.employee_id:p for p in db.scalars(select(m.EmployeeRegistryProfile))}
            roles={r.id:r.name for r in db.scalars(select(m.RestaurantRole))}
            current={}
            at=svc.now()
            for a in db.scalars(select(m.EmployeeAssignment).where(m.EmployeeAssignment.valid_from<=at,
                (m.EmployeeAssignment.valid_to.is_(None)) | (m.EmployeeAssignment.valid_to>at))):
                current.setdefault(a.employee_id,[]).append(roles[a.restaurant_role_id])
            rows=[]
            for e in employees:
                p=profiles.get(e.id);source=p.source_roles_signature if p else None
                mismatch=bool(p and ((p.source_name or '')!=(e.display_name or '') or
                    (p.source_custom_id or '')!=(e.custom_id or '') or
                    (source is not None and set(filter(None,source.split(' | ')))!=set(current.get(e.id,[])))))
                pending=p is None or p.needs_review
                if query and query not in ' '.join(filter(None,[e.display_name,e.custom_id,p.source_name if p else ''])).casefold():continue
                if only=='review' and not pending:continue
                if only=='differences' and not mismatch:continue
                rows.append(dict(employee=e,profile=p,roles=current.get(e.id,[]),source_roles=source,mismatch=mismatch,pending=pending))
            return render_template('employee_registry.html',rows=rows,query=request.args.get('q',''),view=only,
                total=len(employees),pending_count=sum(p is None or p.needs_review for p in [profiles.get(e.id) for e in employees]),
                initialized=len(profiles))

    @app.post('/employees/initialize')
    @require_admin
    def employee_registry_initialize():
        require_csrf()
        with SessionFactory() as db:
            count=svc.initialize(db);db.commit()
        flash(f'Anagrafica inizializzata: {count} nuove schede da controllare.','info')
        return redirect(url_for('employee_registry_home'))

    @app.route('/employees/<int:employee_id>',methods=['GET','POST'])
    @require_admin
    def employee_registry_detail(employee_id):
        if request.method=='POST':
            require_csrf()
            with SessionFactory() as db:
                e=db.get(m.Employee,employee_id)
                if e is None:abort(404)
                location=db.get(m.Location,e.location_id)
                try:
                    role_id=int(request.form['role_id']) if request.form.get('role_id') else None
                    svc.save(db,employee_id=employee_id,account_id=current_account_id(),version=int(request.form['version']),
                        name=request.form.get('name'),code=request.form.get('code'),status=request.form.get('status'),
                        role_id=role_id,area_id=int(request.form['area_id']) if role_id else None,
                        restaurant_id=int(request.form['restaurant_id']) if role_id else None,
                        effective_at=parse_local(request.form.get('effective_at',''),location.timezone) if role_id else None)
                    db.commit()
                except (svc.RegistryError,ValueError,KeyError) as exc:
                    db.rollback()
                    flash(str(exc) if isinstance(exc,svc.RegistryError) else 'Controlla i campi inseriti.','error')
                    return redirect(url_for('employee_registry_detail',employee_id=employee_id))
            flash('Scheda verificata e salvata in RF1.','info')
            return redirect(url_for('employee_registry_detail',employee_id=employee_id))
        with SessionFactory() as db:
            e=db.get(m.Employee,employee_id)
            if e is None:abort(404)
            profile=db.get(m.EmployeeRegistryProfile,employee_id)
            if profile is None:
                flash('Inizializza l’anagrafica prima di modificare le schede.','info')
                return redirect(url_for('employee_registry_home'))
            location=db.get(m.Location,e.location_id)
            restaurant_ids=list(db.scalars(select(m.RestaurantLocation.restaurant_id).where(m.RestaurantLocation.location_id==e.location_id)))
            restaurants=list(db.scalars(select(m.Restaurant).where(m.Restaurant.id.in_(restaurant_ids))))
            roles=list(db.scalars(select(m.RestaurantRole).where(m.RestaurantRole.restaurant_id.in_(restaurant_ids)).order_by(m.RestaurantRole.name)))
            areas=list(db.scalars(select(m.OperationalArea).where(m.OperationalArea.restaurant_id.in_(restaurant_ids)).order_by(m.OperationalArea.name)))
            history=svc.assignments(db,employee_id)
            changes=list(db.scalars(select(m.EmployeeRegistryChange).where(m.EmployeeRegistryChange.employee_id==employee_id).order_by(m.EmployeeRegistryChange.changed_at.desc(),m.EmployeeRegistryChange.id.desc()).limit(100)))
            accounts={a.id:a.display_name for a in db.scalars(select(m.RFOneAccount).where(m.RFOneAccount.id.in_([c.account_id for c in changes if c.account_id])))}
            return render_template('employee_registry_detail.html',employee=e,profile=profile,location=location,
                restaurants=restaurants,roles=roles,areas=areas,history=history,changes=changes,accounts=accounts,
                change_effective={c.id:datetime.fromisoformat(c.details['assignment']['effective_at']) for c in changes if 'assignment' in c.details},
                role_names={r.id:r.name for r in roles},area_names={a.id:a.name for a in areas},
                effective_default=svc.now().astimezone(ZoneInfo(location.timezone or 'UTC')).strftime('%Y-%m-%dT%H:%M'),
                tz=location.timezone)
