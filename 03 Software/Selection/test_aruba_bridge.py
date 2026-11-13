"""Isolated HTTP tests, synthetic identities, no provider or production calls."""
import hashlib
import hmac
import json
import os
import re
import tempfile
import time
from urllib.parse import parse_qs, urlparse

tmp = tempfile.TemporaryDirectory(prefix='selection_aruba_test_')
os.environ.update(RFONE_DATABASE_URL='sqlite:///' + tmp.name.replace('\\', '/') + '/test.db',
    RFONE_SELECTION_REQUIRE_RFONE_LOGIN='1', RFONE_FLASK_SECRET_KEY='synthetic-test-secret',
    RFONE_WEB_BASE_URL='https://rfone.example.test', RFONE_SELECTION_ARUBA_KEY='a' * 64,
    RFONE_SELECTION_UPLOAD_DIR=tmp.name + '/uploads')
os.environ.pop('RFONE_PUBLIC_BASE_URL', None)
os.environ.pop('RFONE_SELECTION_DOCUMENT_BUCKET', None)
import app
from workspace.schema import provision
provision(app._engine)

client = app.app.test_client()
other = app.app.test_client()
BASE = 'https://rfone.example.test'
PREFIX = '/selection'
start = client.get(PREFIX + '/candidate/bridge/start', base_url=BASE)
assert start.status_code == 302
state = parse_qs(urlparse(start.location).query)['state'][0]


def relay(action, **fields):
    body = json.dumps(dict(action=action, state=state, **fields)).encode()
    stamp = str(int(time.time()))
    signature = hmac.new(b'a' * 64, stamp.encode() + b'\n' + body, hashlib.sha256).hexdigest()
    return client.post(PREFIX + '/candidate/bridge/relay', data=body, content_type='application/json',
        headers={'X-RFOne-Time': stamp, 'X-RFOne-Signature': signature}, base_url=BASE)


assert client.post(PREFIX + '/candidate/bridge/relay', json={}, base_url=BASE).status_code == 403
print('PASS unsigned relay is refused')
r = relay('code', full_name='Synthetic Candidate', email='bridge@example.test', ip='192.0.2.1')
assert r.status_code == 200, r.data
code = r.json['delivery_code']
assert len(code) == 6
print('PASS authenticated server gets the code for local delivery')
assert not relay('confirm', email='bridge@example.test', code='wrong').json['ok']
print('PASS wrong code is refused')
r = relay('confirm', email='bridge@example.test', code=code)
assert r.json['ok'], r.data
finish = urlparse(r.json['redirect']).path + '?' + urlparse(r.json['redirect']).query
assert other.get(finish, base_url=BASE).status_code == 400
print('PASS another browser cannot redeem the ticket')
r = client.get(finish, base_url=BASE)
assert r.status_code == 200
csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.get_data(as_text=True)).group(1)
ticket = parse_qs(urlparse(finish).query)['ticket'][0]
assert client.post(PREFIX + '/candidate/bridge/finish', data={'ticket': ticket}, base_url=BASE).status_code == 302
r = client.post(PREFIX + '/candidate/bridge/finish', data={'ticket': ticket, 'csrf_token': csrf}, base_url=BASE)
assert r.status_code == 303, r.data
assert client.get(PREFIX + '/candidate', base_url=BASE).status_code == 200
print('PASS code opens the AWS candidate session')
assert client.get(finish, base_url=BASE).status_code == 400
print('PASS redeemed ticket cannot be replayed')
r = client.get(PREFIX + '/', base_url=BASE)
assert r.status_code == 302 and '/login?' in r.location
print('PASS candidate session grants no staff access')
assert not relay('confirm', email='bridge@example.test', code=code).json['ok']
print('PASS a consumed OTP cannot be reused')
r = relay('code', full_name='A Different Name', email='bridge@example.test', ip='192.0.2.1')
assert r.json['ok'], r.data
new_code = r.json['delivery_code']
r = relay('confirm', email='bridge@example.test', code=new_code)
assert r.json['ok'], r.data
with app.SessionFactory() as db:
    from rfone_data_store.selection import candidate_identity_service as identity
    account = identity.get_account_by_email(db, 'bridge@example.test')
    assert account.full_name == 'Synthetic Candidate'
print('PASS returning candidates use only a new email code; their identity is preserved')
print('ALL BRIDGE TESTS PASSED')
app._engine.dispose()
tmp.cleanup()
