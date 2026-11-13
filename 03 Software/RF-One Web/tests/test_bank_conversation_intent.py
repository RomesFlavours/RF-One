"""WHO/WHY terminology recovery and preview-confirmed configuration, on an isolated Bank copy.

The provider is stubbed in HTTP tests; its complete contract and the human's exact
Publix phrase are checked, while validation, preview, saving and stale guards run for real.
"""
import copy
from datetime import date
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1])]
import test_bank_review_who_rules as isolated
os.environ['RFONE_DATABASE_URL'] = 'sqlite:///' + isolated.COPY.as_posix()
os.environ['RFONE_WEB_TEST_SECRET_KEY'] = 'isolated-conversation-intent-test'
os.environ['RFONE_BANK_SINGLE_ENGINE'] = '1'
import app as web_app
import auth
import bank_chatgpt
import bank_assistant_preview_routes
import bank_conversation_intent as intent
from db import SessionFactory
from sqlalchemy import select
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import flow, card_configuration

PHRASE = 'Se è una carta personal allora il WHO è "Owner Personal — Food"\nin tutti gli altri casi è "Food Purchases"\n\n"PUBLIX #1661'
SPEC = dict(engine=flow.ENGINE, kind='EXTRACTOR', from_beginning=True, start='',
            require=['PUBLIX #'], end_mode='marker', end=' #')


class IntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with SessionFactory() as db:
            what = db.scalar(select(m.BankAccountingClassification).where(
                m.BankAccountingClassification.active.is_(True)))
            reasons = []
            for name, code in [('Owner Personal — Food','TEST_INTENT_PERSONAL'), ('Food Purchases','TEST_INTENT_FOOD')]:
                reason = db.scalar(select(m.BankTransactionReason).where(m.BankTransactionReason.name == name))
                if reason is None:
                    reason=m.BankTransactionReason(code=code,name=name,accounting_classification_id=what.id)
                    db.add(reason)
                reason.status='ACTIVE'
                if not reason.accounting_classification_id:reason.accounting_classification_id=what.id
                db.flush();reasons.append(reason.id)
            cls.personal_why,cls.food_why=reasons
            person=m.ReportingEntity(code='TEST_INTENT_OWNER',name='Intent test person',entity_type='PERSONAL',status='ACTIVE')
            db.add(person);db.flush()
            company=db.scalar(select(m.ReportingEntity).where(m.ReportingEntity.entity_type=='LEGAL'))
            assert company is not None
            sources=[]
            for name,kind,owner in [('Intent personal account','BANK_ACCOUNT',person.id),
                ('Intent personal card','CREDIT_CARD',None),('Intent company account','BANK_ACCOUNT',company.id),
                ('Intent company card','CREDIT_CARD',None),('Intent unknown owner','CREDIT_CARD',None)]:
                source=m.PaymentInstrument(display_name=name,instrument_type=kind,owner_reporting_entity_id=owner,currency='USD',status='ACTIVE')
                db.add(source);db.flush();sources.append(source.id)
            cls.personal_account,cls.personal_card,cls.company_account,cls.company_card,cls.unknown=sources
            for card,account in [(cls.personal_card,cls.personal_account),(cls.company_card,cls.company_account)]:
                card_configuration.assign_settlement_account(db,credit_card_payment_instrument_id=card,
                    settlement_bank_account_id=account,valid_from=date(2020,1,1))
            txn=db.scalar(select(m.FinancialTransaction).where(m.FinancialTransaction.accounting_status=='CANONICAL'))
            txn.description_original='PUBLIX #1661';txn.payment_instrument_id=cls.personal_card
            txn.explanation_id=None;txn.duplicate_status='NONE';cls.txn_id=txn.id
            admin=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.is_admin.is_(True),m.RFOneAccount.status=='ACTIVE'))
            cls.admin_id,cls.admin_version=admin.id,admin.session_version
            db.commit()

    def setUp(self):
        self.plan=dict(who='PUBLIX',cases=[dict(source_class='PERSONAL_CARD',why_name='Owner Personal — Food'),
            dict(source_class='OTHER',why_name='Food Purchases')])
        self.client=web_app.app.test_client()
        with self.client.session_transaction() as session:
            session[auth.SESSION_ACCOUNT_KEY]=self.admin_id
            session[auth.SESSION_VERSION_KEY]=self.admin_version
            session[auth.CSRF_SESSION_KEY if hasattr(auth,'CSRF_SESSION_KEY') else 'csrf_token']='intent-test-token'
        # Get the actual Bank CSRF token; no login or operational data is written.
        import re
        page=self.client.get('/bank/ai-rules').data.decode()
        self.csrf=re.search(r'<meta name="bank-csrf" content="([^"]+)"',page).group(1)
        with SessionFactory() as db:
            rule=m.BankAiRule(title='Intent test Publix',organization_kind='GENERAL',status='ACTIVE',apply_future=True)
            db.add(rule);db.flush()
            db.add(m.BankAiRuleVersion(rule_id=rule.id,version_no=1,rule_text='Publix merchant extraction',
                spec=json.dumps(SPEC),method='CODE'))
            self.rule_id=rule.id;db.commit()
        self.chat=self.post('/bank/flow/conversation',rule_id=self.rule_id)['id']

    def post(self,path,**data):
        response=self.client.post(path,data=dict(csrf_token=self.csrf,**data))
        self.assertEqual(response.status_code,200,response.data.decode()[:600])
        return response.get_json()

    def answer(self,**changes):
        return dict(ready=True,title='Publix name extraction',spec=copy.deepcopy(SPEC),
            classification_plan=copy.deepcopy(self.plan),reply='Intendi WHY: il WHO resta PUBLIX. Carta personale: Owner Personal — Food; altrimenti Food Purchases.',**changes)

    def discuss(self):
        with patch.object(bank_assistant_preview_routes,'_provider_context_approved',return_value=True), \
             patch.object(bank_chatgpt,'generate_json',return_value=self.answer()) as provider:
            result=self.post(f'/bank/flow/conversation/{self.chat}',message=PHRASE)
        prompt=provider.call_args.args[0]
        self.assertIn('Understand intent before terminology',prompt)
        self.assertIn(PHRASE,json.loads(prompt[prompt.rindex('\n{')+1:])['conversation'][-1]['text'])
        self.assertTrue(result['ready'],result)
        return result

    def preview(self):
        with patch.object(bank_assistant_preview_routes,'_provider_context_approved',return_value=True), \
             patch.object(bank_chatgpt,'generate_json',side_effect=AssertionError('Preview must not call AI for these code-only cases')):
            return self.post(f'/bank/flow/conversation/{self.chat}/preview')

    def decisions(self):
        with SessionFactory() as db:
            return (db.execute(select(m.FinancialTransaction.id,m.FinancialTransaction.explanation_id)).all(),
                db.execute(select(m.BankTransactionExplanation.id,m.BankTransactionExplanation.occurrence_id,
                                  m.BankTransactionExplanation.transaction_reason_id)).all())

    def test_exact_phrase_prepares_who_and_why_preview_then_explicit_atomic_save(self):
        before=self.decisions()
        with SessionFactory() as db:
            pairs_before=db.execute(select(m.BankWhoSourceClassification.id,m.BankWhoSourceClassification.transaction_reason_id)).all()
        chat=self.discuss()
        self.assertEqual(flow.extract(chat['spec'],'PUBLIX #1661'),'PUBLIX')
        p=self.preview();c=p['classification_preview']
        rows={r['source_id']:r for r in c['rows']}
        self.assertEqual(rows[self.personal_card]['why_id'],self.personal_why)
        self.assertEqual(rows[self.company_card]['why_id'],self.food_why)
        self.assertEqual(rows[self.personal_account]['why_id'],self.food_why) # personal CARD, not every personal Source
        self.assertIn(self.unknown,{r['source_id'] for r in c['skipped']})
        matched=next(r for r in p['rows'] if r['transaction_id']==self.txn_id)
        self.assertEqual(matched['prepared_after']['why'],'Owner Personal — Food')
        self.assertEqual(matched['extracted_who'],'PUBLIX')
        self.assertEqual(matched['after']['who'],'PUBLIX')
        self.assertEqual(matched['after']['why'],'Owner Personal — Food')
        self.assertTrue(matched['after']['what'])
        self.assertEqual(matched['default_whom'],'Intent test person')
        self.assertEqual(matched['after']['whom'],matched['default_whom'])
        self.assertLess(len(p['definition_summary']),230)
        with SessionFactory() as db:
            self.assertEqual(db.execute(select(m.BankWhoSourceClassification.id,m.BankWhoSourceClassification.transaction_reason_id)).all(),pairs_before)
        rejected=self.client.post(f'/bank/flow/conversation/{self.chat}/save',data=dict(csrf_token=self.csrf,preview_id=p['id'],action='FUTURE'))
        self.assertEqual(rejected.status_code,409)
        saved=self.post(f'/bank/flow/conversation/{self.chat}/save',preview_id=p['id'],action='FUTURE',confirm_classification='yes')
        self.assertEqual(saved['classifications_saved'],len(rows))
        # Regression: verifying configuration alone missed the bug. Read the actual
        # Review row and its column-filter values through the real single Engine.
        from rfone_data_store.bank_reconciliation import row_reconciliation, review_queues
        with SessionFactory() as db:
            txn=db.get(m.FinancialTransaction,self.txn_id)
            row=row_reconciliation.rows_view(db,[txn])['rows'][0]
            self.assertEqual(row['who'],'PUBLIX')
            self.assertEqual(row['why_id'],self.personal_why)
            reason=db.get(m.BankTransactionReason,self.personal_why)
            self.assertEqual(row['what_id'],reason.accounting_classification_id)
            self.assertTrue(row['what'])
            self.assertIsNotNone(row['for_whom'])
            texts=review_queues.column_texts(db,[txn])[txn.id]
            self.assertEqual(texts['why'],row['why'])
            self.assertIn('Intent test person',texts['for_whom'])
        self.assertEqual(self.decisions(),before)
        replay=self.client.post(f'/bank/flow/conversation/{self.chat}/save',data=dict(csrf_token=self.csrf,
            preview_id=p['id'],action='FUTURE',confirm_classification='yes'))
        self.assertEqual(replay.status_code,409)
        # A user's explicit row confirmation must accept the values actually shown,
        # even when the old persisted RULE explanation still has no WHO/WHY.
        with SessionFactory() as db:
            row_reconciliation.confirm_row(db,transaction_id=self.txn_id,
                reporting_entity_id=None,account_id=self.admin_id)
            row=row_reconciliation.rows_view(db,[db.get(m.FinancialTransaction,self.txn_id)])['rows'][0]
            self.assertEqual(row['status'],'Confirmed')
            self.assertEqual(row['why_id'],self.personal_why)
            self.assertEqual(row['what_id'],db.get(m.BankTransactionReason,self.personal_why).accounting_classification_id)
            self.assertIsNotNone(row['for_whom'])
            db.rollback()

    def test_saved_uninterpreted_phrase_compiles_both_parts_on_preview(self):
        self.post(f'/bank/flow/conversation/{self.chat}/draft',pending_message=PHRASE)
        with patch.object(bank_assistant_preview_routes,'_provider_context_approved',return_value=True), \
             patch.object(bank_chatgpt,'generate_json',return_value=self.answer()) as provider:
            p=self.post(f'/bank/flow/conversation/{self.chat}/preview')
        self.assertEqual(p['classification_preview']['who'],'PUBLIX')
        prompt=provider.call_args_list[0].args[0]
        self.assertIn('Understand intent before terminology',prompt)
        self.assertIn('Food Purchases',prompt)
        # Draft preparation receives the real WHY catalog, not just extraction examples.
        self.assertIn('catalog',json.loads(prompt[prompt.rindex('\n{')+1:]))

    def test_save_existing_persists_preview_values_and_protects_human_confirmation(self):
        from rfone_data_store.bank_reconciliation import row_reconciliation, rule_application_safety
        with SessionFactory() as db:
            from datetime import datetime, timezone
            for rule in db.scalars(select(m.BankAiRule).where(m.BankAiRule.title=='Publix name extraction', m.BankAiRule.id!=self.rule_id)):
                rule.deleted_at=datetime.now(timezone.utc)
            txn=db.get(m.FinancialTransaction,self.txn_id)
            txn.explanation_id=None
            txn.review_status='REQUIRES_REVIEW'
            db.commit()
        self.discuss(); preview=self.preview()
        row=next(r for r in preview['rows'] if r['transaction_id']==self.txn_id)
        self.assertEqual(row['choice']['why_id'],self.personal_why)
        saved=self.post(f'/bank/flow/conversation/{self.chat}/save',preview_id=preview['id'],
            action='ALL',confirm_classification='yes')
        self.assertGreaterEqual(saved['updated'],1)
        with SessionFactory() as db:
            txn=db.get(m.FinancialTransaction,self.txn_id)
            explanation=db.get(m.BankTransactionExplanation,txn.explanation_id)
            self.assertEqual(explanation.transaction_reason_id,self.personal_why)
            self.assertEqual(db.get(m.BankOccurrence,explanation.occurrence_id).canonical_name,'PUBLIX')
            allocation=db.scalar(select(m.BankTransactionAllocation).where(
                m.BankTransactionAllocation.financial_transaction_id==txn.id))
            self.assertEqual(allocation.transaction_reason_id,self.personal_why)
            self.assertEqual(allocation.reporting_entity_id,db.get(m.PaymentInstrument,self.personal_account).owner_reporting_entity_id)
            self.assertEqual(txn.review_status,'REVIEWED')
            self.assertEqual(explanation.decision_source,'HUMAN')
            row_reconciliation.confirm_row(db,transaction_id=txn.id,reporting_entity_id=None,account_id=self.admin_id)
            db.commit()
            protected=rule_application_safety.snapshot(db,txn)
        replay=self.client.post(f'/bank/flow/conversation/{self.chat}/save',data=dict(csrf_token=self.csrf,
            preview_id=preview['id'],action='ALL',confirm_classification='yes'))
        self.assertEqual(replay.status_code,409)
        self.plan['cases'][0]['why_name']='Food Purchases'
        self.discuss(); preview=self.preview()
        row=next(r for r in preview['rows'] if r['transaction_id']==self.txn_id)
        self.assertIsNone(row['choice'])
        self.assertIn('protected',row['note'])
        self.post(f'/bank/flow/conversation/{self.chat}/save',preview_id=preview['id'],
            action='ALL',confirm_classification='yes')
        with SessionFactory() as db:
            self.assertEqual(rule_application_safety.snapshot(db,db.get(m.FinancialTransaction,self.txn_id)),protected)

    def test_catalog_ids_and_unsupported_conditions_are_not_guessed(self):
        with SessionFactory() as db:
            for case in [dict(source_class='OTHER',why_name='Nonexistent purpose xyz'),
                         dict(source_class='OTHER',why_id=99999999),
                         dict(source_class='OTHER',why_id=self.food_why,amount_minor=50)]:
                with self.assertRaises(ValueError):intent.normalize(db,dict(who='PUBLIX',cases=[case]))

    def test_merchant_after_card_reference_reads_publix_not_prefix(self):
        text='POS SIG 04/17 VISA #5363 PUBLIX #1488 WINTER PARK FL'
        with SessionFactory() as db:
            spec=intent.compile_spec(db,dict(SPEC,classification_plan=self.plan))
            flow.validate(db,spec)
            fixed=dict(engine=flow.ENGINE,kind='EXTRACTOR',fixed_who='PUBLIX',require=['PUBLIX #'])
            flow.validate(db,fixed)
        for rule in (spec,fixed):
            self.assertEqual(flow.extract(rule,text),'PUBLIX')
            selection=flow.extract(rule,text,highlight=True)
            self.assertEqual(selection['who'],'PUBLIX')
            self.assertEqual(selection['before']+selection['who']+selection['after'],text)
            self.assertIsNone(flow.extract(rule,'SUPERPUBLIX #1488'))

    def test_plan_survives_extraction_revision_and_saved_draft(self):
        chat=self.discuss()
        self.post(f'/bank/flow/conversation/{self.chat}/draft',pending_message='')
        with SessionFactory() as db:
            revised=intent.incorporate(db,dict(spec=dict(SPEC,end_markers=[' #'])),chat['spec'])
        self.assertEqual(revised[intent.KEY],chat['spec'][intent.KEY])
        reloaded=self.client.get(f'/bank/flow/conversation/{self.chat}').get_json()
        self.assertEqual(reloaded['saved_definition']['spec'][intent.KEY],chat['spec'][intent.KEY])

    def test_stale_pair_change_blocks_save_and_does_not_publish_rule(self):
        self.discuss();p=self.preview()
        from rfone_data_store.bank_reconciliation import manual_reconciliation,source_classification
        with SessionFactory() as db:
            who=manual_reconciliation.create_who(db,name='PUBLIX').occurrence
            pair=db.scalar(select(m.BankWhoSourceClassification).where(
                m.BankWhoSourceClassification.occurrence_id==who.id,
                m.BankWhoSourceClassification.payment_instrument_id==self.personal_card))
            source_classification.save(db,occurrence_id=who.id,payment_instrument_id=self.personal_card,
                transaction_reason_id=self.food_why,classification_id=pair.id if pair else None)
            db.commit()
        response=self.client.post(f'/bank/flow/conversation/{self.chat}/save',data=dict(csrf_token=self.csrf,
            preview_id=p['id'],action='FUTURE',confirm_classification='yes'))
        self.assertEqual(response.status_code,409)
        with SessionFactory() as db:
            self.assertEqual(len(db.get(m.BankAiRule,self.rule_id).versions),1)

    def test_ambiguous_ai_answer_keeps_conversation_without_publishing(self):
        with patch.object(bank_assistant_preview_routes,'_provider_context_approved',return_value=True), \
             patch.object(bank_chatgpt,'generate_json',return_value=dict(ready=False,reply='Quale WHY vuoi usare?',spec=None)):
            data=self.post(f'/bank/flow/conversation/{self.chat}',message='Qualche altra causale')
        self.assertFalse(data['ready'])
        self.assertEqual(data['messages'][-2]['text'],'Qualche altra causale')


if __name__=='__main__':unittest.main()

