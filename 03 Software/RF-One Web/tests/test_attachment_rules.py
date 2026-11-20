"""Attachment rules per mailbox: configuration only. Disposable DBs, no AI or network calls."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import uuid

WEB = Path(__file__).resolve().parents[1]
STORE = WEB.parent / 'RF-One Data Store'
sys.path[:0] = [str(WEB), str(STORE)]

from flask import Flask, abort, request, session
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from rfone_data_store import models as m, incoming_email as incoming, email_service as outgoing
from rfone_data_store import incoming_attachment_rules as rules
from rfone_data_store import rfone_web_session as identity, display_format
from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store.selection.parsing import ai_client
from incoming_email_routes import register_incoming_email_routes
from email_routes import register_email_routes
from run_email_control_local import prepare_database, upgrade_database, _apply_local_migration, SANDBOX_VERSION


class Vault:
    def __init__(self):
        self.loads = 0

    def save(self, password):
        return 'local:' + uuid.uuid4().hex

    def load(self, ref):
        self.loads += 1
        raise AssertionError('Credentials must not be read by attachment rules.')

    def delete(self, ref):
        pass


class AttachmentRuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rfone_test_rules_')
        self.engine = create_configured_engine('sqlite:///' + (Path(self.temp.name) / 'mail.db').as_posix(), sqlite_immediate=True)
        m.Base.metadata.create_all(self.engine, tables=[m.RFOneAccount.__table__, m.RFOneAccountDomainAccess.__table__,
            m.EmployeeContextLink.__table__, m.RFOneTrainingIdentityLink.__table__, m.RFOneAccountDomainItemAccess.__table__]
            + outgoing.TABLES + incoming.TABLES + rules.TABLES)
        self.factory = create_session_factory(self.engine)
        with self.factory.begin() as db:
            for account_id in (1, 2):
                db.add(m.RFOneAccount(id=account_id, username='user' + str(account_id), display_name='Local User',
                                     password_hash='unused-test', is_admin=account_id == 1))
            for worker_id in (1, 2):
                db.add(outgoing.EmailWorkerState(id=worker_id, lease_until=outgoing.now(), next_send_at=outgoing.now()))
        self.vault = Vault()
        self.calls = []
        self.assistant = self.fake_assistant
        self.ai = (True, 'TEST')
        app = Flask(__name__, template_folder=str(WEB / 'templates'), static_folder=str(WEB / 'static'))
        app.secret_key = 'local-rules-test-only'
        app.config['TESTING'] = True
        app.add_url_rule('/', 'home', lambda: 'RF-One')
        app.jinja_env.filters['local_dt'] = display_format.local_datetime
        app.context_processor(lambda: {'csrf_token': lambda: 'csrf'})

        def load(db):
            return identity.account_for_session(db, account_id=session.get(identity.SESSION_ACCOUNT_KEY),
                session_version=session.get(identity.SESSION_VERSION_KEY))

        def csrf():
            if request.form.get('csrf_token') != session.get(identity.SESSION_CSRF_KEY):
                abort(400)

        kwargs = dict(SessionFactory=self.factory, load_current_account=load, require_csrf=csrf,
                      get_timezone=lambda: 'America/New_York')
        register_email_routes(app, **kwargs)
        register_incoming_email_routes(app, vault=self.vault, ai_status=lambda: self.ai,
            rule_assistant=lambda **kw: self.assistant(**kw), **kwargs)
        self.client = app.test_client()
        self.login(1)
        self.box1 = self.add(1, 'Fatture', 'office@example.test')
        self.box2 = self.add(2, 'Other', 'other@example.test')

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def fake_assistant(self, **kw):
        self.calls.append(kw)
        return {'reply': 'In quale cartella vuoi salvarli?',
                'rule': {'selection': 'PDF con "fattura" nel nome', 'conditions': '', 'actions': 'Salvarli',
                         'missing': 'Destinazione non indicata'}}

    def login(self, account_id):
        with self.client.session_transaction() as s:
            s[identity.SESSION_ACCOUNT_KEY] = account_id
            s[identity.SESSION_VERSION_KEY] = 1
            s[identity.SESSION_CSRF_KEY] = 'csrf'

    def add(self, owner, label, address):
        with self.factory.begin() as db:
            return incoming.configure(db, owner=owner, credential_ref=self.vault.save('x'), label=label,
                address=address, host='imaps.aruba.it', username=address, folder='INBOX', interval_seconds=60).id

    def rule(self, mailbox_id):
        with self.factory() as db:
            return db.get(rules.AttachmentRule, mailbox_id)

    def save(self, mailbox_id, token='csrf', **values):
        data = dict(csrf_token=token, instructions='Salva le fatture PDF', selection='PDF fatture',
                    conditions='Mittente fornitore', actions='Salvarli', missing='')
        data.update(values)
        return self.client.post(f'/administration/email/mailboxes/{mailbox_id}/attachment-rule', data=data)

    def assist(self, mailbox_id, token='csrf', **extra):
        data = dict(csrf_token=token, message='Voglio salvare le fatture PDF', history='[]', instructions='', selection='',
                    conditions='', actions='', missing='')
        data.update(extra)
        return self.client.post(f'/administration/email/mailboxes/{mailbox_id}/attachment-rule/assist', data=data)

    # -- Owner isolation ------------------------------------------------------
    def test_owner_isolation(self):
        self.assertEqual(self.save(self.box1).status_code, 302)
        self.login(2)
        self.assertEqual(self.save(self.box1, actions='Altro').status_code, 404)
        self.assertEqual(self.assist(self.box1).status_code, 404)
        self.assertEqual(self.calls, [])
        page = self.client.get('/administration/email/mailboxes').get_data(as_text=True)
        self.assertNotIn('Mittente fornitore', page)
        self.assertNotIn('rule-' + self.box1, page)
        self.assertIn('rule-' + self.box2, page)
        self.assertEqual(self.rule(self.box1).actions, 'Salvarli')
        self.assertEqual(self.save('not-a-mailbox').status_code, 404)

    # -- CSRF -----------------------------------------------------------------
    def test_csrf_required_for_save_and_assist(self):
        self.assertEqual(self.save(self.box1, token='wrong').status_code, 400)
        self.assertEqual(self.client.post(f'/administration/email/mailboxes/{self.box1}/attachment-rule',
                                          data=dict(actions='x')).status_code, 400)
        self.assertIsNone(self.rule(self.box1))
        self.assertEqual(self.assist(self.box1, token='wrong').status_code, 400)
        self.assertEqual(self.calls, [])

    # -- Save and reopen ------------------------------------------------------
    def test_save_and_reopen(self):
        response = self.save(self.box1)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('#mailbox-' + self.box1))
        page = self.client.get('/administration/email/mailboxes').get_data(as_text=True)
        self.assertIn('Regole allegati', page)
        self.assertIn('Casella: Fatture', page)
        self.assertIn('Regola salvata · versione 1', page)
        self.assertIn('>Mittente fornitore</textarea>', page)
        self.save(self.box1, actions='Salvarli in archivio')
        row = self.rule(self.box1)
        self.assertEqual((row.version, row.actions, row.mailbox_id), (2, 'Salvarli in archivio', self.box1))
        with self.factory() as db:
            audit = [a.action for a in db.scalars(select(incoming.MailboxAudit).where(
                incoming.MailboxAudit.mailbox_id == self.box1).order_by(incoming.MailboxAudit.id))]
        self.assertEqual(audit, ['CREATE', 'ATTACHMENT_RULE_SAVE', 'ATTACHMENT_RULE_SAVE'])
        history = self.client.get(f'/administration/email/mailboxes/{self.box1}/checks').get_data(as_text=True)
        self.assertIn('Attachment rule saved (inactive)', history)

    def test_invalid_save_reopens_modal_with_unsaved_text(self):
        response = self.save(self.box1, instructions='', selection='', conditions='', actions='', missing='')
        self.assertEqual(response.status_code, 400)
        page = response.get_data(as_text=True)
        self.assertIn('data-rule-reopen', page)
        self.assertIn('Descrivi la regola', page)
        long = self.save(self.box1, actions='x' * (rules.FIELD_LIMIT + 1))
        self.assertEqual(long.status_code, 400)
        self.assertIsNone(self.rule(self.box1))

    def test_rule_text_is_escaped(self):
        self.save(self.box1, actions='<script>alert(1)</script>')
        page = self.client.get('/administration/email/mailboxes').get_data(as_text=True)
        self.assertNotIn('<script>alert(1)</script>', page)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', page)

    # -- AI draft separate from saved configuration ---------------------------
    def test_ai_answer_does_not_change_saved_rule(self):
        self.save(self.box1)
        before = self.rule(self.box1)
        response = self.assist(self.box1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['rule']['actions'], 'Salvarli')
        after = self.rule(self.box1)
        self.assertEqual((after.version, after.actions, after.selection, after.updated_at),
                         (before.version, before.actions, before.selection, before.updated_at))
        self.assertIsNone(self.rule(self.box2))
        self.assist(self.box1)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(rules.AttachmentRule)), 1)

    def test_prompt_contains_only_user_text_and_pdf_scope(self):
        seen = []
        with self.factory.begin() as db:
            db.add(incoming.Arrival(mailbox_id=self.box1, generation=1, uidvalidity='1', uid=1,
                sender='secret-sender@example.test', recipient='office@example.test', subject='Confidential subject'))
        result = rules.assist(message='Salva i PDF delle fatture', history=[{'role': 'user', 'content': 'ciao'}],
            draft={'actions': 'Salvarli'}, generate_json_fn=lambda prompt: seen.append(prompt) or
            {'reply': 'Ok', 'rule': {'selection': 'PDF', 'conditions': '', 'actions': 'Salvarli', 'missing': ''}})
        self.assertEqual(result['rule']['actions'], 'Salvarli')
        prompt = seen[0]
        self.assertIn('Salva i PDF delle fatture', prompt)
        self.assertIn('only PDF attachments', prompt)
        self.assertIn('Never invent actions', prompt)
        for private in ('office@example.test', 'imaps.aruba.it', 'secret-sender', 'Confidential subject', 'local:'):
            self.assertNotIn(private, prompt)
        # The route forwards only the form text fields, never mailbox data.
        self.assist(self.box1)
        self.assertEqual(set(self.calls[-1]), {'message', 'history', 'draft'})
        self.assertEqual(set(self.calls[-1]['draft']), set(rules.FIELDS))

    # -- Always inactive, no download or execution ---------------------------
    def test_rule_is_always_inactive_pdf_only_and_touches_no_mailbox_state(self):
        with self.factory() as db:
            box = db.get(incoming.Mailbox, self.box1)
            snapshot = (box.last_uid, box.uidvalidity, box.config_version, box.generation, box.next_check_at, box.enabled)
        self.save(self.box1)
        self.assist(self.box1)
        row = self.rule(self.box1)
        self.assertFalse(row.active)
        self.assertEqual(row.file_type, 'PDF')
        with self.factory() as db:
            box = db.get(incoming.Mailbox, self.box1)
            self.assertEqual(snapshot, (box.last_uid, box.uidvalidity, box.config_version, box.generation,
                                        box.next_check_at, box.enabled))
            self.assertEqual(db.scalar(select(func.count()).select_from(incoming.Arrival)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(incoming.MailboxCheck)), 0)
        self.assertEqual(self.vault.loads, 0)
        for column, value in (('active', True), ('file_type', 'DOCX')):
            with self.assertRaises(IntegrityError):
                with self.factory.begin() as db:
                    setattr(db.get(rules.AttachmentRule, self.box1), column, value)
        source = (STORE / 'rfone_data_store/incoming_attachment_rules.py').read_text(encoding='utf-8')
        for forbidden in ('imaplib', 'imap_mailbox', 'BODY[', 'smtplib', 'vault'):
            self.assertNotIn(forbidden, source)

    # -- AI unavailable -------------------------------------------------------
    def test_ai_unavailable_is_reported_and_manual_save_still_works(self):
        def down(**kw):
            raise rules.AssistantUnavailable('NOT_CONFIGURED')
        self.assistant = down
        self.ai = (False, 'ANTHROPIC_API_KEY non configurata')
        response = self.assist(self.box1)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()['error'], 'NOT_CONFIGURED')
        self.assertIn('non è configurato', response.get_json()['message'])
        self.assertNotIn('reply', response.get_json())
        page = self.client.get('/administration/email/mailboxes').get_data(as_text=True)
        self.assertIn('L’assistente AI non è disponibile in questo ambiente (ANTHROPIC_API_KEY non configurata)', page)
        self.assertEqual(self.save(self.box1).status_code, 302)
        self.assertEqual(self.rule(self.box1).actions, 'Salvarli')

    def test_assist_never_simulates_an_answer(self):
        def provider_down(prompt):
            raise ai_client.AIProviderUnavailable('No ANTHROPIC_API_KEY configured.')
        with self.assertRaises(rules.AssistantUnavailable):
            rules.assist(message='x', generate_json_fn=provider_down)
        for bad in ({'reply': 'x'}, {'rule': {}}, 'text', {'reply': 'x', 'rule': {'actions': 5}}):
            with self.assertRaises(rules.AssistantUnavailable):
                rules.assist(message='x', generate_json_fn=lambda prompt, bad=bad: bad)
        with self.assertRaises(ValueError):
            rules.assist(message='   ', generate_json_fn=provider_down)
        self.assertEqual(self.assist(self.box1, history='{"not": "a list"}').status_code, 400)
        self.assertEqual(self.assist(self.box1, history='not json').status_code, 400)

    # -- Error kinds, timeouts, malformed answers ------------------------------
    def test_error_kinds_are_classified_without_leaking_details(self):
        secret = 'arn:aws:iam::123456789012:user/secret-detail'
        cases = [(ai_client.AIProviderTimeout(secret), 'TIMEOUT', 504),
                 (ai_client.AIProviderNotConfigured(secret), 'NOT_CONFIGURED', 503),
                 (ai_client.AIProviderDependencyMissing(secret), 'DEPENDENCY_MISSING', 503),
                 (ai_client.AIProviderBadResponse(secret), 'BAD_RESPONSE', 503),
                 (ai_client.AIProviderUnavailable(secret), 'PROVIDER_ERROR', 503),
                 (RuntimeError(secret), 'PROVIDER_ERROR', 503)]
        for error, code, status in cases:
            def fail(prompt, error=error):
                raise error
            with self.assertRaises(rules.AssistantUnavailable) as caught:
                rules.assist(message='Solo PDF', generate_json_fn=fail)
            self.assertEqual(caught.exception.code, code)
            self.assistant = lambda **kw: rules.assist(generate_json_fn=fail, **kw)
            response = self.assist(self.box1)
            self.assertEqual((response.status_code, response.get_json()['error']), (status, code))
            self.assertNotIn('secret-detail', response.get_data(as_text=True))
            self.assertNotIn('123456789012', response.get_data(as_text=True))
        self.assertIsNone(self.rule(self.box1))

    def test_proposal_validation(self):
        ok = rules.validate_proposal({'reply': 'Quale azione?', 'rule': {'selection': 'PDF con CV nel nome',
                                      'conditions': None, 'actions': '', 'missing': ''}})
        self.assertEqual(ok['rule']['actions'], '')
        self.assertEqual(ok['rule']['conditions'], '')
        self.assertIn('Azione da definire', ok['rule']['missing'])
        kept = rules.validate_proposal({'reply': 'x', 'rule': {'selection': 'PDF', 'actions': '',
                                        'missing': 'Azione successiva da decidere'}})
        self.assertEqual(kept['rule']['missing'], 'Azione successiva da decidere')
        docx = rules.validate_proposal({'reply': 'x', 'rule': {'selection': 'file .docx', 'actions': 'Archiviare'}})
        self.assertIn(rules.PDF_ONLY_NOTE, docx['rule']['missing'])
        self.assertEqual(set(docx), {'reply', 'rule'})
        self.assertEqual(set(docx['rule']), set(rules.PROPOSAL_KEYS))
        for bad in (None, [], {'reply': '', 'rule': {}}, {'reply': 'x', 'rule': {'selection': ['a']}},
                    {'reply': 'x' * (rules.FIELD_LIMIT + 1), 'rule': {}}, {'reply': 'x', 'rule': {'actions': 'a\x00'}}):
            with self.assertRaises(rules.AssistantUnavailable) as caught:
                rules.validate_proposal(bad)
            self.assertEqual(caught.exception.code, 'BAD_RESPONSE')

    def test_rule_is_bound_to_the_opening_mailbox(self):
        prompt = rules.build_prompt(message='Solo PDF con CV', history=[], draft={})
        self.assertIn('The mailbox is ALREADY DETERMINED', prompt)
        self.assertIn('Never ask which mailbox', prompt)
        for private in ('office@example.test', 'imaps.aruba.it'):
            self.assertNotIn(private, prompt)
        cleaned = rules.validate_proposal({'reply': 'Ok', 'rule': {'selection': 'PDF con CV', 'actions': 'Conservarli',
            'missing': 'Su quale casella applicare la regola?\nMittenti da considerare'}})
        self.assertEqual(cleaned['rule']['missing'], 'Mittenti da considerare')
        only_mailbox = rules.validate_proposal({'reply': 'Ok', 'rule': {'selection': 'PDF', 'actions': 'Conservarli',
            'missing': 'mailbox di destinazione, account email da usare'}})
        self.assertEqual(only_mailbox['rule']['missing'], '')
        untouched = rules.validate_proposal({'reply': 'Ok', 'rule': {'selection': 'PDF', 'actions': 'Conservarli',
            'missing': 'indirizzo email dei fornitori, periodo'}})
        self.assertEqual(untouched['rule']['missing'], 'indirizzo email dei fornitori, periodo')

    def test_default_assist_uses_email_selector_with_timeout(self):
        seen = {}
        def fake(prompt, *, timeout=None):
            seen.update(prompt=prompt, timeout=timeout)
            return {'reply': 'Ok', 'rule': {'selection': 'PDF', 'conditions': '', 'actions': 'x', 'missing': ''}}
        with patch.object(ai_client, 'generate_json_for_email_rules', fake), \
                patch.object(ai_client, 'generate_json', side_effect=AssertionError('global provider used')):
            rules.assist(message='Solo PDF con CV')
        self.assertEqual(seen['timeout'], rules.AI_TIMEOUT_SECONDS)
        self.assertIn('Solo PDF con CV', seen['prompt'])

    # -- Email selector configuration in the shared client -------------------
    def env(self, **values):
        return patch.object(ai_client, '_read_env_or_dotenv', lambda name: values.get(name))

    def test_email_selector_configuration_and_no_global_fallback(self):
        with self.env(RFONE_AI_PROVIDER='BEDROCK', RFONE_BEDROCK_MODEL_ID='global-model'):
            with self.assertRaises(ai_client.AIProviderNotConfigured):
                ai_client.generate_json_for_email_rules('p', timeout=1)
            self.assertEqual(rules.provider_status(), (False, 'RFONE_EMAIL_AI_PROVIDER non configurato'))
        with self.env(RFONE_EMAIL_AI_PROVIDER='ANTHROPIC', RFONE_EMAIL_BEDROCK_MODEL_ID='m'):
            with self.assertRaises(ai_client.AIProviderNotConfigured):
                ai_client.generate_json_for_email_rules('p', timeout=1)
        with self.env(RFONE_EMAIL_AI_PROVIDER='BEDROCK'):
            with self.assertRaises(ai_client.AIProviderNotConfigured):
                ai_client.generate_json_for_email_rules('p', timeout=1)
            self.assertEqual(rules.provider_status(), (False, 'RFONE_EMAIL_BEDROCK_MODEL_ID non configurato'))
        with self.env(RFONE_EMAIL_AI_PROVIDER='bedrock', RFONE_EMAIL_BEDROCK_MODEL_ID='openai.test-model'):
            self.assertEqual(rules.provider_status(), (True, 'BEDROCK · openai.test-model'))
            with patch.dict(sys.modules, {'boto3': None}):
                self.assertEqual(rules.provider_status()[0], False)
                with self.assertRaises(ai_client.AIProviderDependencyMissing):
                    ai_client.generate_json_for_email_rules('p', timeout=1)

    def test_email_selector_uses_profile_model_and_timeout(self):
        calls = {}

        class Client:
            def __init__(self, answer):
                self.answer = answer

            def converse(self, **kw):
                calls['converse'] = kw
                return {'stopReason': 'end_turn', 'output': {'message': {'content': [
                    {'reasoningContent': {'reasoningText': {'text': 'hidden'}}}, {'text': self.answer}]}}}

        def fake_boto3(answer):
            def session(profile_name=None):
                calls['profile'] = profile_name
                def client(name, region_name=None, config=None):
                    calls.update(service=name, region=region_name, read_timeout=config.read_timeout,
                                 attempts=config.retries['total_max_attempts'])
                    return Client(answer)
                return types.SimpleNamespace(client=client)
            return types.SimpleNamespace(Session=session, client=lambda *a, **k: (_ for _ in ()).throw(
                AssertionError('default credential chain used')))

        config = dict(RFONE_EMAIL_AI_PROVIDER='BEDROCK', RFONE_EMAIL_BEDROCK_MODEL_ID='openai.gpt-oss-test',
                      RFONE_EMAIL_AWS_PROFILE='local-profile', AWS_REGION='us-east-1', RFONE_AI_PROVIDER='ANTHROPIC')
        ai_client._BEDROCK_CLIENTS.clear()
        with self.env(**config), patch.dict(sys.modules, {'boto3': fake_boto3('```json\n{"reply": "ok", "rule": {}}\n```')}):
            self.assertEqual(ai_client.generate_json_for_email_rules('synthetic', timeout=45), {'reply': 'ok', 'rule': {}})
        self.assertEqual((calls['profile'], calls['region'], calls['read_timeout'], calls['attempts']),
                         ('local-profile', 'us-east-1', 45, 1))
        self.assertEqual(calls['converse']['modelId'], 'openai.gpt-oss-test')
        ai_client._BEDROCK_CLIENTS.clear()
        for answer, error in (('not json', ai_client.AIProviderBadResponse), ('[1, 2]', ai_client.AIProviderBadResponse)):
            with self.env(**config), patch.dict(sys.modules, {'boto3': fake_boto3(answer)}):
                with self.assertRaises(error):
                    ai_client.generate_json_for_email_rules('synthetic', timeout=45)
            ai_client._BEDROCK_CLIENTS.clear()

    # -- Local sandbox migration ---------------------------------------------
    def test_sandbox_upgrade_backs_up_and_preserves_existing_data(self):
        with tempfile.TemporaryDirectory(prefix='rfone_rules_sandbox_') as directory:
            path = Path(directory) / 'sandbox.db'
            engine = create_configured_engine('sqlite:///' + path.as_posix(), sqlite_immediate=True)
            with engine.begin() as db:
                m.Base.metadata.create_all(db, tables=[m.RFOneAccount.__table__] + outgoing.TABLES)
                _apply_local_migration(db, 'i9a120261117_incoming_email_monitoring.py')
                _apply_local_migration(db, 'i9b120261117_incoming_attachment_metadata.py')
                db.execute(text('CREATE TABLE _email_control_sandbox (version VARCHAR(30) NOT NULL)'))
                db.execute(text("INSERT INTO _email_control_sandbox VALUES ('i9b120261117')"))
                db.execute(m.RFOneAccount.__table__.insert().values(id=1, username='u', display_name='U', password_hash='x'))
            with create_session_factory(engine).begin() as db:
                box = incoming.configure(db, owner=1, credential_ref='local:' + 'a' * 32, label='Box',
                    address='a@example.test', host='imaps.aruba.it', username='a@example.test', folder='INBOX', interval_seconds=60)
                box.uidvalidity, box.last_uid = '77', 42
            engine.dispose()
            with self.assertRaises(RuntimeError):
                prepare_database(path)
            backup = upgrade_database(path)
            self.assertTrue(backup.exists())
            self.assertIn('pre-i9c120261117', backup.name)
            with closing(sqlite3.connect(str(backup))) as old:
                self.assertEqual(old.execute('SELECT version FROM _email_control_sandbox').fetchone()[0], 'i9b120261117')
            engine = prepare_database(path)
            with engine.connect() as db:
                self.assertEqual(db.scalar(text('SELECT version FROM _email_control_sandbox')), SANDBOX_VERSION)
                self.assertEqual(db.execute(text('SELECT credential_ref, uidvalidity, last_uid FROM email_mailboxes')).one(),
                                 ('local:' + 'a' * 32, '77', 42))
                self.assertEqual(db.scalar(text('SELECT count(*) FROM email_attachment_rules')), 0)
            engine.dispose()
            self.assertIsNone(upgrade_database(path))

    def test_fresh_sandbox_includes_rules_table(self):
        with tempfile.TemporaryDirectory(prefix='rfone_rules_fresh_') as directory:
            engine = prepare_database(Path(directory) / 'fresh.db')
            with engine.connect() as db:
                self.assertEqual(db.scalar(text('SELECT version FROM _email_control_sandbox')), 'i9c120261117')
                self.assertEqual(db.scalar(text('SELECT count(*) FROM email_attachment_rules')), 0)
            engine.dispose()


if __name__ == '__main__':
    unittest.main()
