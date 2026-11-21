"""Build-time cold import and exact overlay hash checks; no database/migration/seed."""
from pathlib import Path
import hashlib,json,os,socket,sys
root=Path('/app')
manifest=json.loads((root/'release-enrollment-manifest.json').read_text())
for path,digest in manifest['files'].items():
    actual=root/Path(path).relative_to('03 Software')
    assert hashlib.sha256(actual.read_bytes()).hexdigest()==digest,path
def no_connect(*args,**kwargs):raise RuntimeError('Startup must not contact the database or network')
socket.socket.connect=no_connect
os.environ['RFONE_DATABASE_URL']='postgresql+psycopg2://startup:unused@127.0.0.1:1/startup'
os.environ['RFONE_FLASK_SECRET_KEY']='build-only-non-runtime-test-secret'
sys.path.insert(0,str(root/'RF-One Web'))
import training_cloud
app=training_cloud.app
assert app.config['SESSION_COOKIE_SECURE']
assert not app.config.get('TRAINING_ENROLLMENT_LOCAL')
assert not app.config.get('RFONE_LOCAL_OPERATOR')
assert {'tw_enrollment','tw_enrollment_activation','tw_enrollment_link'} <= set(app.view_functions)
print('PASS: exact English enrollment overlay cold imports without network, database, migration or seed.')
