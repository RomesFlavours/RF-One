from pathlib import Path
p=Path('tmp/git-anagrafica-release/03 Software/RF-One Data Store/migrations/versions/r1a120261112_person_reconciliation.py')
p.write_text('''"""Explicit central identity links; no historical backfill or grant writes."""
from alembic import op
import sqlalchemy as sa
revision='r1a120261112'
down_revision='t9a120261110'
branch_labels=None
depends_on=None


def upgrade():
    bind=op.get_bind()
    def create(name,*columns):
        if not sa.inspect(bind).has_table(name):
            op.create_table(name,*columns)
            return True
        return False
    create('person_account_links',
        sa.Column('account_id',sa.Integer(),sa.ForeignKey('rfone_accounts.id'),primary_key=True),
        sa.Column('person_id',sa.Integer(),sa.ForeignKey('candidate_persons.id'),nullable=False,unique=True),
        sa.Column('linked_by_id',sa.Integer(),sa.ForeignKey('rfone_accounts.id'),nullable=False),
        sa.Column('linked_at',sa.DateTime(timezone=True),nullable=False))
    if create('person_employee_links',
        sa.Column('employee_id',sa.Integer(),sa.ForeignKey('employees.id'),primary_key=True),
        sa.Column('person_id',sa.Integer(),sa.ForeignKey('candidate_persons.id'),nullable=False),
        sa.Column('linked_by_id',sa.Integer(),sa.ForeignKey('rfone_accounts.id'),nullable=False),
        sa.Column('linked_at',sa.DateTime(timezone=True),nullable=False)):
        op.create_index('ix_person_employee_links_person_id','person_employee_links',['person_id'])
    create('training_person_links',
        sa.Column('training_account_id',sa.Integer(),sa.ForeignKey('training_accounts.id'),primary_key=True),
        sa.Column('person_id',sa.Integer(),sa.ForeignKey('candidate_persons.id'),nullable=False,unique=True))
    create('person_qualifications',
        sa.Column('person_id',sa.Integer(),sa.ForeignKey('candidate_persons.id'),primary_key=True),
        sa.Column('code',sa.String(32),primary_key=True),
        sa.Column('assigned_at',sa.DateTime(timezone=True),nullable=False))
    create('person_reconciliation_events',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('person_id',sa.Integer(),sa.ForeignKey('candidate_persons.id'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('rfone_accounts.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('action',sa.String(32),nullable=False),
        sa.Column('details',sa.JSON(),nullable=False))


def downgrade():
    raise RuntimeError('Person identity links and reconciliation history must be preserved.')
''',encoding='utf-8',newline='\n')
p=Path('tmp/git-anagrafica-release/03 Software/RF-One Data Store/test_person_reconciliation.py');s=p.read_text(encoding='utf-8');pos=s.index('\nif __name__');s=s[:pos]+'''
 def test_shared_writers_reject_conflicting_confirmed_bridges(self):
  with self.factory() as db:
   p=self.person(db);self.confirm(db,person_id=p.id);q=self.person(db,'Different person')
   with self.assertRaises(ValueError):people.link_source(db,db.get(m.RFOneAccount,self.admin),q.id,'employee',self.employee)
   with self.assertRaises(ValueError):students.attach(db,q,db.get(m.RFOneAccount,self.account),db.get(m.TrainingAccount,self.training))
   self.assertEqual(db.get(people.PersonAccountLink,self.account).person_id,p.id)
 def test_frozen_migration_preserves_populated_core_and_is_repeatable(self):
  import importlib.util
  from alembic.migration import MigrationContext
  from alembic.operations import Operations
  path=Path(__file__).resolve().parent/'migrations/versions/r1a120261112_person_reconciliation.py'
  spec=importlib.util.spec_from_file_location('identity_migration',path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
  with self.engine.begin() as connection:
   # Only newly added tables in this disposable fixture are recreated.
   for model in reversed(rec.TABLES):model.__table__.drop(connection)
   before=connection.execute(select(func.count()).select_from(m.RFOneAccount)).scalar()
   operations=Operations(MigrationContext.configure(connection))
   from unittest.mock import patch
   with patch.object(migration,'op',operations):migration.upgrade();migration.upgrade()
   self.assertEqual(connection.execute(select(func.count()).select_from(m.RFOneAccount)).scalar(),before)
   self.assertEqual(connection.execute(select(func.count()).select_from(rec.PersonReconciliationEvent)).scalar(),0)
   with self.assertRaises(RuntimeError):migration.downgrade()
'''+s[pos:];p.write_text(s,encoding='utf-8',newline='\n')
