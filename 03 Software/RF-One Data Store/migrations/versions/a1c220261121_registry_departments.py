"""Registry Role/Department table (REGISTRY_CLOVER_DEPARTMENTS_001, Product Owner 2026-11-21).

Additive: four new tables and the Product Owner's initial table.
- Departments FOH (Front of House) and BOH (Back of House), inside the existing "Restaurant
  Operations" Area (code ROOT): no new Area.
- RF-One roles Cook, Dishwasher and Server Help (Server Help is its own FOH role, never merged with
  Server), added to the shared Registry role catalog with the Restaurant Operations Area, as Registry
  itself creates roles. Existing roles are reused by code, never renamed.
- Role departments: Server, Host, Server Help, Team Leader, Busser-Runner -> FOH; Cook, Dishwasher -> BOH;
  Manager -> to be defined.
- Original roles at the Restaurant of the ROOT Area (Winter Park): Note sheet codes 2-Serv -> Server,
  3-Host -> Host, 4-Cook -> Cook, 6-Dish -> Dishwasher; Clover roles Server, Host, Team Leader, Manager ->
  same RF-One role; Clover BOH -> department BOH (RF-One role to be defined); Admin, Employee -> to be defined.
No employee, assignment, Clover role or Tips mapping is created or changed.
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = 'a1c220261121'
down_revision = 'e9a120261117'
branch_labels = None
depends_on = None

NEW_ROLES = (('COOK', 'Cook'), ('DISHWASHER', 'Dishwasher'), ('SERVER_HELP', 'Server Help'))
ROLE_DEPARTMENT = {'SERVER': 'FOH', 'HOST': 'FOH', 'SERVER_HELP': 'FOH', 'TEAM_LEADER': 'FOH',
                   'BUSSER_RUNNER': 'FOH', 'COOK': 'BOH', 'DISHWASHER': 'BOH', 'MANAGER': None}
EXCEL_SOURCE = 'EXCEL_WP_NOTE'
EXCEL_CODES = (('2-Serv', 'SERVER'), ('3-Host', 'HOST'), ('4-Cook', 'COOK'), ('6-Dish', 'DISHWASHER'))
# Clover role name -> (RF-One role code, department when the RF-One role is not certain)
CLOVER = {'Server': ('SERVER', None), 'Host': ('HOST', None), 'Team Leader': ('TEAM_LEADER', None),
          'Manager': ('MANAGER', None), 'BOH': (None, 'BOH'), 'Admin': (None, None), 'Employee': (None, None)}


def _temporal(name, *columns):
    return op.create_table(
        name, sa.Column('id', sa.Integer(), primary_key=True), *columns,
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('origin', sa.String(16), nullable=False),
        sa.Column('changed_by_account_id', sa.Integer(), sa.ForeignKey('rfone_accounts.id'), nullable=True))


def upgrade():
    op.create_table(
        'registry_departments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('operational_area_id', sa.Integer(), sa.ForeignKey('operational_areas.id'), nullable=False),
        sa.Column('code', sa.String(32), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('updated_by_account_id', sa.Integer(), sa.ForeignKey('rfone_accounts.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('code', name='uq_registry_departments_code'),
        sa.UniqueConstraint('name', name='uq_registry_departments_name'))
    op.create_index('ix_registry_departments_operational_area_id', 'registry_departments', ['operational_area_id'])
    _temporal('registry_role_departments',
              sa.Column('restaurant_role_id', sa.Integer(), sa.ForeignKey('restaurant_roles.id'), nullable=False),
              sa.Column('department_id', sa.Integer(), sa.ForeignKey('registry_departments.id'), nullable=True))
    op.create_index('ix_registry_role_departments_restaurant_role_id', 'registry_role_departments', ['restaurant_role_id'])
    op.create_index('ux_registry_role_departments_current', 'registry_role_departments', ['restaurant_role_id'],
                    unique=True, sqlite_where=sa.text('valid_to IS NULL'), postgresql_where=sa.text('valid_to IS NULL'))
    _temporal('registry_role_mappings',
              sa.Column('restaurant_id', sa.Integer(), sa.ForeignKey('restaurants.id'), nullable=False),
              sa.Column('source', sa.String(32), nullable=False),
              sa.Column('original_key', sa.String(128), nullable=False),
              sa.Column('original_label', sa.String(255), nullable=False),
              sa.Column('source_role_id', sa.Integer(), sa.ForeignKey('source_roles.id'), nullable=True),
              sa.Column('restaurant_role_id', sa.Integer(), sa.ForeignKey('restaurant_roles.id'), nullable=True),
              sa.Column('department_id', sa.Integer(), sa.ForeignKey('registry_departments.id'), nullable=True))
    op.create_index('ix_registry_role_mappings_restaurant_id', 'registry_role_mappings', ['restaurant_id'])
    op.create_index('ux_registry_role_mappings_current', 'registry_role_mappings',
                    ['restaurant_id', 'source', 'original_key'], unique=True,
                    sqlite_where=sa.text('valid_to IS NULL'), postgresql_where=sa.text('valid_to IS NULL'))
    op.create_table(
        'registry_person_source_roles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), sa.ForeignKey('restaurants.id'), nullable=False),
        sa.Column('source', sa.String(32), nullable=False),
        sa.Column('original_key', sa.String(128), nullable=False),
        sa.Column('declared_department', sa.String(32), nullable=True),
        sa.Column('source_reference', sa.String(255), nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('employee_id', 'restaurant_id', 'source', name='uq_registry_person_source_role'))
    op.create_index('ix_registry_person_source_roles_employee_id', 'registry_person_source_roles', ['employee_id'])

    bind = op.get_bind()
    root = bind.execute(sa.text(
        "SELECT id, restaurant_id FROM operational_areas WHERE code = 'ROOT' AND restaurant_id IS NOT NULL "
        "ORDER BY id")).first()
    if root is None:        # a fresh database: everything is created from Registry
        return
    area_id, restaurant_id = root
    now = datetime.now(timezone.utc)
    t = lambda name, *cols: sa.table(name, *(sa.column(c) for c in cols))
    op.bulk_insert(t('registry_departments', 'operational_area_id', 'code', 'name', 'active', 'created_at', 'updated_at'), [
        dict(operational_area_id=area_id, code='FOH', name='Front of House', active=True, created_at=now, updated_at=now),
        dict(operational_area_id=area_id, code='BOH', name='Back of House', active=True, created_at=now, updated_at=now)])
    departments = dict(bind.execute(sa.text("SELECT code, id FROM registry_departments")).all())

    def role_ids():
        return {code: rid for code, rid in bind.execute(sa.text(
            "SELECT code, id FROM restaurant_roles WHERE code IS NOT NULL AND (restaurant_id = :r OR restaurant_id IS NULL) "
            "ORDER BY restaurant_id NULLS FIRST, id DESC"), {'r': restaurant_id}).all()}   # the Restaurant's own role wins
    existing = role_ids()
    names = {n.lower() for (n,) in bind.execute(sa.text("SELECT name FROM restaurant_roles")).all()}
    for code, name in NEW_ROLES:
        if code in existing or name.lower() in names:
            continue
        bind.execute(sa.text("INSERT INTO restaurant_roles (restaurant_id, name, code, active) VALUES (NULL, :n, :c, true)"),
                     {'n': name, 'c': code})
        rid = bind.execute(sa.text("SELECT id FROM restaurant_roles WHERE code = :c AND restaurant_id IS NULL"), {'c': code}).scalar()
        bind.execute(sa.text("INSERT INTO operational_area_roles (operational_area_id, restaurant_role_id) VALUES (:a, :r)"),
                     {'a': area_id, 'r': rid})
    roles = role_ids()
    op.bulk_insert(t('registry_role_departments', 'restaurant_role_id', 'department_id', 'valid_from', 'origin'), [
        dict(restaurant_role_id=roles[code], department_id=departments.get(dep), valid_from=now, origin='SEED')
        for code, dep in ROLE_DEPARTMENT.items() if code in roles])
    rows = [dict(restaurant_id=restaurant_id, source=EXCEL_SOURCE, original_key=key, original_label=key, source_role_id=None,
                 restaurant_role_id=roles.get(code), department_id=None, valid_from=now, origin='SEED')
            for key, code in EXCEL_CODES]
    seen = set()
    for source_role_id, clover_id, name in bind.execute(sa.text(
            "SELECT sr.id, sr.source_role_id, sr.name FROM source_roles sr "
            "JOIN source_systems ss ON ss.id = sr.source_system_id AND ss.code = 'CLOVER' "
            "JOIN restaurant_locations rl ON rl.location_id = sr.location_id AND rl.restaurant_id = :r "
            "ORDER BY sr.id"), {'r': restaurant_id}).all():
        if name in CLOVER and clover_id not in seen:
            seen.add(clover_id)
            code, dep = CLOVER[name]
            rows.append(dict(restaurant_id=restaurant_id, source='CLOVER', original_key=clover_id, original_label=name,
                             source_role_id=source_role_id, restaurant_role_id=roles.get(code) if code else None,
                             department_id=departments.get(dep) if dep else None, valid_from=now, origin='SEED'))
    op.bulk_insert(t('registry_role_mappings', 'restaurant_id', 'source', 'original_key', 'original_label', 'source_role_id',
                     'restaurant_role_id', 'department_id', 'valid_from', 'origin'), rows)


def downgrade():
    op.drop_index('ix_registry_person_source_roles_employee_id', table_name='registry_person_source_roles')
    op.drop_table('registry_person_source_roles')
    op.drop_index('ux_registry_role_mappings_current', table_name='registry_role_mappings')
    op.drop_index('ix_registry_role_mappings_restaurant_id', table_name='registry_role_mappings')
    op.drop_table('registry_role_mappings')
    op.drop_index('ux_registry_role_departments_current', table_name='registry_role_departments')
    op.drop_index('ix_registry_role_departments_restaurant_role_id', table_name='registry_role_departments')
    op.drop_table('registry_role_departments')
    op.drop_index('ix_registry_departments_operational_area_id', table_name='registry_departments')
    op.drop_table('registry_departments')
    # The roles Cook, Dishwasher and Server Help stay in the role catalog: assignments may reference them.
