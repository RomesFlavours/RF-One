"""Kitchen reference lists and the existing Purchasing Supplier registry."""
import unicodedata

import sqlalchemy as sa
from .models import Base, Restaurant, Supplier, SupplierAlias, Location
from .purchasing.repository import get_or_create_supplier, rename_supplier_canonical

SECTIONS = (('MENU_TYPE', 'Menu Type'), ('MENU_AREA', 'Menu Area'),
            ('CATEGORY', 'Category'), ('COMPONENT', 'Components'), ('SUPPLIER', 'Supplier'),
            ('RECIPE_TYPE', 'Recipe Type'))
REFERENCE_SECTIONS = {key for key, _ in SECTIONS if key != 'SUPPLIER'}

items = sa.Table('kitchen_configuration_items', Base.metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('section', sa.String(24), nullable=False),
    sa.Column('name', sa.String(255), nullable=False),
    sa.Column('normalized_name', sa.String(255), nullable=False),
    sa.Column('location_id', sa.Integer, sa.ForeignKey('locations.id')),
    sa.Column('archived', sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.Index('uq_kitchen_configuration_shared_name','section','normalized_name',unique=True,
        postgresql_where=sa.text("section <> 'MENU_AREA'"),sqlite_where=sa.text("section <> 'MENU_AREA'")),
    sa.Index('uq_kitchen_menu_area_location_name','normalized_name',unique=True,
        postgresql_where=sa.text("section = 'MENU_AREA'"),sqlite_where=sa.text("section = 'MENU_AREA'")),
    sa.CheckConstraint("section IN ('MENU_TYPE','MENU_AREA','CATEGORY','COMPONENT','RECIPE_TYPE')", name='ck_kitchen_configuration_section'),
    sa.CheckConstraint("length(trim(name)) > 0", name='ck_kitchen_configuration_name'),
)


class ConfigurationError(ValueError):
    pass


def normalize(name):
    return unicodedata.normalize('NFKC', name).casefold()


def clean_name(name):
    name = ' '.join((name or '').split())
    if not name or len(name) > 255 or len(normalize(name)) > 255:
        raise ConfigurationError('Enter a name between 1 and 255 characters.')
    return name


def lists(db):
    result = {section: [] for section, _ in SECTIONS}
    for row in db.execute(sa.select(items,Location.name.label('location_name')).outerjoin(Location,Location.id==items.c.location_id).order_by(items.c.archived, items.c.normalized_name)).mappings():
        result[row['section']].append(dict(row))
    suppliers = db.execute(sa.select(Supplier.id, Supplier.name, Supplier.status,
        Supplier.restaurant_id, Restaurant.name.label('restaurant_name'))
        .join(Restaurant, Restaurant.id == Supplier.restaurant_id).order_by(sa.func.lower(Supplier.name))).mappings()
    for row in suppliers:
        result['SUPPLIER'].append(dict(row, archived=row['status'] in ('INACTIVE','ARCHIVED')))
    return result


def save(db, section, *, name, item_id=None, restaurant_id=None, location_id=None):
    if section=='MENU_AREA' and db.get_bind().dialect.name=='postgresql':
        db.execute(sa.text('SELECT pg_advisory_xact_lock(1919247476, 0)'))
    name = clean_name(name)
    if section == 'SUPPLIER':
        current = db.get(Supplier, item_id) if item_id else None
        if item_id and current is None:
            raise ConfigurationError('This supplier no longer exists.')
        restaurant_id = current.restaurant_id if current else restaurant_id
        if not restaurant_id or db.get(Restaurant, restaurant_id) is None:
            raise ConfigurationError('Choose a restaurant for this supplier.')
        # Kitchen reuses canonical suppliers, their restaurant scope and rename provenance.
        if db.get_bind().dialect.name == 'postgresql':
            db.execute(sa.text('SELECT pg_advisory_xact_lock(1919247476, :restaurant)'), {'restaurant':restaurant_id})
        candidates = db.scalars(sa.select(Supplier).where(Supplier.restaurant_id == restaurant_id)).all()
        aliases = db.execute(sa.select(SupplierAlias.supplier_id, SupplierAlias.alias_name)
            .join(Supplier).where(Supplier.restaurant_id == restaurant_id)).all()
        matches = [s.id for s in candidates if normalize(s.name) == normalize(name)]
        matches += [sid for sid, alias in aliases if normalize(alias) == normalize(name)]
        if any(sid != item_id for sid in matches):
            raise ConfigurationError('This supplier name already exists for this restaurant, including archived names or aliases.')
        if current:
            return rename_supplier_canonical(db, current.id, name, source='Kitchen Configuration').id
        return get_or_create_supplier(db, restaurant_id, name).id
    if section not in REFERENCE_SECTIONS:
        raise ConfigurationError('Unknown configuration section.')
    if item_id:
        current = db.execute(sa.select(items).where(items.c.id == item_id, items.c.section == section)).first()
        if current is None:
            raise ConfigurationError('This item no longer exists in this section.')
    duplicate = db.scalar(sa.select(items.c.id).where(items.c.section == section,
                         items.c.normalized_name == normalize(name), items.c.id != (item_id or -1)))
    if duplicate is not None:
        raise ConfigurationError('This name already exists in this section, including archived items.')
    values = dict(name=name, normalized_name=normalize(name), updated_at=sa.func.now())
    if section=='MENU_AREA':values['location_id']=None
    if item_id:
        db.execute(items.update().where(items.c.id == item_id,items.c.section == section).values(**values))
        return item_id
    return db.execute(items.insert().values(section=section,**values).returning(items.c.id)).scalar_one()


def archive(db, section, item_id):
    if section == 'SUPPLIER':
        supplier = db.get(Supplier, item_id)
        if supplier is None:
            raise ConfigurationError('This supplier no longer exists.')
        supplier.status = 'INACTIVE'
        db.flush()
        return
    if section not in REFERENCE_SECTIONS:
        raise ConfigurationError('Unknown configuration section.')
    changed = db.execute(items.update().where(items.c.id==item_id,items.c.section==section)
                         .values(archived=True,updated_at=sa.func.now()))
    if changed.rowcount != 1:
        raise ConfigurationError('This item no longer exists in this section.')
