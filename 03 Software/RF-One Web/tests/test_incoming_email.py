"""Disposable local tests. No real IMAP/SMTP calls or operational databases."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import imaplib
import importlib.util
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

WEB = Path(__file__).resolve().parents[1]
STORE = WEB.parent / 'RF-One Data Store'
sys.path[:0] = [str(WEB), str(STORE)]

from flask import Flask, abort, request, session
from sqlalchemy import select, func, text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from rfone_data_store import models as m, incoming_email as incoming, email_service as outgoing
from rfone_data_store import incoming_attachment_rules as attachment_rules
from rfone_data_store import rfone_web_session as identity, display_format
from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store.incoming_email_worker import check_one
from rfone_data_store.technical.imap_mailbox import Header, Snapshot, HeaderMailboxClient, MailboxError, public_address
from rfone_data_store.technical.mailbox_credentials import LocalMailboxVault, CredentialError
from incoming_email_routes import register_incoming_email_routes
from email_routes import register_email_routes


class MemoryVault:
    def __init__(self):
        self.values = {}

    def save(self, password):
        ref = 'local:' + uuid.uuid4().hex
        self.values[ref] = password
        return ref

    def load(self, ref):
        if ref not in self.values:
            raise CredentialError('CREDENTIALS_UNAVAILABLE')
        return self.values[ref]

    def delete(self, ref):
        self.values.pop(ref, None)


class FakeClient:
    def __init__(self, box, password, server):
        self.server = server
        self.server['opens'] = self.server.get('opens', 0) + 1

    def open(self):
        if self.server.get('failure'):
            raise self.server['failure']
        return Snapshot(self.server['validity'], self.server['next'])

    def headers_since(self, last_uid, snapshot):
        if self.server.get('on_fetch'):
            self.server['on_fetch']()
        if self.server.get('crash'):
            raise KeyboardInterrupt()
        return [h for h in self.server['headers'] if last_uid < h.uid < snapshot.uidnext][:20]

    def attachments_for(self, uid):
        return (), None

    def verify(self, snapshot):
        if self.server.get('verify_failure'):
            raise MailboxError('IMAP_FAILED')

    def close(self):
        pass


class IncomingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rfone_test_incoming_')
        self.path = Path(self.temp.name) / 'mail.db'
        self.engine = create_configured_engine('sqlite:///' + self.path.as_posix(), sqlite_immediate=True)
        m.Base.metadata.create_all(self.engine, tables=[m.RFOneAccount.__table__, m.RFOneAccountDomainAccess.__table__,
            m.EmployeeContextLink.__table__, m.RFOneTrainingIdentityLink.__table__, m.RFOneAccountDomainItemAccess.__table__]
            + outgoing.TABLES + incoming.TABLES + attachment_rules.TABLES)
        self.factory = create_session_factory(self.engine)
        with self.factory.begin() as db:
            for account_id in (1, 2):
                db.add(m.RFOneAccount(id=account_id, username='user'+str(account_id), display_name='Local User',
                                     password_hash='unused-test', is_admin=account_id == 1))
            for worker_id in (1, 2):
                db.add(outgoing.EmailWorkerState(id=worker_id, lease_until=outgoing.now(), next_send_at=outgoing.now()))
        self.vault = MemoryVault()
        self.app = Flask(__name__, template_folder=str(WEB / 'templates'), static_folder=str(WEB / 'static'))
        self.app.secret_key = 'local-incoming-test-only'
        self.app.config['TESTING'] = True
        self.app.add_url_rule('/', 'home', lambda: 'RF-One')
        self.app.jinja_env.filters['local_dt'] = display_format.local_datetime
        self.app.context_processor(lambda: {'csrf_token': lambda: 'csrf'})

        def load(db):
            return identity.account_for_session(db, account_id=session.get(identity.SESSION_ACCOUNT_KEY),
                session_version=session.get(identity.SESSION_VERSION_KEY))

        def csrf():
            if request.form.get('csrf_token') != session.get(identity.SESSION_CSRF_KEY):
                abort(400)

        kwargs = dict(SessionFactory=self.factory, load_current_account=load, require_csrf=csrf,
                      get_timezone=lambda: 'America/New_York')
        register_email_routes(self.app, **kwargs)
        register_incoming_email_routes(self.app, vault=self.vault, **kwargs)
        self.client = self.app.test_client()
        self.login(1)
        self.stamp = outgoing.now() + timedelta(seconds=1)
        self.server = dict(validity='100', next=11, headers=[])

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def login(self, account_id):
        with self.client.session_transaction() as s:
            s[identity.SESSION_ACCOUNT_KEY] = account_id
            s[identity.SESSION_VERSION_KEY] = 1
            s[identity.SESSION_CSRF_KEY] = 'csrf'

    def add(self, owner=1, label='Applications', username='mail@example.test'):
        with self.factory.begin() as db:
            box = incoming.configure(db, owner=owner, credential_ref=self.vault.save('not-a-real-password'),
                label=label, address='mail@example.test', host='imaps.aruba.it', username=username, folder='INBOX', interval_seconds=60)
            return box.id

    def box(self, mailbox_id):
        with self.factory() as db:
            return db.get(incoming.Mailbox, mailbox_id)

    def poll(self, seconds=0):
        self.stamp += timedelta(seconds=seconds)
        return check_one(self.factory, self.vault, clock=lambda: self.stamp,
                         client_factory=lambda box, password: FakeClient(box, password, self.server))

    def count(self, model=incoming.Arrival):
        with self.factory() as db:
            return db.scalar(select(func.count()).select_from(model))

    def headers(self, *uids):
        self.server['next'] = max(uids) + 1
        self.server['headers'] = [Header(uid, 'Sender <s@example.test>', 'mail@example.test', 'New CV '+str(uid),
            '<'+str(uid)+'@example.test>', outgoing.now(), 450) for uid in uids]

    def test_first_check_baselines_without_importing_old_mail(self):
        bid = self.add()
        self.headers(1, 5, 10)
        self.assertTrue(self.poll())
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.box(bid).last_uid, 10)
        self.assertEqual(self.box(bid).uidvalidity, '100')

    def test_new_arrivals_persist_and_replay_deduplicates(self):
        bid = self.add(); self.poll(); self.headers(11, 12)
        self.poll(61)
        self.assertEqual(self.count(), 2)
        with self.factory.begin() as db:
            db.get(incoming.Mailbox, bid).last_uid = 10
        self.poll(61)
        self.assertEqual(self.count(), 2)
        self.assertEqual(self.box(bid).last_uid, 12)

    def test_batch_checkpoint_does_not_skip_backlog(self):
        bid = self.add(); self.poll(); self.headers(*range(11, 56))
        self.poll(61)
        self.assertEqual(self.count(), 20)
        self.assertEqual(self.box(bid).last_uid, 30)
        self.poll(2); self.poll(2)
        self.assertEqual(self.count(), 45)
        self.assertEqual(self.box(bid).last_uid, 55)

    def test_uidvalidity_change_starts_new_baseline(self):
        bid = self.add(); self.poll(); self.headers(11); self.poll(61)
        self.server['validity'] = '200'; self.headers(1, 2)
        self.poll(61)
        self.assertEqual(self.count(), 1)
        self.assertEqual(self.box(bid).last_error, 'UIDVALIDITY_CHANGED')
        self.headers(3); self.poll(61)
        self.assertEqual(self.count(), 2)

    def test_identity_changes_use_a_new_generation(self):
        bid = self.add(); self.poll(); self.headers(11); self.poll(61)
        with self.factory.begin() as db:
            incoming.configure(db, owner=1, mailbox_id=bid, label='Archive', address='mail@example.test',
                host='imaps.aruba.it', username='mail@example.test', folder='Archive', interval_seconds=60)
        self.server['next'] = 11; self.server['headers'] = []
        self.poll(61); self.headers(11); self.poll(61)
        self.assertEqual(self.count(), 2)
        self.assertEqual(self.box(bid).generation, 2)

    def test_failure_does_not_advance_cursor_and_is_sanitized(self):
        bid = self.add(); self.poll(); self.headers(11)
        self.server['failure'] = RuntimeError('password-sensitive-provider-reply')
        self.poll(61)
        box = self.box(bid)
        self.assertEqual(box.last_uid, 10)
        self.assertEqual(box.last_error, 'IMAP_FAILED')
        self.assertGreater(box.next_check_at.replace(tzinfo=self.stamp.tzinfo), self.stamp)
        self.server.pop('failure'); self.poll(121)
        self.assertEqual(self.count(), 1)

    def test_changed_validity_during_fetch_discards_batch(self):
        bid = self.add(); self.poll(); self.headers(11)
        self.server['verify_failure'] = True; self.poll(61)
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.box(bid).last_uid, 10)

    def test_pause_during_check_fences_stale_results(self):
        bid = self.add(); self.poll(); self.headers(11)
        def pause():
            with self.factory.begin() as db:
                incoming.control(db, owner=1, mailbox_id=bid, action='pause')
        self.server['on_fetch'] = pause
        self.poll(61)
        self.assertFalse(self.box(bid).enabled)
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.box(bid).last_uid, 10)
        self.server.pop('on_fetch')
        with self.factory.begin() as db:
            incoming.control(db, owner=1, mailbox_id=bid, action='resume')
        self.poll(1)
        self.assertEqual(self.count(), 1)

    def test_crash_and_restart_recover_after_lease(self):
        bid = self.add(); self.poll(); self.headers(11)
        self.server['crash'] = True
        with self.assertRaises(KeyboardInterrupt):
            self.poll(61)
        self.assertFalse(self.poll(1))
        self.server.pop('crash'); self.poll(301)
        self.assertEqual(self.count(), 1)
        self.assertEqual(self.box(bid).last_uid, 11)
        with self.factory() as db:
            self.assertIn('INTERRUPTED', list(db.scalars(select(incoming.MailboxCheck.outcome))))

    def test_concurrent_workers_claim_only_once(self):
        self.add()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.poll(), range(2)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(self.server['opens'], 1)

    def test_inactive_owner_is_not_polled(self):
        self.add(owner=2)
        with self.factory.begin() as db:
            db.get(m.RFOneAccount, 2).status = 'INACTIVE'
        self.assertFalse(self.poll())

    def test_missing_credentials_record_fixed_category(self):
        bid = self.add(); self.vault.values.clear(); self.poll()
        self.assertEqual(self.box(bid).last_error, 'CREDENTIALS_UNAVAILABLE')

    def test_revoked_canonical_owner_stops_monitoring_before_credentials_are_read(self):
        bid = self.add()
        with patch('rfone_data_store.incoming_email_worker.identity.account_for_session', return_value=None):
            self.assertTrue(self.poll())
        self.assertFalse(self.box(bid).enabled)
        self.assertEqual(self.box(bid).last_error, 'OWNER_INACTIVE')
        self.assertEqual(self.server.get('opens', 0), 0)

    def test_server_change_cannot_redirect_saved_password(self):
        bid = self.add()
        with self.factory.begin() as db:
            with self.assertRaises(ValueError):
                incoming.configure(db, owner=1, mailbox_id=bid, label='Applications', address='mail@example.test',
                    host='other-provider.example.test', username='mail@example.test', folder='INBOX', interval_seconds=60)
        self.assertEqual(self.box(bid).host, 'imaps.aruba.it')

    def test_regular_user_can_configure_without_access_to_others(self):
        hidden = self.add(); self.login(2)
        data = dict(label='My box', address='me@example.test', host='imaps.aruba.it', username='me@example.test',
                    folder='INBOX', interval_seconds='60', password='private-test-secret', csrf_token='csrf')
        result = self.client.post('/administration/email/mailboxes/new', data=data)
        self.assertEqual(result.status_code, 302)
        page = self.client.get('/administration/email/mailboxes').get_data(as_text=True)
        self.assertIn('My box', page)
        self.assertNotIn('Applications', page)
        self.assertNotIn('private-test-secret', page)
        self.assertNotIn(b'private-test-secret', self.path.read_bytes())
        self.assertEqual(self.client.get(f'/administration/email/mailboxes/{hidden}/edit').status_code, 404)
        self.assertEqual(self.client.get(f'/administration/email/mailboxes/{hidden}/checks').status_code, 404)
        self.assertEqual(self.client.post(f'/administration/email/mailboxes/{hidden}/pause', data={'csrf_token':'csrf'}).status_code, 404)
        self.assertEqual(self.client.get('/administration/email/incoming?mailbox='+hidden).status_code, 404)
        self.assertEqual(self.client.get('/administration/email').status_code, 403)

    def test_mailbox_forms_csrf_revocation_and_failed_save_cleanup(self):
        self.assertEqual(self.client.post('/administration/email/mailboxes/new', data={}).status_code, 400)
        data = dict(label='Box', address='me@example.test', host='imaps.aruba.it', username='me@example.test',
                    folder='INBOX', interval_seconds='60', password='not-for-html', csrf_token='csrf')
        self.client.post('/administration/email/mailboxes/new', data=data)
        before = len(self.vault.values)
        failed = self.client.post('/administration/email/mailboxes/new', data=data)
        self.assertEqual(failed.status_code, 400)
        self.assertEqual(len(self.vault.values), before)
        self.assertNotIn('not-for-html', failed.get_data(as_text=True))
        with self.factory.begin() as db:
            db.get(m.RFOneAccount, 1).session_version += 1
        self.assertEqual(self.client.get('/administration/email/mailboxes').status_code, 401)

    def test_save_and_pause_operations_are_audited(self):
        bid = self.add()
        self.client.post(f'/administration/email/mailboxes/{bid}/pause', data={'csrf_token':'csrf'})
        self.assertFalse(self.poll())
        self.client.post(f'/administration/email/mailboxes/{bid}/resume', data={'csrf_token':'csrf'})
        self.client.post(f'/administration/email/mailboxes/{bid}/check', data={'csrf_token':'csrf'})
        with self.factory() as db:
            actions = list(db.scalars(select(incoming.MailboxAudit.action).order_by(incoming.MailboxAudit.id)))
        self.assertEqual(actions, ['CREATE', 'PAUSE', 'RESUME', 'CHECK'])

    def test_arrival_rendering_is_scoped_escaped_and_has_no_body(self):
        bid = self.add(); self.poll(); self.headers(11)
        h = self.server['headers'][0]
        self.server['headers'] = [Header(h.uid, '<script>bad</script>', h.recipient, '<b>CV</b>', None, None, 0)]
        self.poll(61)
        page = self.client.get('/administration/email/incoming').get_data(as_text=True)
        self.assertIn('&lt;b&gt;CV&lt;/b&gt;', page)
        self.assertNotIn('<script>bad</script>', page)
        self.login(2)
        self.assertNotIn('CV', self.client.get('/administration/email/incoming').get_data(as_text=True))
        self.assertNotIn('body', incoming.Arrival.__table__.columns)

    def test_editing_password_rotates_opaque_reference(self):
        bid = self.add(); old = self.box(bid).credential_ref
        data = dict(label='Applications', address='mail@example.test', host='imaps.aruba.it', username='mail@example.test',
                    folder='INBOX', interval_seconds='120', password='replacement-secret', csrf_token='csrf')
        self.assertEqual(self.client.post(f'/administration/email/mailboxes/{bid}/edit', data=data).status_code, 302)
        new = self.box(bid).credential_ref
        self.assertNotEqual(new, old)
        self.assertNotIn(old, self.vault.values)
        self.assertEqual(self.vault.load(new), 'replacement-secret')

    def test_worker_dry_run_does_not_connect(self):
        self.add()
        result = subprocess.run([sys.executable, '-B', '-m', 'rfone_data_store.incoming_email_worker',
            '--database-url', str(self.engine.url), '--once'], cwd=STORE, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('no mailbox connections', result.stdout)
        self.assertEqual(self.count(incoming.MailboxCheck), 0)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.commands = []
        self.box = type('Box', (), dict(host='imaps.aruba.it', username='test@example.test', folder='INBOX'))()
        outer = self
        class Connection:
            def login(self, *args): outer.commands.append(('login',))
            def select(self, folder, readonly): outer.commands.append(('select', folder, readonly)); return 'OK', [b'12']
            def status(self, *args): return 'OK', [b'"INBOX" (UIDVALIDITY 100 UIDNEXT 13)']
            def uid(self, command, *args):
                outer.commands.append((command, *args))
                if command == 'search': return 'OK', [b'1 10 11 12']
                uid = int(args[0])
                raw = b'From: Sender <s@example.test>\r\nTo: r@example.test\r\nSubject: =?utf-8?q?CV_ricevuto?=\r\nDate: Tue, 17 Nov 2026 10:00:00 -0500\r\nMessage-ID: <x@example.test>\r\n\r\n'
                prefix = (f'1 (UID {uid} RFC822.SIZE 400 BODYSTRUCTURE ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 20 1) '
                          f'BODY[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID)]<0> {{{len(raw)}}}').encode()
                return 'OK', [(prefix, raw), b')']
            def logout(self): outer.commands.append(('logout',))
        self.connection = Connection()
        def factory(host, address, context):
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
            return self.connection
        self.client = HeaderMailboxClient(self.box, 'not-real', resolver=lambda host:'93.184.216.34', factory=factory)

    def test_readonly_header_peek_and_uid_filter(self):
        snapshot = self.client.open()
        headers = self.client.headers_since(10, snapshot)
        self.client.verify(snapshot); self.client.close()
        self.assertEqual([h.uid for h in headers], [11, 12])
        self.assertEqual(headers[0].subject, 'CV ricevuto')
        self.assertIn(('select', '"INBOX"', True), self.commands)
        fetch = [c for c in self.commands if c[0] == 'fetch']
        self.assertTrue(all('BODY.PEEK[HEADER.FIELDS' in c[2] and '<0.65536>' in c[2] for c in fetch))
        self.assertTrue(all('RFC822)' not in c[2] and 'TEXT' not in c[2] for c in fetch))
        self.assertNotIn('store', [c[0] for c in self.commands])

    def test_login_failure_is_sanitized(self):
        self.connection.login = lambda *args: (_ for _ in ()).throw(imaplib.IMAP4.error('password not-real'))
        with self.assertRaises(MailboxError) as exc:
            self.client.open()
        self.assertEqual(str(exc.exception), 'AUTHENTICATION_FAILED')

    def test_private_and_rebound_addresses_are_rejected(self):
        for ip in ['127.0.0.1', '169.254.169.254', '10.0.0.1', '::1']:
            with patch('socket.getaddrinfo', return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,993))]):
                with self.assertRaises(MailboxError) as exc:
                    public_address('private.test')
                self.assertEqual(str(exc.exception), 'UNSAFE_SERVER')


class VaultTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Local credential backend uses Windows DPAPI')
    def test_windows_dpapi_roundtrip_and_opaque_file(self):
        with tempfile.TemporaryDirectory(prefix='rfone_test_vault_') as directory:
            vault = LocalMailboxVault(directory)
            password = 'fake-mailbox-password-for-dpapi-test'
            ref = vault.save(password)
            self.assertEqual(vault.load(ref), password)
            self.assertNotIn(password.encode(), next(Path(directory).glob('*.dpapi')).read_bytes())
            with self.assertRaises(CredentialError): vault.load('local:../../private')
            vault.delete(ref)
            self.assertEqual(list(Path(directory).iterdir()), [])


class MigrationTests(unittest.TestCase):
    def test_frozen_migration_matches_models_and_roundtrips_empty_schema(self):
        path = STORE / 'migrations/versions/i9a120261117_incoming_email_monitoring.py'
        spec = importlib.util.spec_from_file_location('incoming_migration_test', path)
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        engine = create_configured_engine('sqlite://')
        m.Base.metadata.create_all(engine, tables=[m.RFOneAccount.__table__] + outgoing.TABLES)
        with engine.begin() as db:
            with Operations.context(MigrationContext.configure(db)):
                migration.upgrade()
            self.assertEqual(db.scalar(text('SELECT id FROM email_worker_state WHERE id=2')), 2)
            next_spec = importlib.util.spec_from_file_location('attachment_migration_test', STORE / 'migrations/versions/i9b120261117_incoming_attachment_metadata.py')
            attachment_migration = importlib.util.module_from_spec(next_spec); next_spec.loader.exec_module(attachment_migration)
            with Operations.context(MigrationContext.configure(db)):
                attachment_migration.upgrade()
            for table in incoming.TABLES:
                columns = {r[1] for r in db.execute(text('PRAGMA table_info('+table.name+')'))}
                self.assertEqual(columns, set(table.c.keys()))
            with Operations.context(MigrationContext.configure(db)):
                attachment_migration.downgrade()
                migration.downgrade()
            self.assertIsNone(db.scalar(text('SELECT id FROM email_worker_state WHERE id=2')))
        engine.dispose()


class LocalRunnerTests(unittest.TestCase):
    def test_private_local_app_has_no_login_but_keeps_csrf_and_host_checks(self):
        from run_email_control_local import prepare_database, make_app
        with tempfile.TemporaryDirectory(prefix='rfone_test_local_mail_') as directory:
            engine = prepare_database(Path(directory) / 'private.db')
            try:
                client = make_app(engine).test_client()
                self.assertEqual(client.get('/administration/email/mailboxes').status_code, 200)
                self.assertEqual(client.post('/administration/email/mailboxes/new', data={}).status_code, 400)
                self.assertEqual(client.get('/administration/email/mailboxes', headers={'Host':'untrusted.example'}).status_code, 400)
            finally:
                engine.dispose()

    def test_local_launcher_refuses_unrelated_database_without_changing_it(self):
        from run_email_control_local import prepare_database
        with tempfile.TemporaryDirectory(prefix='rfone_test_db_guard_') as directory:
            path = Path(directory) / 'existing.db'
            engine = create_configured_engine('sqlite:///' + path.as_posix(), sqlite_immediate=True)
            with engine.begin() as db:
                db.execute(text('CREATE TABLE important_data (id INTEGER PRIMARY KEY)'))
                db.execute(text('INSERT INTO important_data VALUES (42)'))
            engine.dispose()
            with self.assertRaises(RuntimeError):
                prepare_database(path)
            engine = create_configured_engine('sqlite:///' + path.as_posix(), sqlite_immediate=True)
            try:
                with engine.connect() as db:
                    self.assertEqual(db.scalar(text('SELECT id FROM important_data')), 42)
                    self.assertEqual(db.scalar(text("SELECT count(*) FROM sqlite_master WHERE name='email_mailboxes'")), 0)
            finally:
                engine.dispose()


if __name__ == '__main__':
    unittest.main()
