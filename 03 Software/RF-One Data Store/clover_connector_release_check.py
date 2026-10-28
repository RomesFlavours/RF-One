"""Runtime verification: immutable artifact, isolated tests, optional DB reads.

No source synchronization and no database writes.
"""
import json,hashlib,sys,unittest,os
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root));sys.path.insert(0,str(root.parent/'Clover Data Explorer'))
manifest=json.loads((root/'clover_connector_release.json').read_text())
for path,digest in manifest['files'].items():
    actual=root.parent/path
    assert hashlib.sha256(actual.read_bytes()).hexdigest()==digest,'Runtime artifact mismatch'
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(n) for n in ('test_clover_employee_history','test_clover_monthly_recovery','test_clover_line_presence'))
result=unittest.TextTestRunner().run(suite)
assert result.wasSuccessful()
out={'release':manifest['release'],'tests_passed':result.testsRun,'artifact_verified':True,'database_writes':False}
if '--database-readonly' in sys.argv:
    from sqlalchemy import create_engine,text
    engine=create_engine(os.environ['RFONE_DATABASE_URL'],connect_args={'sslmode':'require','options':'-c default_transaction_read_only=on'})
    with engine.connect() as c:
        assert c.scalar(text('select version_num from alembic_version'))=='c8e1f4a7b2d6','Employee Directory schema is not ready'
        out['directory_links']=c.scalar(text('select count(*) from employee_clover_links'))
        out['employees']=dict(c.execute(text('''select count(*) as total,count(*) filter(where source_available) as available,count(*) filter(where source_available=false) as unavailable,count(*) filter(where source_available=false and display_name is not null) as historical_named from employees where source_system_id=1''')).mappings().one())
        out['orphan_shifts']=c.scalar(text('select count(*) from shifts s left join employees e on e.id=s.employee_id where e.id is null'))
        assert out['orphan_shifts']==0
    engine.dispose()
print('CLOVER_RELEASE_VERIFIED '+json.dumps(out),flush=True)
