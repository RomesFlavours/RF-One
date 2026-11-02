"""Runtime verification: immutable artifact, isolated tests, optional DB reads.

No source synchronization and no database writes. The database check requires
the objects the connector maps, not an exact Alembic revision: another Domain's
newer additive migration must not stop the workers (MIGRATIONS.md).
"""
import json,hashlib,sys,unittest,os
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root));sys.path.insert(0,str(root.parent/'Clover Data Explorer'))
manifest=json.loads((root/'clover_connector_release.json').read_text())
# Employee directory (c8e1f4a7b2d6), person foundation (d9e220261029) and shifts.
CLOVER_REQUIRED_TABLES=('employees','employee_clover_links','employee_identity_aliases','employee_directory_events','employee_context_links','shifts')

def database_summary(engine):
    from sqlalchemy import text
    from rfone_data_store.models import Base
    from rfone_data_store.schema_compatibility import require_compatible_schema
    report=require_compatible_schema(engine,[Base.metadata.tables[n] for n in CLOVER_REQUIRED_TABLES],service='Clover connector (Employee Directory schema)')
    out={'schema_revision':list(report.revisions),'revision_known':bool(report.revisions) and not report.unknown_revisions}
    with engine.connect() as c:
        out['directory_links']=c.scalar(text('select count(*) from employee_clover_links'))
        out['employees']=dict(c.execute(text('''select count(*) as total,count(*) filter(where source_available) as available,count(*) filter(where source_available=false) as unavailable,count(*) filter(where source_available=false and display_name is not null) as historical_named from employees where source_system_id=1''')).mappings().one())
        out['orphan_shifts']=c.scalar(text('select count(*) from shifts s left join employees e on e.id=s.employee_id where e.id is null'))
    assert out['orphan_shifts']==0
    return out

def main(argv):
    for path,digest in manifest['files'].items():
        actual=root.parent/path
        assert hashlib.sha256(actual.read_bytes()).hexdigest()==digest,'Runtime artifact mismatch'
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(n) for n in ('test_clover_employee_history','test_clover_monthly_recovery','test_clover_line_presence'))
    result=unittest.TextTestRunner().run(suite)
    assert result.wasSuccessful()
    out={'release':manifest['release'],'tests_passed':result.testsRun,'artifact_verified':True,'database_writes':False}
    if '--database-readonly' in argv:
        from sqlalchemy import create_engine
        engine=create_engine(os.environ['RFONE_DATABASE_URL'],connect_args={'sslmode':'require','options':'-c default_transaction_read_only=on'})
        try:out.update(database_summary(engine))
        finally:engine.dispose()
    print('CLOVER_RELEASE_VERIFIED '+json.dumps(out),flush=True)

if __name__=='__main__':main(sys.argv)
