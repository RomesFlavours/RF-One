"""Isolated local integration tests: never resolve .env or send real email."""
import sys
from pathlib import Path
import tempfile
import unittest
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import smtplib
import subprocess

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB))
sys.path.insert(0, str(WEB.parent / 'RF-One Data Store'))

from flask import Flask, session
from sqlalchemy import select, update
from rfone_data_store import models as m, email_service as e, rfone_web_session as identity
from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store.email_worker import run_once, LEASE_SECONDS
from rfone_data_store.technical.aruba_smtp import ArubaSMTP, SendFailure, load_secret
from email_routes import register_email_routes


class FakeTransport:
    def __init__(self, failure=None):
        self.failure, self.sent = failure, []

    def send(self, row):
        self.sent.append(row.id)
        if self.failure:
            raise self.failure


class EmailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rfone_test_email_')
        self.engine = create_configured_engine('sqlite:///' + str(Path(self.temp.name) / 'queue.db').replace('\\', '/'))
        m.Base.metadata.create_all(self.engine, tables=[m.RFOneAccount.__table__, m.RFOneAccountDomainAccess.__table__,
            m.EmployeeContextLink.__table__, m.RFOneTrainingIdentityLink.__table__,
            m.RFOneAccountDomainItemAccess.__table__] + e.TABLES)
        self.factory = create_session_factory(self.engine)
        self.stamp = e.now()
        with self.factory.begin() as db:
            db.add(e.EmailWorkerState(id=1, lease_until=self.stamp, next_send_at=self.stamp))
            db.add(m.RFOneAccount(id=1, username='local', display_name='Local', password_hash='unused', is_admin=True))
            db.add(m.RFOneAccount(id=2, username='domain', display_name='Domain', password_hash='unused', is_admin=False))
            db.flush()
            for account_id in (1, 2):
                db.add(m.RFOneAccountDomainAccess(account_id=account_id, domain_code='TRAINING', enabled=True))
        self.transport = FakeTransport()
        self.app = Flask(__name__, template_folder=str(WEB / 'templates'))
        self.app.secret_key = 'local-test-only'
        self.app.config['TESTING'] = True
        self.app.jinja_env.filters['local_dt'] = lambda value, tz=None: str(value)
        self.app.add_url_rule('/', 'home', lambda: 'home')
        self.app.context_processor(lambda: {'csrf_token': lambda: 'csrf', 'tz': None})
        register_email_routes(self.app, SessionFactory=self.factory,
            load_current_account=lambda db: identity.account_for_session(db, account_id=session.get('rfone_account_id'),
                session_version=session.get('rfone_session_version')),
            require_csrf=lambda: None)
        self.client = self.app.test_client()
        self.login(1)

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def login(self, account_id):
        with self.client.session_transaction() as s:
            s['rfone_account_id'] = account_id
            s['rfone_session_version'] = 1
            s['rfone_csrf_token'] = 'csrf'

    def enqueue(self, domain='TRAINING', key='event-1'):
        with self.factory.begin() as db:
            row = e.enqueue(db, domain=domain, recipient='recipient@example.test', subject='Test', body='Local test', event='test', dedup_key=key)
            db.flush()
            return row.id

    def row(self, request_id):
        with self.factory() as db:
            return db.get(e.EmailRequest, request_id)

    def tick(self, seconds=1, transport=None):
        self.stamp += timedelta(seconds=seconds)
        return run_once(self.factory, transport or self.transport, clock=lambda: self.stamp)

    def test_enqueue_acceptance_and_history(self):
        rid = self.enqueue()
        self.assertTrue(self.tick())
        self.assertEqual(self.row(rid).status, 'ACCEPTED')
        self.assertEqual(self.row(rid).attempts, 1)
        with self.factory() as db:
            self.assertEqual(len(e.history(db, domain='TRAINING')), 1)
            self.assertEqual(db.scalar(select(e.EmailAttempt)).outcome, 'ACCEPTED')

    def test_duplicate_and_payload_conflict(self):
        rid = self.enqueue()
        self.assertEqual(self.enqueue(), rid)
        with self.factory.begin() as db:
            with self.assertRaises(ValueError):
                e.enqueue(db, domain='TRAINING', recipient='other@example.test', subject='Test', body='Local test', event='test', dedup_key='event-1')

    def test_domain_isolation_and_parallel_domains(self):
        a, b = self.enqueue(), self.enqueue(domain='SELECTION')
        with self.factory() as db:
            self.assertIsNone(e.get(db, 'SELECTION', a))
        self.tick()
        self.tick(3)
        self.assertEqual({self.row(a).status, self.row(b).status}, {'ACCEPTED'})

    def test_temporary_retry_and_restart(self):
        rid = self.enqueue()
        self.tick(transport=FakeTransport(SendFailure('SMTP_451', temporary=True)))
        self.assertEqual(self.row(rid).status, 'RETRY')
        self.assertFalse(self.tick(3))
        self.tick(30)
        self.assertEqual(self.row(rid).status, 'ACCEPTED')
        self.assertEqual(self.row(rid).attempts, 2)

    def test_permanent_failure_manual_resend_audited(self):
        rid = self.enqueue()
        self.tick(transport=FakeTransport(SendFailure('SMTP_550')))
        self.assertEqual(self.row(rid).status, 'FAILED')
        with self.factory.begin() as db:
            e.transition(db, domain='TRAINING', request_id=rid, action='resend', actor_account_id=1)
        self.tick(3)
        self.assertEqual(self.row(rid).status, 'ACCEPTED')
        with self.factory() as db:
            self.assertEqual(db.scalar(select(e.EmailAudit)).action, 'resend')

    def test_uncertain_never_retried(self):
        rid = self.enqueue()
        self.tick(transport=FakeTransport(SendFailure('SMTP_CONNECTION', uncertain=True)))
        self.assertEqual(self.row(rid).status, 'UNCERTAIN')
        self.assertFalse(self.tick(400))
        with self.factory.begin() as db:
            with self.assertRaises(ValueError):
                e.transition(db, domain='TRAINING', request_id=rid, action='resend', actor_account_id=1)

    def test_worker_crash_recovery(self):
        rid = self.enqueue()
        class Crash:
            def send(self, row):
                raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.tick(transport=Crash())
        self.assertEqual(self.row(rid).status, 'SENDING')
        self.assertFalse(self.tick(2))
        self.tick(LEASE_SECONDS + 1)
        self.assertEqual(self.row(rid).status, 'UNCERTAIN')

    def test_cancel_is_atomic_and_audited(self):
        rid = self.enqueue()
        with self.factory.begin() as db:
            e.transition(db, domain='TRAINING', request_id=rid, action='cancel', actor_account_id=1)
        self.assertFalse(self.tick())
        self.assertEqual(self.row(rid).status, 'CANCELLED')

    def test_global_rate_limit(self):
        self.enqueue()
        self.enqueue(key='event-2')
        self.tick()
        self.assertFalse(self.tick(1))
        self.assertTrue(self.tick(2))

    def test_retry_exhaustion(self):
        rid = self.enqueue()
        failing = FakeTransport(SendFailure('SMTP_451', temporary=True))
        for _ in range(5):
            self.tick(4000, transport=failing)
        self.assertEqual(self.row(rid).status, 'FAILED')
        self.assertEqual(self.row(rid).attempts, 5)
        self.assertFalse(self.tick(4000))

    def test_header_injection_rejected(self):
        with self.factory.begin() as db:
            with self.assertRaises(ValueError):
                e.enqueue(db, domain='TRAINING', recipient='r@example.test\r\nBcc: x@example.test',
                          subject='test', body='test', event='test', dedup_key='attack')

    def test_worker_cli_dry_run_does_not_consume(self):
        rid = self.enqueue()
        result = subprocess.run([sys.executable, '-m', 'rfone_data_store.email_worker',
            '--database-url', str(self.engine.url), '--once'], cwd=WEB.parent / 'RF-One Data Store',
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('dry-run', result.stdout)
        self.assertEqual(self.row(rid).status, 'QUEUED')

    def test_concurrent_workers_send_once(self):
        rid = self.enqueue()
        self.stamp += timedelta(seconds=1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: run_once(self.factory, self.transport, clock=lambda: self.stamp), range(2)))
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(self.transport.sent, [rid])

    def test_concurrent_enqueue_deduplicates(self):
        # SQLite serializes writers; use independent transactions on the same key.
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.enqueue(), range(2)))
        self.assertEqual(results[0], results[1])

    def test_api_authorization_csrf_and_domain_boundaries(self):
        rid = self.enqueue()
        self.login(2)
        self.assertEqual(self.client.get('/administration/email').status_code, 403)
        self.assertEqual(self.client.get(f'/api/email/SELECTION/requests/{rid}').status_code, 403)
        self.assertEqual(self.client.post(f'/api/email/TRAINING/requests/{rid}/resend').status_code, 403)
        self.assertEqual(self.client.post('/api/email/TRAINING/requests', json={}).status_code, 400)
        self.assertEqual(self.client.get(f'/api/email/TRAINING/requests/{rid}').status_code, 200)
        with self.factory.begin() as db:
            db.get(m.RFOneAccount, 2).session_version = 2
        self.assertEqual(self.client.get('/api/email/TRAINING/requests').status_code, 401)

    def test_http_enqueue_and_control_templates(self):
        response = self.client.post('/api/email/TRAINING/requests', json=dict(recipient='r@example.test', subject='Test',
            body='Confidential body', event='event', dedup_key='http'), headers={'X-CSRF-Token': 'csrf'})
        self.assertEqual(response.status_code, 202)
        data = response.get_json()
        self.assertNotIn('body', data)
        self.assertEqual(self.client.get('/administration/email').status_code, 200)
        self.assertEqual(self.client.get(f"/administration/email/TRAINING/{data['id']}").status_code, 200)
        self.assertEqual(self.client.get('/administration/email?start=bad').status_code, 400)


class FakeSMTP:
    phase, code = None, 250
    def __init__(self, *args, **kwargs):
        if self.phase == 'connect':
            raise TimeoutError('sensitive info')
    def ehlo(self): pass
    def login(self, *args): pass
    def mail(self, *args): return 250, b'ok'
    def rcpt(self, *args): return 250, b'ok'
    def data(self, *args):
        if self.phase == 'data':
            raise smtplib.SMTPServerDisconnected('sensitive info')
        return self.code, b'sensitive remote reply'
    def close(self): pass


class TransportTests(unittest.TestCase):
    def setUp(self):
        FakeSMTP.phase, FakeSMTP.code = None, 250
        self.config = dict(host='smtps.aruba.it', port=465, username='test', password='private', from_address='sender@example.test')
        self.row = e.EmailRequest(id='test', recipient='r@example.test', subject='test', body='test')

    def test_aruba_tls_acceptance(self):
        ArubaSMTP(self.config, FakeSMTP).send(self.row)

    def test_temporary_and_permanent_smtp_replies(self):
        for code in (451, 550):
            FakeSMTP.code = code
            with self.assertRaises(SendFailure) as caught:
                ArubaSMTP(self.config, FakeSMTP).send(self.row)
            self.assertEqual(caught.exception.temporary, code == 451)
            self.assertFalse(caught.exception.uncertain)
            self.assertNotIn('sensitive', str(caught.exception))

    def test_connection_vs_data_uncertainty(self):
        for phase in ('connect', 'data'):
            FakeSMTP.phase = phase
            with self.assertRaises(SendFailure) as caught:
                ArubaSMTP(self.config, FakeSMTP).send(self.row)
            self.assertEqual(caught.exception.uncertain, phase == 'data')
            self.assertNotIn('sensitive', str(caught.exception))

    def test_secret_failure_is_sanitized(self):
        with patch('boto3.client', side_effect=RuntimeError('private-token')):
            with self.assertRaises(SendFailure) as caught:
                load_secret('test-secret', 'us-east-1')
        self.assertEqual(str(caught.exception), 'SMTP_CONFIGURATION')


if __name__ == '__main__':
    unittest.main()
