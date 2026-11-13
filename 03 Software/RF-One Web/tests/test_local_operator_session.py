"""Local-preview boundaries; production/default behavior remains off."""
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'RF-One Data Store'))
from flask import Flask
from local_operator_session import local_admin_preview

app=Flask(__name__)
admin=SimpleNamespace(username='rfone',is_admin=True,status='ACTIVE')
assert not local_admin_preview(admin)
with app.test_request_context('/',environ_base={'REMOTE_ADDR':'127.0.0.1'}):
    assert not local_admin_preview(admin)
    app.config['RFONE_LOCAL_OPERATOR']='rfone'
    assert local_admin_preview(admin)
    assert not local_admin_preview(SimpleNamespace(username='other',is_admin=True,status='ACTIVE'))
    assert not local_admin_preview(SimpleNamespace(username='rfone',is_admin=False,status='ACTIVE'))
    assert not local_admin_preview(SimpleNamespace(username='rfone',is_admin=True,status='DISABLED'))
with app.test_request_context('/',environ_base={'REMOTE_ADDR':'192.0.2.1'}):
    assert not local_admin_preview(admin)
print('PASS: default off, loopback only, named active administrator only, remote/inactive/non-admin denied')
