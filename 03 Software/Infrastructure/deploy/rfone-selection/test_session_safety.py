"""Session safety of the release tooling (fix A6).

1. No versioned deploy, migration or test script signs a session or reads the Flask session key.
2. verify_http_release.py signs in only through the normal login form, sends only GET requests afterwards and
   reports authenticated checks as NOT VERIFIED when no authorized test account is supplied.
3. The Selection app rejects a session cookie signed with any other key (throwaway SQLite database).
No network, no AWS, no secret.

    python test_session_safety.py
"""
import importlib.util
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
APP = REPO / '03 Software/AWSSelection/Selection'
FORBIDDEN = re.compile(r'get_signing_serializer|SecureCookieSessionInterface|flask-secret-key|RFONE_FLASK_SECRET_KEY\s*=\s*[^\n]*get_secret')


def scripts():
    roots = [REPO / '03 Software/Infrastructure', APP]
    for root in roots:
        for path in root.rglob('*.py'):
            if '__pycache__' in path.parts or path.name == Path(__file__).name:
                continue
            if root == APP and not path.name.startswith('test_'):
                continue   # the application's own runtime tokens are not test or deploy tooling
            yield path


class StaticGuard(unittest.TestCase):
    def test_no_script_signs_sessions_or_reads_the_session_key(self):
        scanned = list(scripts())
        self.assertGreater(len(scanned), 40)   # deploy, migration and the release tests are really scanned
        self.assertIn(HERE / 'verify_http_release.py', scanned)
        offenders = [str(p.relative_to(REPO)) for p in scanned if FORBIDDEN.search(p.read_text(encoding='utf-8'))]
        self.assertEqual(offenders, [])

    def test_http_verifier_has_no_secret_access(self):
        source = (HERE / 'verify_http_release.py').read_text(encoding='utf-8')
        for word in ('boto3', 'secretsmanager', 'secret_key', 'itsdangerous', 'flask'):
            self.assertNotIn(word, source.lower().replace('secrets_read', ''), word)


class Response:
    def __init__(self, status, url, text='', location=None):
        self.status_code, self.url, self.text, self.content = status, url, text, text.encode()
        self.headers = {'Location': location} if location else {}


class FakeHttp:
    """Records every request; behaves like RF-One for an authorized test account."""
    def __init__(self):
        self.calls = []
        outer = self

        class Session:
            def __init__(self):
                self.headers = {}

            def get(self, url, **kw):
                outer.calls.append(('GET', url))
                if url.endswith('/login'):
                    return Response(200, url, '<input type="hidden" name="csrf_token" value="tok">')
                return Response(200, url, 'page')

            def post(self, url, data=None, **kw):
                outer.calls.append(('POST', url, sorted(data)))
                return Response(200, url.replace('/login', '/selection/'))
        self.Session = Session

    def get(self, url, **kw):
        self.calls.append(('GET', url))
        return Response(302, url, location='https://rfone.example.test/login?next=/selection/')


def verifier():
    spec = importlib.util.spec_from_file_location('verify_http_release', HERE / 'verify_http_release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HttpVerifier(unittest.TestCase):
    def test_without_account_reports_not_verified(self):
        http = FakeHttp()
        report = verifier().verify('https://rfone.example.test', 7, http=http)
        self.assertTrue(report['anonymous_requires_login'])
        self.assertTrue(report['authenticated'].startswith('NOT VERIFIED'))
        self.assertEqual(report['status'], 'partial')
        self.assertEqual([c[0] for c in http.calls], ['GET'])

    def test_with_test_account_only_login_post_and_gets(self):
        http = FakeHttp()
        report = verifier().verify('https://rfone.example.test', 7, 'synthetic-test', 'synthetic-password', http=http)
        self.assertEqual(report['status'], 'passed')
        posts = [c for c in http.calls if c[0] == 'POST']
        self.assertEqual(posts, [('POST', 'https://rfone.example.test/login', ['csrf_token', 'next', 'password', 'username'])])
        self.assertFalse(report['secrets_read'] or report['session_signed_locally'] or report['writes_sent'])


class ForeignKeySession(unittest.TestCase):
    def test_cookie_signed_with_another_key_is_rejected(self):
        tmp = tempfile.mkdtemp(prefix='selection_session_test_')
        os.environ.update(RFONE_DATABASE_URL=f"sqlite:///{os.path.join(tmp, 'rfone.db').replace(os.sep, '/')}",
                          RFONE_SELECTION_UPLOAD_DIR=os.path.join(tmp, 'uploads'), RFONE_SELECTION_REQUIRE_RFONE_LOGIN='1',
                          RFONE_WEB_BASE_URL='https://rfone.example.test', RFONE_FLASK_SECRET_KEY='isolated-app-key')
        for name in ('RFONE_PUBLIC_BASE_URL', 'RFONE_SELECTION_DOCUMENT_BUCKET', 'RFONE_SELECTION_AI', 'RFONE_SELECTION_AI_CV'):
            os.environ.pop(name, None)
        sys.path[:0] = [str(APP), str(APP.parent / 'RF-One Data Store')]
        cwd = os.getcwd()
        os.chdir(APP)
        try:
            import app as selection_app
            from flask import Flask
            from workspace.schema import provision
            from rfone_data_store import rfone_account_service as accounts
            from rfone_data_store import rfone_web_session as shared
            provision(selection_app._engine)
            with selection_app.SessionFactory() as db:
                acc = accounts.create_account(db, username='admin', display_name='Synthetic Admin',
                                              password='synthetic-password-1', is_admin=True)
                accounts.set_domain_access(db, account_id=acc.id, domain_code='SELECTION', enabled=True, role_code=None)
                db.commit()
                account = (acc.id, acc.session_version)
            forger = Flask('foreign');forger.secret_key = 'a-different-key'
            cookie = forger.session_interface.get_signing_serializer(forger).dumps(
                {shared.SESSION_ACCOUNT_KEY: account[0], shared.SESSION_VERSION_KEY: account[1]})
            client = selection_app.app.test_client()
            client.set_cookie('session', cookie)
            response = client.get('/selection/')
            self.assertEqual(response.status_code, 302)
            self.assertIn('/login', response.headers['Location'])
            selection_app._engine.dispose()
        finally:
            os.chdir(cwd)
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
