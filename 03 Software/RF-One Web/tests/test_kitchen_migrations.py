"""Frozen PostgreSQL release DDL: no duplicate active column or unrelated tables."""
from pathlib import Path
import importlib.util,io,re
from alembic.migration import MigrationContext
from alembic.operations import Operations
STORE=Path(__file__).resolve().parents[2]/'RF-One Data Store/migrations/versions'
def ddl(*names):
    output=io.StringIO()
    context=MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output})
    with Operations.context(context):
        for name in names:
            spec=importlib.util.spec_from_file_location(name,STORE/name);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.upgrade()
    return output.getvalue()
historical=ddl('k9d120261112_kitchen_menus.py','k9f120261112_active_menu_per_location.py')
initial=historical.split('CREATE TABLE kitchen_menu_entries',1)[0]
assert not re.search(r'\bactive\b',initial)
assert historical.count('ADD COLUMN active BOOLEAN')==1
assert historical.count('CREATE UNIQUE INDEX uq_kitchen_active_menu_location')==1
release=ddl('k9g120261112_kitchen_aws_release.py')
assert release.count('elapsed_preparation_minutes')==1
assert release.count('active BOOLEAN')==1
assert 'UPDATE ' not in release and 'DROP TABLE' not in release
assert 'student' not in release.lower() and 'rfone_account' not in release.lower()
assert 'WHERE active' in release
print('PASS: frozen menu migration sequence, one active column/index, Kitchen-only PostgreSQL release DDL; no identity/data mutations')
