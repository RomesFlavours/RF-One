"""Run inside the built image, against a disposable release-test PostgreSQL clone."""
import io
import json
import os
import sys
from uuid import uuid4
from pathlib import Path
from unittest.mock import patch

sys.path[:0] = ['/app/Selection', '/app/RF-One Data Store']
from sqlalchemy import select, func
from sqlalchemy.engine import make_url

url = make_url(os.environ['RFONE_DATABASE_URL'])
if url.database is None or not url.database.startswith('selection_release_test_') or url.host != '10.0.2.2':
    raise SystemExit('Release verification is restricted to the isolated local clone.')


class MemoryS3:
    def __init__(self):
        self.objects = {}

    def upload_file(self, path, bucket, key, ExtraArgs):
        self.objects[key] = Path(path).read_bytes()

    def get_object(self, Bucket, Key):
        return {'Body': io.BytesIO(self.objects[Key])}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)
        return {'ContentLength': len(self.objects[Key])}

    def list_object_versions(self, Bucket, Prefix):
        return {'Versions': [{'Key': key, 'VersionId': 'test'} for key in self.objects if key.startswith(Prefix)]}

    def delete_object(self, Bucket, Key, VersionId):
        self.objects.pop(Key, None)


with patch('boto3.client', return_value=MemoryS3()):
    import app

from flask import Flask
from PIL import Image, ImageDraw, ImageFont
from rfone_data_store import models as m, rfone_account_service as accounts, rfone_web_session as auth
from rfone_data_store.selection import workspace_models as ps, document_store
from rfone_data_store.selection.parsing.text_extraction import extract_text
from workspace import engine, routes
from werkzeug.datastructures import FileStorage

result = {'aws_calls': 0, 'linux': sys.platform, 'postgresql': True}
with app.SessionFactory() as db:
    before = db.scalar(select(func.count()).select_from(ps.Proposal))
    allowed = accounts.create_account(db, username='release-qa-allowed-'+uuid4().hex[:8], display_name='Release QA Allowed', password='Synthetic-release-pass-1')
    denied = accounts.create_account(db, username='release-qa-denied-'+uuid4().hex[:8], display_name='Release QA Denied', password='Synthetic-release-pass-2')
    accounts.set_domain_access(db, account_id=allowed.id, domain_code='SELECTION', enabled=True, role_code='OWNER')
    db.commit()
    allowed_id, allowed_version = allowed.id, allowed.session_version
    denied_id, denied_version = denied.id, denied.session_version
    Path('/release-results/http-session-fixture.json').write_text(json.dumps({'allowed': [allowed_id, allowed_version], 'denied': [denied_id, denied_version]}))


def client(account_id=None, version=None):
    value = app.app.test_client()
    if account_id:
        with value.session_transaction() as session:
            session[auth.SESSION_ACCOUNT_KEY] = account_id
            session[auth.SESSION_VERSION_KEY] = version
    return value


assert client().get('/selection/').status_code == 302
assert client(denied_id, denied_version).get('/selection/').status_code == 403
assert client(allowed_id, allowed_version + 1).get('/selection/').status_code == 302
authorized = client(allowed_id, allowed_version)
paths = ['/selection/', '/selection/requisiti-priorita', '/selection/configurazioni',
         '/selection/posizioni/7', '/selection/posizioni/7/interviews', '/selection/posizioni/7/sp/upload?modal=1']
for path in paths:
    response = authorized.get(path, follow_redirects=True)
    assert response.status_code == 200, (path, response.status_code)
    text = response.get_data(as_text=True)
    assert 'How this page works' in text, path
    assert 'Come funziona questa pagina' not in text, path
result['shared_authentication'] = True
result['english_pages'] = len(paths)

storage = document_store.S3DocumentStore('synthetic-selection-release', client=MemoryS3())
with app.SessionFactory() as db:
    position = db.get(ps.Position, 7)
    raw_bytes = b'Release Synthetic Candidate\nrelease.qa@example.test\nEXPERIENCE\nServer at QA Restaurant\n2022 - 2024\n'
    with patch('workspace.rule_ai.generate', side_effect=AssertionError('Upload must not call AI')):
        imported = engine.import_cv(db, documents=storage, restaurant_id=1, position=position,
            file_storage=FileStorage(stream=io.BytesIO(raw_bytes), filename='release-synthetic.txt'),
            channel=ps.MANUAL_UPLOAD, actor_id=allowed_id, actor_name='Release QA', analyze_after=False, ai_reading=False)
    assert imported['status'] == 'OK', imported
    pc = db.get(ps.PositionCandidate, imported['position_candidate_id'])
    candidate = db.get(m.Candidate, pc.candidate_id)
    raw = db.get(m.RawResume, candidate.raw_resume_id)
    assert storage.read(raw.storage_path) == raw_bytes
    assert db.scalar(select(func.count()).select_from(ps.Proposal)) == before
result['upload_original_preserved_without_evaluation'] = True

# Actual Linux OCR backend, using a generated image-only PDF with synthetic text.
image = Image.new('RGB', (1400, 600), 'white')
draw = ImageDraw.Draw(image)
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 44) if Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf').exists() else ImageFont.load_default(size=44)
draw.text((60, 80), 'Release Synthetic Candidate', fill='black', font=font)
draw.text((60, 170), 'Server experience 2022 - 2024', fill='black', font=font)
image.save('/tmp/release-image-only.pdf', 'PDF', resolution=150)
text = extract_text('/tmp/release-image-only.pdf', '.pdf')
assert 'Synthetic' in text and '2022' in text, text
result['native_linux_ocr'] = True
Path('/release-results/linux-smoke.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
