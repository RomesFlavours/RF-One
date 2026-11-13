"""Movement research reads dated cross-record evidence and never classifies.

HTTP tests use a disposable SQLite backup. Provider responses are stubbed;
context assembly, identity/date selection, access controls and persistence run for real.
"""
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1])]
import test_bank_conversation_intent as fixture
from db import SessionFactory
from sqlalchemy import select
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import card_configuration
from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable
import app as web
import auth
import bank_chatgpt
import bank_assistant_preview_routes
import bank_movement_research as research


class ResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.IntentTests.setUpClass()
        cls.day=date(2027,3,10)
        with SessionFactory() as db:
            sibling=m.PaymentInstrument(instrument_type='CREDIT_CARD',display_name='Same traveler second card',currency='USD',status='ACTIVE')
            db.add(sibling);db.flush()
            card_configuration.assign_settlement_account(db,credit_card_payment_instrument_id=sibling.id,
                settlement_bank_account_id=fixture.IntentTests.personal_account,valid_from=date(2020,1,1))
            other=m.ReportingEntity(code='RESEARCH_OTHER_OWNER',name='Another person',entity_type='PERSONAL',status='ACTIVE')
            db.add(other);db.flush()
            source=m.PaymentInstrument(instrument_type='BANK_ACCOUNT',display_name='Unrelated person source',currency='USD',owner_reporting_entity_id=other.id,status='ACTIVE')
            db.add(source);db.flush()
            def txn(description,offset,source_id,duplicate='NONE'):
                t=m.FinancialTransaction(payment_instrument_id=source_id,description_original=description,
                    transaction_date=cls.day+timedelta(days=offset),posting_date=cls.day+timedelta(days=offset+1),
                    amount_minor=-7680,source_memo='Research fixture memo',accounting_status='CANONICAL',
                    duplicate_status=duplicate,classification='UNKNOWN',status='COMPLETED')
                db.add(t);db.flush();return t.id
            card=fixture.IntentTests.personal_card
            cls.target=txn('METRO P.H. EDIFIC 4732 (V',0,card)
            cls.flight=txn('AIRLINE ORLANDO PANAMA flight',-2,card)
            cls.hotel=txn('HOTEL PANAMA CITY',-1,sibling.id)
            cls.local=txn('PUBLIX WINTER PARK ROUTINE',-40,card)
            cls.unrelated=txn('HOTEL FOR ANOTHER PERSON',-1,source.id)
            cls.duplicate=txn('AIRLINE DUPLICATE',-1,card,'CONFIRMED_DUPLICATE')
            db.commit()

    def setUp(self):
        self.client=web.app.test_client()
        with self.client.session_transaction() as session:
            session[auth.SESSION_ACCOUNT_KEY]=fixture.IntentTests.admin_id
            session[auth.SESSION_VERSION_KEY]=fixture.IntentTests.admin_version
        page=self.client.get('/bank/ai-rules').data.decode()
        self.csrf=re.search(r'<meta name="bank-csrf" content="([^"]+)"',page).group(1)
        self.url=f'/bank/movements/{self.target}/research'

    def fingerprint(self):
        models=(m.FinancialTransaction,m.BankTransactionExplanation,m.BankTransactionAllocation,
            m.BankAiRule,m.BankAiRuleVersion,m.BankWhoSourceClassification,m.BankOccurrence,
            m.BankTransactionReason,m.BankAccountingClassification,m.BankWhoKnowledge,m.PaymentInstrument,
            m.BankCardSettlementAccount,m.BankCardHolderAssignment,m.FinancialTransactionMatch)
        with SessionFactory() as db:
            data=[(model.__tablename__,[tuple(r) for r in db.execute(select(*model.__table__.c).order_by(model.id))]) for model in models]
        return hashlib.sha256(json.dumps(data,default=str).encode()).hexdigest()

    def answer(self):
        return dict(reply='Le date di volo e hotel rendono la spesa compatibile con un viaggio, ma manca la località abituale. Nessuna classificazione modificata.',
            assessment='TRAVEL_COMPATIBLE',confidence='MEDIUM',
            evidence=[dict(transaction_id=self.flight,reason='Volo due giorni prima'),dict(transaction_id=self.hotel,reason='Hotel su un’altra carta dello stesso proprietario')],
            sources=[dict(title='Source',url='https://example.org/merchant'),dict(title='unsafe',url='javascript:alert(1)')],
            missing_information=['Qual è la località abituale della persona?'])

    def test_context_contains_whole_record_and_cross_card_dated_evidence(self):
        before=self.fingerprint()
        response=self.client.get(self.url)
        self.assertEqual(response.status_code,200,response.data)
        c=response.get_json()['context'];target=c['movement']
        self.assertEqual(target['amount_minor'],-7680)
        self.assertEqual(target['currency'],'USD')
        self.assertEqual(target['date'],str(self.day))
        self.assertEqual(target['memo'],'Research fixture memo')
        self.assertTrue(target['source']['name'])
        self.assertTrue(target['whom']['default_name'])
        self.assertIn('raw_bank_fields',target)
        ids={r['id'] for r in c['nearby_records']}
        self.assertIn(self.flight,ids);self.assertIn(self.hotel,ids)
        self.assertNotIn(self.unrelated,ids);self.assertNotIn(self.duplicate,ids)
        hotel=next(r for r in c['nearby_records'] if r['id']==self.hotel)
        self.assertIn('same_personal_owner',hotel['relationship'])
        self.assertIn(self.local,{r['id'] for r in c['same_source_baseline']})
        self.assertIsNone(c['home_location'])
        self.assertEqual(self.fingerprint(),before)

    def test_chat_research_and_followup_store_only_advisory_conversation(self):
        before=self.fingerprint()
        with patch.object(bank_assistant_preview_routes,'_provider_context_approved',return_value=True), \
             patch.object(bank_chatgpt,'generate_json',return_value=self.answer()) as provider:
            response=self.client.post(self.url,data=dict(csrf_token=self.csrf))
            self.assertEqual(response.status_code,200,response.data)
            result=response.get_json();cid=result['conversation_id']
            self.assertEqual(provider.call_args.kwargs,dict(web_research=True))
            prompt=provider.call_args.args[0]
            context=json.loads(prompt[prompt.rindex('\n{')+1:])['context']
            self.assertEqual(context['movement']['description'],'METRO P.H. EDIFIC 4732 (V')
            self.assertIn('UNTRUSTED DATA',prompt)
            self.assertIn('Shared company ownership',prompt)
            self.assertEqual(len(result['answer']['sources']),1)
            response=self.client.post(self.url,data=dict(csrf_token=self.csrf,conversation_id=cid,message='Vivo a Winter Park; potrebbe essere Panama?'))
            self.assertEqual(response.status_code,200,response.data)
            self.assertEqual(len(response.get_json()['messages']),4)
            self.assertIn('Winter Park',provider.call_args.args[0])
            reopened=self.client.get(self.url).get_json()
            self.assertEqual(reopened['conversation_id'],cid)
            self.assertEqual(len(reopened['messages']),4)
        with SessionFactory() as db:
            self.assertEqual(db.get(m.BankFlowArtifact,cid).kind,research.KIND)
        self.assertEqual(self.fingerprint(),before)

    def test_missing_csrf_or_consent_never_calls_chatgpt(self):
        with patch.object(bank_chatgpt,'generate_json') as provider:
            self.assertEqual(self.client.post(self.url).status_code,400)
            with patch.object(bank_assistant_preview_routes,'_provider_context_approved',return_value=False):
                self.assertEqual(self.client.post(self.url,data=dict(csrf_token=self.csrf)).status_code,403)
            provider.assert_not_called()

    def test_foreign_conversation_and_unknown_evidence_rejected_without_changes(self):
        with SessionFactory() as db:
            artifact=m.BankFlowArtifact(kind=research.KIND,account_id=None,payload=json.dumps(dict(transaction_id=self.target,messages=[])))
            db.add(artifact);db.flush();cid=artifact.id;db.commit()
        before=self.fingerprint()
        with patch.object(bank_assistant_preview_routes,'_provider_context_approved',return_value=True),patch.object(bank_chatgpt,'generate_json') as provider:
            self.assertEqual(self.client.post(self.url,data=dict(csrf_token=self.csrf,conversation_id=cid)).status_code,404)
            provider.assert_not_called()
            bad=self.answer();bad['evidence']=[dict(transaction_id=999999999,reason='Invented record')]
            provider.return_value=bad
            self.assertEqual(self.client.post(self.url,data=dict(csrf_token=self.csrf)).status_code,409)
        self.assertEqual(self.fingerprint(),before)

    def test_provider_failure_is_recoverable_and_never_classifies(self):
        before=self.fingerprint()
        with patch.object(bank_assistant_preview_routes,'_provider_context_approved',return_value=True), \
             patch.object(bank_chatgpt,'generate_json',side_effect=AIProviderUnavailable('offline')):
            self.assertEqual(self.client.post(self.url,data=dict(csrf_token=self.csrf)).status_code,503)
        self.assertEqual(self.fingerprint(),before)

    def test_existing_classification_is_not_hidden_by_empty_engine_proposal(self):
        with SessionFactory() as db:
            explanation=db.scalar(select(m.BankTransactionExplanation).where(
                m.BankTransactionExplanation.transaction_reason_name_snapshot.is_not(None)))
            self.assertIsNotNone(explanation)
            target=db.get(m.FinancialTransaction,self.target)
            target.explanation_id=explanation.id;db.flush()
            with patch.object(research.engine_view,'values',return_value={self.target:dict(
                who_name=None,why=None,category=None,status='EXCEPTION')}):
                result=research.context(db,self.target)['movement']
            self.assertEqual(result['why'],explanation.transaction_reason_name_snapshot)
            self.assertIsNone(result['engine_proposal']['why'])
            db.rollback()

    def test_ai_buttons_open_advisory_modal_on_both_review_views(self):
        for view in ('to_reconcile','reconciled'):
            page=self.client.get('/bank/review?view='+view).data.decode()
            self.assertIn('bank-movement-research-dialog',page)
            self.assertIn('bank-movement-research.js',page)
        page=self.client.get('/bank/review?view=to_reconcile&search=METRO').data.decode()
        self.assertIn(f'data-movement-research="{self.target}"',page)
        self.assertNotIn(f'data-profile-research="{self.target}"',page)


if __name__=='__main__':unittest.main()
