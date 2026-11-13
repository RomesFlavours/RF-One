"""Shared additive role profiles and explicit company memberships."""
from alembic import op
import sqlalchemy as sa

revision='f2a120261110'
down_revision='e2c320261109'
branch_labels=None
depends_on=None


def upgrade():
    for table in ('restaurant_roles','operational_areas'):
        with op.batch_alter_table(table) as batch:
            batch.alter_column('restaurant_id',existing_type=sa.Integer(),nullable=True)
    for table,label in [('restaurant_roles','role'),('operational_areas','area')]:
        predicate=sa.text('restaurant_id IS NULL')
        op.create_index('uq_shared_profile_'+label+'_name',table,[sa.text('lower(name)')],unique=True,
                        postgresql_where=predicate,sqlite_where=predicate)
    op.create_table('rfone_company_contexts',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('name',sa.String(255),nullable=False,unique=True),
        sa.Column('kind',sa.String(16),nullable=False),sa.Column('legal_entity_id',sa.Integer(),sa.ForeignKey('legal_entities.id'),unique=True),
        sa.Column('active',sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.CheckConstraint("kind IN ('COMPANY','GROUP')",name='ck_rfone_company_kind'))
    op.create_table('rfone_person_company_memberships',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('employee_id',sa.Integer(),sa.ForeignKey('employees.id')),
        sa.Column('account_id',sa.Integer(),sa.ForeignKey('rfone_accounts.id')),
        sa.Column('company_id',sa.Integer(),sa.ForeignKey('rfone_company_contexts.id'),nullable=False),
        sa.Column('valid_from',sa.DateTime(timezone=True),nullable=False),sa.Column('valid_to',sa.DateTime(timezone=True)),
        sa.CheckConstraint('(employee_id IS NOT NULL AND account_id IS NULL) OR (employee_id IS NULL AND account_id IS NOT NULL)',name='ck_company_membership_target'))
    for target in ('employee','account'):
        predicate=sa.text(f'valid_to IS NULL AND {target}_id IS NOT NULL')
        op.create_index('uq_company_'+target+'_open','rfone_person_company_memberships',[target+'_id','company_id'],unique=True,postgresql_where=predicate,sqlite_where=predicate)
        op.create_index('ix_rfone_person_company_memberships_'+target+'_id','rfone_person_company_memberships',[target+'_id'])
    op.create_index('ix_rfone_person_company_memberships_company_id','rfone_person_company_memberships',['company_id'])
    op.create_table('rfone_role_profile_assignments',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('membership_id',sa.Integer(),sa.ForeignKey('rfone_person_company_memberships.id'),nullable=False),
        sa.Column('role_id',sa.Integer(),sa.ForeignKey('restaurant_roles.id'),nullable=False),
        sa.Column('area_id',sa.Integer(),sa.ForeignKey('operational_areas.id'),nullable=False),
        sa.Column('valid_from',sa.DateTime(timezone=True),nullable=False),sa.Column('valid_to',sa.DateTime(timezone=True)))
    predicate=sa.text('valid_to IS NULL')
    op.create_index('uq_profile_assignment_open','rfone_role_profile_assignments',['membership_id','role_id','area_id'],unique=True,postgresql_where=predicate,sqlite_where=predicate)
    for name in ('membership_id','role_id'):op.create_index('ix_rfone_role_profile_assignments_'+name,'rfone_role_profile_assignments',[name])
    op.create_table('rfone_role_permissions',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('role_id',sa.Integer(),sa.ForeignKey('restaurant_roles.id'),nullable=False),
        sa.Column('domain_code',sa.String(64),nullable=False),sa.Column('scope',sa.String(16),nullable=False),
        sa.Column('role_code',sa.String(64)),sa.Column('items',sa.JSON(),nullable=False),
        sa.UniqueConstraint('role_id','domain_code',name='uq_profile_role_domain'),
        sa.CheckConstraint("scope IN ('ALL','SELECTED')",name='ck_profile_permission_scope'))
    op.create_index('ix_rfone_role_permissions_role_id','rfone_role_permissions',['role_id'])
    op.create_table('rfone_access_profile_events',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('account_id',sa.Integer(),sa.ForeignKey('rfone_accounts.id')),sa.Column('action',sa.String(64),nullable=False),
        sa.Column('details',sa.JSON(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    db=op.get_bind()
    companies=sa.table('rfone_company_contexts',sa.column('name'),sa.column('kind'),sa.column('legal_entity_id'),sa.column('active'))
    labels={'RF-Winter Park':'WP','RF-Mount Dora':'MD'}
    for identity,name,status in db.execute(sa.text('SELECT id,legal_name,status FROM legal_entities ORDER BY id')):
        db.execute(companies.insert().values(name=labels.get(name,name),kind='COMPANY',legal_entity_id=identity,active=status=='ACTIVE'))
    db.execute(companies.insert().values(name='RFGroup',kind='GROUP',legal_entity_id=None,active=True))
    # Reuse factual role/area relationships already present in Workforce. No people,
    # company memberships, access grants or employment assignments are guessed.
    pairs=sa.table('operational_area_roles',sa.column('operational_area_id'),sa.column('restaurant_role_id'))
    for area,role in db.execute(sa.text('SELECT DISTINCT operational_area_id,restaurant_role_id FROM employee_assignments')):
        known=db.scalar(sa.select(sa.func.count()).select_from(pairs).where(pairs.c.operational_area_id==area,pairs.c.restaurant_role_id==role))
        if not known:db.execute(pairs.insert().values(operational_area_id=area,restaurant_role_id=role))


def downgrade():
    raise RuntimeError('Role/profile/company history must be retained; restore the verified local dump instead.')
