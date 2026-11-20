"""Kitchen menu composition: location areas and references to shared dish recipes."""
from uuid import UUID
import sqlalchemy as sa
from .models import Base, Location
from .kitchen import recipes
from .kitchen_configuration import items, clean_name, ConfigurationError, normalize

menus=sa.Table('kitchen_menus',Base.metadata,
    sa.Column('id',sa.Integer,primary_key=True),
    sa.Column('draft_key',sa.String(32),nullable=False,unique=True),
    sa.Column('name',sa.String(255),nullable=False),
    sa.Column('location_id',sa.Integer,sa.ForeignKey('locations.id'),nullable=False),
    sa.Column('archived',sa.Boolean,nullable=False,server_default=sa.false()),
    sa.Column('active',sa.Boolean,nullable=False,server_default=sa.false()),
    sa.Column('revision',sa.Integer,nullable=False,server_default='1'),
    sa.CheckConstraint('NOT (active AND archived)',name='ck_kitchen_menu_active_not_archived'),
    sa.Index('uq_kitchen_active_menu_location','location_id',unique=True,
        postgresql_where=sa.text('active'),sqlite_where=sa.text('active = 1')))
entries=sa.Table('kitchen_menu_entries',Base.metadata,
    sa.Column('id',sa.Integer,primary_key=True),
    sa.Column('menu_id',sa.Integer,sa.ForeignKey('kitchen_menus.id'),nullable=False),
    sa.Column('area_id',sa.Integer,sa.ForeignKey('kitchen_configuration_items.id'),nullable=False),
    sa.Column('recipe_id',sa.Integer,sa.ForeignKey('kitchen_recipes.id')),
    sa.Column('label',sa.String(255),nullable=False),
    sa.Column('position',sa.Integer,nullable=False),
    sa.CheckConstraint('position > 0',name='ck_kitchen_menu_position'),
    sa.UniqueConstraint('menu_id','position',name='uq_kitchen_menu_position'))

class MenuError(ValueError):pass
class StaleMenu(MenuError):pass

def identifier(value):
    if value in (None,''):return None
    try:
        result=int(value)
        if result<1 or str(result)!=str(value):raise ValueError()
        return result
    except (TypeError,ValueError):raise MenuError('Choose a valid record.')

def options(db):
    category=items.alias('recipe_category')
    return dict(locations=[dict(r) for r in db.execute(sa.select(Location.id,Location.name).order_by(Location.name)).mappings()],
        areas=[dict(r) for r in db.execute(sa.select(items.c.id,items.c.name,items.c.location_id,items.c.archived).where(items.c.section=='MENU_AREA').order_by(items.c.name)).mappings()],
        recipes=[dict(r) for r in db.execute(sa.select(recipes.c.id,recipes.c.name,category.c.name.label('category')).outerjoin(category,category.c.id==recipes.c.category_id).where(recipes.c.kind=='dish').order_by(recipes.c.name)).mappings()])

def read(db,mid):
    row=db.execute(sa.select(menus,Location.name.label('location_name')).join(Location,Location.id==menus.c.location_id).where(menus.c.id==mid)).mappings().first()
    if row is None:raise MenuError('This menu no longer exists.')
    result=dict(row)
    result['entries']=[dict(r) for r in db.execute(sa.select(entries,items.c.name.label('area_name'),recipes.c.name.label('recipe_name'))
        .join(items,items.c.id==entries.c.area_id).outerjoin(recipes,recipes.c.id==entries.c.recipe_id)
        .where(entries.c.menu_id==mid).order_by(entries.c.position)).mappings()]
    return result

def listing(db):
    return [read(db,mid) for mid in db.scalars(sa.select(menus.c.id).order_by(menus.c.archived,sa.func.lower(menus.c.name),menus.c.id))]

def save(db,data):
    if db.get_bind().dialect.name=='postgresql':
        db.execute(sa.text('SELECT pg_advisory_xact_lock(1919247476, 0)'))
    mid=identifier(data.get('id'));old=None
    if mid:
        old=db.execute(sa.select(menus).where(menus.c.id==mid).with_for_update()).mappings().first()
        if not old:raise MenuError('This menu no longer exists.')
        if identifier(data.get('revision'))!=old['revision']:raise StaleMenu('This menu changed. Close and reopen it before saving.')
        if old['archived']:raise MenuError('Archived menus are read-only.')
    if not isinstance(data.get('name'),str):raise MenuError('Enter a menu name.')
    try:name=clean_name(data.get('name'))
    except ConfigurationError as exc:raise MenuError(str(exc))
    locations=db.scalars(sa.select(Location.id)).all();location=identifier(data.get('location_id'))
    if len(locations)==1 and location is None:location=locations[0]
    if location not in locations:raise MenuError('Choose a location for this menu.')
    incoming=data.get('entries')
    if not isinstance(incoming,list) or len(incoming)>500:raise MenuError('A menu may contain at most 500 entries.')
    prior={r['id']:dict(r) for r in db.execute(sa.select(entries).where(entries.c.menu_id==mid)).mappings()} if mid else {}
    planned=[];seen=set()
    for line in incoming:
        if not isinstance(line,dict):raise MenuError('Invalid menu entry.')
        eid=identifier(line.get('id'));area=identifier(line.get('area_id'));rid=identifier(line.get('recipe_id'))
        if eid and (eid not in prior or eid in seen):raise MenuError('An entry is duplicated or belongs to another menu.')
        if eid:seen.add(eid)
        a=db.execute(sa.select(items).where(items.c.id==area,items.c.section=='MENU_AREA')).mappings().first()
        if not a or (a['archived'] and (not eid or prior[eid]['area_id']!=area)):raise MenuError('Choose an active Menu Area.')
        category=items.alias('recipe_category')
        recipe=db.execute(sa.select(recipes.c.name,category.c.name.label('category')).outerjoin(category,category.c.id==recipes.c.category_id).where(recipes.c.id==rid,recipes.c.kind=='dish')).first() if rid else None
        if rid and not recipe:raise MenuError('Choose an existing dish recipe, or leave the entry as a label.')
        if recipe and (not recipe.category or normalize(' '.join(recipe.category.split()))!=normalize(' '.join(a['name'].split()))):
            raise MenuError('The recipe Category must match the selected Menu Area.')
        if line.get('label') is not None and not isinstance(line.get('label'),str):raise MenuError('Enter a text label for every menu entry.')
        try:label=clean_name(line.get('label') or (recipe[0] if recipe else ''))
        except ConfigurationError:raise MenuError('Enter a label for every menu entry.')
        planned.append(dict(id=eid,area_id=area,recipe_id=rid,label=label))
    if not mid:
        try:key=UUID(data.get('draft_key','')).hex
        except (ValueError,TypeError,AttributeError):raise MenuError('Reopen the new menu form.')
        existing=db.scalar(sa.select(menus.c.id).where(menus.c.draft_key==key))
        if existing:
            saved=read(db,existing)
            if saved['name']!=name or saved['location_id']!=location or [(e['area_id'],e['recipe_id'],e['label']) for e in saved['entries']]!=[(e['area_id'],e['recipe_id'],e['label']) for e in planned]:
                raise StaleMenu('This draft was already saved. Reopen the menu.')
            return saved
        mid=db.execute(menus.insert().values(name=name,location_id=location,draft_key=key).returning(menus.c.id)).scalar_one()
    else:
        db.execute(menus.update().where(menus.c.id==mid).values(name=name,location_id=location,
            active=old['active'] and old['location_id']==location,revision=old['revision']+1))
    if prior:
        offset=max(r['position'] for r in prior.values())+len(planned)+1
        db.execute(entries.update().where(entries.c.menu_id==mid).values(position=entries.c.position+offset))
    for pos,line in enumerate(planned,1):
        eid=line.pop('id');values=dict(menu_id=mid,position=pos,**line)
        if eid:db.execute(entries.update().where(entries.c.id==eid).values(**values))
        else:seen.add(db.execute(entries.insert().values(**values).returning(entries.c.id)).scalar_one())
    if prior:db.execute(entries.delete().where(entries.c.menu_id==mid,entries.c.id.not_in(seen)))
    return read(db,mid)

def archive(db,mid,revision):
    if db.get_bind().dialect.name=='postgresql':
        db.execute(sa.text('SELECT pg_advisory_xact_lock(1919247476, 0)'))
    row=db.execute(sa.select(menus).where(menus.c.id==mid).with_for_update()).mappings().first()
    if not row:raise MenuError('This menu no longer exists.')
    if identifier(revision)!=row['revision']:raise StaleMenu('This menu changed. Close and reopen it before archiving.')
    if not row['archived']:db.execute(menus.update().where(menus.c.id==mid).values(archived=True,active=False,revision=row['revision']+1))
    return read(db,mid)

def activate(db,mid,revision):
    if db.get_bind().dialect.name=='postgresql':
        db.execute(sa.text('SELECT pg_advisory_xact_lock(1919247476, 0)'))
    row=db.execute(sa.select(menus).where(menus.c.id==mid).with_for_update()).mappings().first()
    if not row:raise MenuError('This menu no longer exists.')
    if identifier(revision)!=row['revision']:raise StaleMenu('This menu changed. Close and reopen it before activating.')
    if row['archived']:raise MenuError('Archived menus cannot be activated.')
    if not row['active']:
        db.execute(menus.update().where(menus.c.location_id==row['location_id'],menus.c.id!=mid,menus.c.active.is_(True))
            .values(active=False,revision=menus.c.revision+1))
        db.execute(menus.update().where(menus.c.id==mid).values(active=True,revision=row['revision']+1))
    return read(db,mid)

def active_for_location(db,location_id):
    mid=db.scalar(sa.select(menus.c.id).where(menus.c.location_id==location_id,menus.c.active.is_(True),menus.c.archived.is_(False)))
    return read(db,mid) if mid is not None else None
