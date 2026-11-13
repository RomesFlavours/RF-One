from pathlib import Path
p=Path('tmp/audit_registry_selection_local.py');t=p.read_text(encoding='utf-8');needle="spec=importlib.util.spec_from_file_location";i=t.index(needle);t=t[:i]+'''# The fixture was built from current metadata; mark only this disposable SQLite
# schema so the standalone app does not replay its full baseline bootstrap.
with e.begin() as db:
 db.execute(text('CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)'))
 db.execute(text('DELETE FROM alembic_version'))
 db.execute(text("INSERT INTO alembic_version(version_num) VALUES ('f3b120261110')"))
''' +t[i:];p.write_text(t,encoding='utf-8')
