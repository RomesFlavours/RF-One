"""Offline integration tests against a disposable canonical SQLite schema."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB))
sys.path.insert(0, str(WEB.parent / 'RF-One Data Store'))
TEMP = tempfile.TemporaryDirectory()
DB_PATH = Path(TEMP.name) / 'ai-organization-local.sqlite3'
os.environ['RFONE_DATABASE_URL'] = 'sqlite:///' + DB_PATH.as_posix()

from flask import Flask, abort
from sqlalchemy import select, func
from db import SessionFactory, _engine
from rfone_data_store import models as m
from rfone_data_store import ai_organization as svc
import auth
from ai_organization_routes import register_ai_organization_routes


class OrganizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        m.Base.metadata.create_all(_engine)

    def setUp(self):
        self.db = SessionFactory()
        a = m.RFOneAccount(username='user-' + svc.now(), display_name='Utente demo', password_hash='unused', status='ACTIVE')
        other = m.RFOneAccount(username='other-' + svc.now(), display_name='Altro utente', password_hash='unused', status='ACTIVE')
        entity = m.LegalEntity(legal_name='Azienda demo', status='ACTIVE')
        foreign = m.LegalEntity(legal_name='Altra azienda', status='ACTIVE')
        self.db.add_all([a, other, entity, foreign])
        self.db.flush()
        self.db.add(svc.CompanyGrant(account_id=a.id, entity_id=entity.id, can_apply=True))
        self.db.add(m.RFOneAccountDomainAccess(account_id=a.id, domain_code='AI_ORGANIZATION', enabled=True))
        self.db.commit()
        self.a, self.other, self.entity, self.foreign = a, other, entity, foreign

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def interview(self):
        row = svc.create(self.db, self.a, self.entity.id)
        for message in ['Vorrei riaprire la sede demo', 'Due persone, venti ore, budget da verificare',
                        'Il titolare autorizza le spese', 'Nessuno coordina le consegne']:
            svc.turn(self.db, row, self.a, message)
        return row

    def test_complete_path_correction_approval_idempotence_restart(self):
        row = self.interview()
        self.assertIn('Ti propongo', json.loads(row.document)['messages'][1]['text'])
        svc.approve(self.db, row, self.a)
        svc.turn(self.db, row, self.a, 'Correzione: solo dieci ore disponibili')
        self.assertIsNone(row.approved_revision)
        with self.assertRaises(ValueError):
            svc.apply(self.db, row, self.a)
        draft = [dict(name='Coordinamento consegne demo', description='Raccoglie le consegne, segnala ritardi al titolare; nessun potere di spesa.', process='Consegne demo')]
        svc.revise(row, draft, self.a)
        svc.approve(self.db, row, self.a)
        svc.apply(self.db, row, self.a)
        self.db.commit()
        ids = json.loads(row.document)['applied'][-1]['records']
        svc.apply(self.db, row, self.a)
        self.db.commit()
        self.assertEqual(len(json.loads(row.document)['applied']), 1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.ProcessOwnership).where(m.ProcessOwnership.scope_id == self.entity.id)), 1)
        interview_id, account_id = row.id, self.a.id
        with SessionFactory() as reopened:
            persisted = svc.load(reopened, reopened.get(m.RFOneAccount, account_id), interview_id)
            self.assertEqual(json.loads(persisted.document)['applied'][-1]['records'], ids)
            self.assertTrue(svc.context(reopened, self.entity.id)['positions'])

    def test_company_and_author_isolation(self):
        with self.assertRaises(PermissionError):
            svc.create(self.db, self.a, self.foreign.id)
        row = self.interview()
        with self.assertRaises(PermissionError):
            svc.load(self.db, self.other, row.id)
        self.assertEqual([x.id for x in svc.companies(self.db, self.a)], [self.entity.id])
        self.assertFalse(svc.context(self.db, self.foreign.id)['positions'])

    def test_readonly_grant_cannot_apply(self):
        row = self.interview()
        self.db.get(svc.CompanyGrant, (self.a.id, self.entity.id)).can_apply = False
        self.db.flush()
        with self.assertRaises(PermissionError):
            svc.approve(self.db, row, self.a)

    def test_changed_organization_requires_new_review(self):
        row = self.interview()
        svc.approve(self.db, row, self.a)
        p = svc.org.create_position(self.db, name='Intervento concorrente')
        svc.org.add_position_scope(self.db, position=p, scope_type='LEGAL_ENTITY', scope_id=self.entity.id)
        with self.assertRaisesRegex(ValueError, 'cambiata'):
            svc.apply(self.db, row, self.a)

    def test_shared_position_cannot_be_changed(self):
        row = self.interview()
        p = svc.org.create_position(self.db, name='Condivisa')
        for eid in [self.entity.id, self.foreign.id]:
            svc.org.add_position_scope(self.db, position=p, scope_type='LEGAL_ENTITY', scope_id=eid)
        svc.revise(row, [dict(name='Condivisa', description='Modifica', process='Processo')], self.a)
        with self.assertRaisesRegex(ValueError, 'condivisa'):
            svc.preview(self.db, row)

    def test_no_duplicate_across_sessions_or_access_grants(self):
        row = self.interview()
        svc.approve(self.db, row, self.a)
        svc.apply(self.db, row, self.a)
        self.db.commit()
        second = self.interview()
        svc.approve(self.db, second, self.a)
        svc.apply(self.db, second, self.a)
        self.db.commit()
        self.assertEqual(len(svc.context(self.db, self.entity.id)['positions']), 1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.RFOneAccountDomainAccess).where(m.RFOneAccountDomainAccess.account_id == self.a.id)), 1)

    def test_provider_invalid_response_is_not_simulated(self):
        row = svc.create(self.db, self.a, self.entity.id)
        with self.assertRaises(ValueError):
            svc.turn(self.db, row, self.a, 'Desiderio', provider=lambda _: {'reply': 'fake'})
        self.assertEqual(row.revision, 0)

    def test_first_reply_proposes_instead_of_outsourcing_design(self):
        row = svc.create(self.db, self.a, self.entity.id)
        svc.turn(self.db, row, self.a, 'Vorrei riaprire una sede')
        doc = json.loads(row.document)
        self.assertTrue(doc['draft'])
        self.assertTrue(doc['recommendation'])
        self.assertEqual(len(doc['research_sources']), 2)
        self.assertEqual(doc['research_sources'][0]['consulted_on'], '2026-10-18')
        self.assertIn('non esegue nuove ricerche', doc['research'])
        self.assertNotIn('Come vorresti distribuire', doc['messages'][-1]['text'])
        self.assertNotIn('modifica la proposta qui sotto', doc['messages'][-1]['text'])
        self.assertEqual(len(doc['missing']), 1)
        self.assertTrue(doc['hypotheses'])

    def test_provider_can_adapt_next_question_and_draft(self):
        row = svc.create(self.db, self.a, self.entity.id)
        captured = []
        def provider(payload):
            captured.append(payload)
            return dict(reply='Chi può autorizzare la variazione di orario?', summary='Disponibilità dichiarata: dieci ore.',
                missing=['Autorità sugli orari'], alternatives=['Coordinamento unico entro dieci ore'],
                draft=[dict(name='Coordinamento demo', description='Coordina entro dieci ore; autorità da chiarire.', process='Coordinamento demo')])
        svc.turn(self.db, row, self.a, 'Ho dieci ore', provider=provider)
        document = json.loads(row.document)
        self.assertEqual(document['mode'], 'AI')
        self.assertEqual(document['missing'], ['Autorità sugli orari'])
        self.assertEqual(captured[0]['document']['evidence'][0]['text'], 'Ho dieci ore')
        self.assertFalse(svc.context(self.db, self.entity.id)['positions'])

    def test_direct_provider_missing_credentials_never_uses_aws(self):
        from unittest.mock import patch
        from rfone_data_store.ai_organization_provider import existing_direct_provider
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY':'', 'RFONE_AI_PROVIDER':'BEDROCK'}):
            with self.assertRaisesRegex(ValueError, 'ANTHROPIC_API_KEY'):
                existing_direct_provider({'document':{}})

    def test_http_csrf_permissions_stale_revision_and_pages(self):
        app = Flask(__name__, template_folder=str(WEB / 'templates'), static_folder=str(WEB / 'static'))
        app.secret_key = 'test-only'
        app.jinja_env.globals['csrf_token'] = auth.get_csrf_token
        from functools import wraps
        def gate(code):
            def decorator(fn):
                @wraps(fn)
                def wrapped(*args, **kwargs):
                    with SessionFactory() as db:
                        a = auth.load_current_account(db)
                        if not a or not __import__('rfone_data_store.rfone_web_session', fromlist=['account_may_enter_domain']).account_may_enter_domain(db, a, code):
                            abort(403)
                    return fn(*args, **kwargs)
                return wrapped
            return decorator
        register_ai_organization_routes(app, SessionFactory=SessionFactory, require_domain_access=gate, require_csrf=auth.require_csrf)
        client = app.test_client()
        self.assertEqual(client.get('/ai-organization').status_code, 403)
        with client.session_transaction() as session:
            session[auth.SESSION_ACCOUNT_KEY] = self.a.id
            session[auth.SESSION_VERSION_KEY] = self.a.session_version
            session[auth.SESSION_CSRF_KEY] = 'test-token'
        self.assertEqual(client.get('/ai-organization').status_code, 200)
        self.assertEqual(client.post('/ai-organization', data={'entity_id': self.entity.id, 'message': 'Aprire'}).status_code, 400)
        created = client.post('/ai-organization', data={'csrf_token':'test-token', 'entity_id':self.entity.id, 'message':'Vorrei riaprire'})
        self.assertEqual(created.status_code, 302)
        self.assertEqual(client.get(created.location).status_code, 200)
        stale = client.post(created.location, data={'csrf_token':'test-token', 'revision':0, 'action':'message','message':'Correzione'})
        self.assertEqual(stale.status_code, 302)
        self.assertIn('sessione è cambiata', client.get(created.location).text)
        self.assertEqual(client.post('/ai-organization', data={'csrf_token':'test-token', 'entity_id':self.foreign.id, 'message':'Tentativo'}).status_code, 403)


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        _engine.dispose()
        TEMP.cleanup()
