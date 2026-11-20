"""Synthetic only: isolated DB, no Indeed/AWS/AI calls. Run as a separate process."""
import os
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

TMP = tempfile.TemporaryDirectory(prefix='rfone-indeed-test-')
os.environ.update(RFONE_DATABASE_URL='sqlite:///' + (Path(TMP.name) / 'selection.db').as_posix(),
                  RFONE_SELECTION_UPLOAD_DIR=str(Path(TMP.name) / 'uploads'),
                  RFONE_SELECTION_REQUIRE_RFONE_LOGIN='1', RFONE_WEB_BASE_URL='https://rfone.example.test',
                  RFONE_FLASK_SECRET_KEY='synthetic-session-secret', RFONE_INDEED_KEY='synthetic-' + 'x' * 40,
                  RFONE_INDEED_WORKER_URL='https://browser.example.test',
                  RFONE_INDEED_PUBLIC_URL='https://browser.example.test',
                  RFONE_INDEED_SELECTION_URL='https://rfone.example.test/selection')
for name in ('RFONE_SELECTION_CANONICAL_LOCAL', 'RFONE_SELECTION_DOCUMENT_BUCKET', 'RFONE_PUBLIC_BASE_URL',
             'RFONE_SELECTION_AI', 'RFONE_SELECTION_AI_CV'):
    os.environ.pop(name, None)

# Unrelated migrations currently have multiple heads. This test creates ONLY
# its disposable database from the runtime metadata; never patch production.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'RF-One Data Store'))
def synthetic_schema(url):
    from rfone_data_store.models import Base
    from sqlalchemy import create_engine
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()

with patch('rfone_data_store.database.run_migrations_to_head', side_effect=synthetic_schema):
    import app as selection
from workspace import indeed
from workspace.schema import provision
from rfone_data_store import rfone_account_service as accounts, rfone_web_session as sessions
from rfone_data_store.selection import workspace_models as ps
from rfone_data_store.selection.parsing.ai_test_isolation import isolated_ai_client
from sqlalchemy import select
from indeed_protocol import list_url
from indeed_worker.service import create_app
from indeed_worker.store import Store

URL = 'https://employers.indeed.com/candidates?selectedJobs=synthetic&employerJobId=synthetic'
AUTH = {'Authorization': 'Bearer ' + os.environ['RFONE_INDEED_KEY']}
CV = b'Jordan Synthetic\njordan@example.test\nServer, Sample Restaurant, Orlando, FL | Jan 2022 - Present\n- Table service\n'


class IndeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        provision(selection._engine)
        cls.ai = isolated_ai_client()
        cls.guard = cls.ai.__enter__()
        cls.app = selection.app
        cls.app.config['TESTING'] = True
        cls.ids = {}
        with selection.SessionFactory() as db:
            for name, role in [('manager', 'MANAGER'), ('other', 'MANAGER'), ('supervisor', 'SUPERVISOR')]:
                acc = accounts.create_account(db, username='indeed-' + name, display_name=name,
                                              password='synthetic-password-1', is_admin=False)
                accounts.set_domain_access(db, account_id=acc.id, domain_code='SELECTION', enabled=True, role_code=role)
                cls.ids[name] = (acc.id, acc.session_version)
            db.commit()
        cls.manager = cls.client('manager')
        with cls.manager.session_transaction() as sess:
            sess[sessions.SESSION_CSRF_KEY] = 'test-csrf'
        cls.csrf = {'csrf_token': 'test-csrf'}
        # Create real positions through the existing HTTP flow.
        for title in ('Indeed A', 'Indeed B'):
            response = cls.manager.post('/selection/posizioni/nuova', data={
                **cls.csrf, 'title': title, 'role_code': 'SERVER', 'location': 'Mount Dora',
                'timezone': 'America/New_York', 'headcount': '1', 'description': 'Synthetic position'})
            if response.status_code != 302:
                raise AssertionError(response.get_data(as_text=True))
        with selection.SessionFactory() as db:
            cls.positions = [p.id for p in db.scalars(select(ps.Position).order_by(ps.Position.id))]

    @classmethod
    def tearDownClass(cls):
        assert not cls.guard.attempts, cls.guard.attempts
        cls.ai.__exit__(None, None, None)
        selection._engine.dispose()
        TMP.cleanup()

    @classmethod
    def client(cls, name):
        client = cls.app.test_client()
        with client.session_transaction() as sess:
            sess[sessions.SESSION_ACCOUNT_KEY], sess[sessions.SESSION_VERSION_KEY] = cls.ids[name]
            sess[sessions.SESSION_CSRF_KEY] = 'test-csrf'
        return client

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TMP.name)
        self.store = Store(Path(self.temp.name) / 'ledger.sqlite')
        self.worker = create_app(store=self.store, launch=False).test_client()

    def tearDown(self):
        self.temp.cleanup()

    def bridge(self, path, data=None):
        result = self.worker.open(path, method='GET' if data is None else 'POST', json=data, headers=AUTH)
        if result.status_code >= 400:
            raise ValueError(result.get_json())
        return result.get_json()

    def job(self):
        return self.bridge('/api/jobs', dict(url=URL, position_id=self.positions[0], actor_id=self.ids['manager'][0]))

    def test_url_validation(self):
        self.assertEqual(list_url(URL), URL)
        for url in ('https://evil.test/candidates?selectedJobs=x', 'https://employers.indeed.com.evil.test/candidates?selectedJobs=x',
                    'http://employers.indeed.com/candidates?selectedJobs=x', 'https://employers.indeed.com/jobs',
                    'https://user@employers.indeed.com/candidates?selectedJobs=x'):
            with self.assertRaises(ValueError):
                list_url(url)

    def test_worker_auth_exclusivity_viewer_and_revocation(self):
        self.assertEqual(self.worker.get('/api/jobs').status_code, 401)
        self.assertEqual(self.worker.get('/vnc.html').status_code, 403)
        job = self.job()
        self.assertEqual(self.worker.post('/api/jobs', json=dict(url=URL, position_id=2, actor_id=1), headers=AUTH).status_code, 409)
        self.store.update(job['id'], state='WAITING_LOGIN')
        url = self.bridge('/api/jobs/' + job['id'] + '/browser', {})['url']
        self.assertEqual(self.worker.get(url).status_code, 302)
        # Authenticated cookie can reach asset handling; unauthenticated was 403.
        self.assertEqual(self.worker.get('/does-not-exist', base_url='https://browser.example.test').status_code, 404)
        self.bridge('/api/jobs/' + job['id'] + '/resume', {})
        self.assertEqual(self.worker.get('/does-not-exist', base_url='https://browser.example.test').status_code, 403)
        self.assertEqual(self.worker.get(url).status_code, 403)

    def test_ui_permissions_csrf_and_bound_start(self):
        pid = self.positions[0]
        with patch.object(indeed, 'worker', side_effect=self.bridge):
            self.assertNotEqual(self.app.test_client().post(f'/selection/posizioni/{pid}/indeed', data={**self.csrf, 'url': URL}).status_code, 200)
            self.assertEqual(self.client('other').post(f'/selection/posizioni/{pid}/indeed', data={**self.csrf, 'url': URL}).status_code, 404)
            self.assertEqual(self.client('supervisor').post(f'/selection/posizioni/{pid}/indeed', data={**self.csrf, 'url': URL}).status_code, 403)
            self.manager.post(f'/selection/posizioni/{pid}/indeed', data={'url': URL})
            self.assertEqual(len(self.store.jobs()), 0)
            self.manager.post(f'/selection/posizioni/{pid}/indeed', data={**self.csrf, 'url': URL, 'position_id': self.positions[1], 'actor_id': 999})
            job = self.store.jobs()[0]
            self.assertEqual((job['position_id'], job['actor_id']), (pid, self.ids['manager'][0]))
            html = self.manager.get(f'/selection/posizioni/{pid}?tab=candidature').get_data(as_text=True)
            self.assertIn('Import résumés from Indeed', html)
            self.assertIn('Opening browser', html)
            self.app.config['RFONE_LOCAL_OPERATOR'] = True
            try:
                html = self.manager.get(f'/selection/posizioni/{pid}?tab=candidature').get_data(as_text=True)
                self.assertIn('Importa CV da Indeed', html)
                self.assertIn('Apertura browser', html)
            finally:
                self.app.config.pop('RFONE_LOCAL_OPERATOR', None)

    def test_real_import_position_binding_and_retry_dedup(self):
        job = self.job()
        self.store.update(job['id'], state='RUNNING')
        endpoint = f'/selection/internal/indeed/{job["id"]}/candidate1'
        client = self.app.test_client()  # Machine callback works without RF-One cookies.
        headers = {**AUTH, 'X-Resume-Filename': 'Synthetic.txt', 'Content-Type': 'application/octet-stream'}
        with patch.object(indeed, 'worker', side_effect=self.bridge):
            self.assertEqual(client.post(endpoint, data=CV).status_code, 401)
            first = client.post(endpoint, data=CV, headers=headers)
            self.assertEqual(first.status_code, 200, first.get_data(as_text=True))
            self.assertEqual(first.json['status'], 'OK')
            again = client.post(endpoint, data=CV, headers=headers)
            self.assertEqual(again.json['status'], 'DUPLICATE')
            self.assertEqual(first.json['position_candidate_id'], again.json['position_candidate_id'])
            with selection.SessionFactory() as db:
                pcs = list(db.scalars(select(ps.PositionCandidate)))
                self.assertEqual(len(pcs), 1)
                self.assertEqual((pcs[0].position_id, pcs[0].channel), (self.positions[0], 'INDEED'))
                candidate = db.get(selection.m.Candidate, pcs[0].candidate_id)
                self.assertEqual((candidate.source, candidate.source_provider), ('INDEED_BROWSER', 'indeed'))
                raw = db.get(selection.m.RawResume, candidate.raw_resume_id)
                self.assertEqual(selection.DOCUMENTS.read(raw.storage_path), CV)
            # Bind actions to worker metadata, never a caller-supplied position.
            self.manager.post(f'/selection/posizioni/{self.positions[1]}/indeed/{job["id"]}/stop', data=self.csrf)
            self.assertEqual(self.store.get(job['id'])['state'], 'RUNNING')
            self.store.update(job['id'], actor_id=self.ids['supervisor'][0])
            self.assertEqual(client.post(endpoint, data=CV, headers=headers).status_code, 403)
            self.store.update(job['id'], state='STOPPED')
            self.assertEqual(client.post(endpoint, data=CV, headers=headers).status_code, 409)

    def test_restart_preserves_checkpoints_and_requires_login(self):
        job = self.job()
        self.store.update(job['id'], state='RUNNING')
        self.store.checkpoint(job['id'], 'abc', 'OK', '123')
        restarted = Store(self.store.path)
        self.assertEqual(restarted.get(job['id'])['state'], 'PAUSED')
        self.assertEqual(restarted.get(job['id'])['items'][0]['status'], 'OK')
        self.bridge('/api/jobs/' + job['id'] + '/resume', {})
        self.assertEqual(self.store.get(job['id'])['state'], 'STARTING')

    def test_s3_archive_and_duplicate_cleanup(self):
        from rfone_data_store.selection.document_store import S3DocumentStore
        objects, staged_paths = {}, []
        class SyntheticS3:
            def upload_file(self, path, bucket, key, ExtraArgs):
                self.assert_encrypted = ExtraArgs['ServerSideEncryption'] == 'AES256'
                objects[key] = Path(path).read_bytes()
                staged_paths.append(path)
            def list_object_versions(self, Bucket, Prefix):
                return {'Versions': [{'Key': k, 'VersionId': '1'} for k in objects if k.startswith(Prefix)]}
            def delete_object(self, Bucket, Key, VersionId):
                del objects[Key]
        fake = SyntheticS3()
        documents = S3DocumentStore('synthetic-private-bucket', client=fake)
        job = self.job()
        self.store.update(job['id'], state='RUNNING', position_id=self.positions[1])
        endpoint = f'/selection/internal/indeed/{job["id"]}/candidateS3'
        headers = {**AUTH, 'X-Resume-Filename': 'SyntheticS3.txt', 'Content-Type': 'application/octet-stream'}
        content = CV.replace(b'Jordan', b'Casey').replace(b'jordan@', b'casey@')
        with patch.object(indeed, 'worker', side_effect=self.bridge), patch.object(indeed.r._cfg, 'documents', documents):
            response = self.app.test_client().post(endpoint, data=content, headers=headers)
            self.assertEqual(response.json['status'], 'OK')
            repeat = self.app.test_client().post(endpoint, data=content, headers=headers)
            self.assertEqual(repeat.json['status'], 'DUPLICATE')
        self.assertTrue(fake.assert_encrypted)
        self.assertEqual(len(objects), 1)
        self.assertEqual(list(objects.values()), [content])
        self.assertTrue(all(not Path(p).exists() for p in staged_paths))
        with selection.SessionFactory() as db:
            pc = db.get(ps.PositionCandidate, response.json['position_candidate_id'])
            self.assertEqual(pc.position_id, self.positions[1])
            candidate = db.get(selection.m.Candidate, pc.candidate_id)
            raw = db.get(selection.m.RawResume, candidate.raw_resume_id)
            self.assertTrue(raw.storage_path.startswith('s3://synthetic-private-bucket/selection/resumes/'))


if __name__ == '__main__':
    unittest.main()
