"""Organization, source-backed WHO research and actual future execution."""
import json
import unittest
from unittest.mock import patch
from datetime import date
from sqlalchemy import select
from test_bank_conversation_workflow import ConversationWorkflow as Workflow
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import ai_rules, ai_rule_operations as operations, rule_organization as organization

class KnowledgeOrganization(unittest.TestCase):
    setUp=Workflow.setUp
    tearDown=Workflow.tearDown
    decide=Workflow.decide
    context=Workflow.context
    post=Workflow.post
    state=Workflow.state

    def test_existing_fixed_mapping_is_a_signature_and_who_knowledge_is_real(self):
        data=self.client.get('/bank/ai-rules/snapshot',headers=self.headers).get_json()
        self.assertEqual(data['learned_rules'][0]['organization_kind'],'RECOGNITION')
        self.assertEqual({k['who_id'] for k in data['knowledge']},{self.oldwho.id,self.newwho.id})
        self.assertTrue(all(not k['sources'] for k in data['knowledge']))
        context=self.context(who_id=self.newwho.id)
        self.assertEqual(context['who_id'],self.newwho.id);self.assertEqual(context['who'],'NEW WHO')
        self.assertEqual(organization.inferred_kind({'who':{'mode':'between'}}),'GENERAL')
        self.assertEqual(organization.inferred_kind({'conditions':[{'field':'description','value':'AMAZON'}]}),'RECOGNITION')

    def test_queue_uses_current_incomplete_decisions_not_historical_preview(self):
        # The old rule proposes a different WHO/WHY for this completed record.
        ai_rules.preview_rule(self.s,rule_text=self.text,origin_transaction_id=self.txns[0].id,
            date_from=None,date_to=None,scope=ai_rules.SCOPE_ALL,ai_rule_id=self.rule.id,generate=self.generate)
        self.s.commit()
        data=self.client.get('/bank/ai-rules/snapshot',headers=self.headers).get_json()
        ids={row['id'] for group in data['cases'] for row in group['rows']}
        self.assertNotIn(self.txns[0].id,ids)
        self.assertIn(self.txns[1].id,ids);self.assertIn(self.txns[2].id,ids)

    def test_explicit_provisional_why_stays_in_the_queue(self):
        self.why.code='ONLINE_PURCHASE_UNIDENTIFIED';self.s.commit()
        data=self.client.get('/bank/ai-rules/snapshot',headers=self.headers).get_json()
        ids={row['id'] for group in data['cases'] for row in group['rows']}
        self.assertIn(self.txns[0].id,ids)

    def test_future_choice_executes_on_a_subsequent_movement_without_ai(self):
        c=self.context(rule_id=self.rule.id);before=self.state()
        result=self.post('/bank/ai-rules/chat/decision',confirmation_token=c['confirmation_token'],action='FUTURE',organization_kind='RECOGNITION')
        self.assertEqual(result.status_code,200,result.get_json());self.assertEqual(self.state(),before)
        self.s.expire_all()
        txn=m.FinancialTransaction(payment_instrument_id=self.txns[0].payment_instrument_id,posting_date=date(2026,2,1),
            amount_minor=-2500,description_original='SYNTHETIC RULE TEST',description_normalized='SYNTHETIC RULE TEST',
            status='COMPLETED',classification='UNKNOWN',duplicate_status='NONE',accounting_status='CANONICAL')
        self.s.add(txn);self.s.flush()
        with patch.object(ai_rules,'default_generate',side_effect=AssertionError('No AI at import')):
            context=operations.import_context(self.s)
            self.assertTrue(operations.apply_to_new_transaction(self.s,txn,context));operations.finish_import(context)
        decision=self.s.get(m.BankTransactionExplanation,txn.explanation_id)
        self.assertEqual(decision.occurrence_id,self.newwho.id);self.assertEqual(decision.transaction_reason_id,self.newwhy.id)

    def test_general_extraction_saved_for_future_creates_a_missing_who(self):
        text='Se descrizione contiene "Zelle payment to" e "JPM", estrai WHO tra "Zelle payment to" e "JPM"; WHY invariato.'
        raw=dict(kind='STRUCTURED',conditions=[dict(field='description',op='contains',value='Zelle payment to'),dict(field='description',op='contains',value='JPM')],
            who=dict(mode='between',start='Zelle payment to',end='JPM',start_at='anywhere',end_case='ignore'),
            coverage=[dict(instruction='whole rule',represented_by='conditions and WHO')])
        saved=operations.save_rule(self.s,rule_id=None,rule_text=text,create_missing_who=False,apply_future=False,
            origin_transaction_id=self.txns[0].id,account_id=None,generate=lambda _:raw)
        rid=saved.rule.id;self.s.commit()
        c=self.context(rule_id=rid)
        result=self.post('/bank/ai-rules/chat/decision',confirmation_token=c['confirmation_token'],action='FUTURE',organization_kind='GENERAL')
        self.assertEqual(result.status_code,200,result.get_json());self.s.expire_all()
        version=operations.current_version(self.s.get(m.BankAiRule,rid));self.assertTrue(version.create_missing_who)
        txn=m.FinancialTransaction(payment_instrument_id=self.txns[0].payment_instrument_id,posting_date=date(2026,2,1),amount_minor=-100,
            description_original='Zelle payment to NEVER SEEN WHO JPM12345',description_normalized='ZELLE PAYMENT TO NEVER SEEN WHO JPM12345',
            status='COMPLETED',classification='UNKNOWN',duplicate_status='NONE',accounting_status='CANONICAL')
        self.s.add(txn);self.s.flush()
        self.assertTrue(operations.apply_to_new_transaction(self.s,txn,operations.import_context(self.s)))
        decision=self.s.get(m.BankTransactionExplanation,txn.explanation_id)
        self.assertEqual(self.s.get(m.BankOccurrence,decision.occurrence_id).canonical_name,'NEVER SEEN WHO')
        self.assertIsNone(decision.transaction_reason_id)

    def test_archive_choice_preserves_kind_until_reviewed_apply(self):
        c=self.context(rule_id=self.rule.id)
        preview=self.post('/bank/ai-rules/chat/decision',confirmation_token=c['confirmation_token'],action='PAST_AND_FUTURE',organization_kind='GENERAL').get_json()
        self.s.refresh(self.rule);self.assertEqual(self.rule.organization_kind,'AUTO')
        result=self.post('/bank/ai-rules/chat/apply',confirmation_token=preview['confirmation_token'],preview_id=preview['preview_id'])
        self.assertEqual(result.status_code,200,result.get_json())
        self.s.refresh(self.rule);self.assertEqual(self.rule.organization_kind,'GENERAL');self.assertTrue(self.rule.apply_future)

    def test_invalid_organization_does_not_save(self):
        c=self.context(rule_id=self.rule.id)
        result=self.post('/bank/ai-rules/chat/decision',confirmation_token=c['confirmation_token'],action='FUTURE',organization_kind='BAD')
        self.assertEqual(result.status_code,409);self.s.refresh(self.rule);self.assertFalse(self.rule.apply_future)

    def test_a_later_organization_change_invalidates_earlier_confirmation(self):
        c=self.context(rule_id=self.rule.id)
        self.rule.organization_kind='GENERAL';self.s.commit()
        result=self.post('/bank/ai-rules/chat/decision',confirmation_token=c['confirmation_token'],action='FUTURE')
        self.assertEqual(result.status_code,409);self.s.refresh(self.rule);self.assertFalse(self.rule.apply_future)

    def test_research_stores_sources_without_classifying_or_changing_default(self):
        before=self.state()
        answer=dict(verified=True,summary='Attività verificata della controparte.',sources=[dict(title='Official',url='https://example.com/about')],suggested_reason_id=self.newwhy.id)
        with patch('bank_chatgpt.generate_json',return_value=answer) as generate:
            response=self.post(f'/bank/ai-rules/who/{self.newwho.id}/research')
            self.assertEqual(response.status_code,200,response.get_json())
            self.assertTrue(generate.call_args.kwargs['web_research'])
            self.assertNotIn('SYNTHETIC RULE TEST',generate.call_args.args[0])
        self.assertEqual(self.state(),before);self.s.refresh(self.newwho);self.assertIsNone(self.newwho.default_transaction_reason_id)
        item=self.s.scalar(select(m.BankWhoKnowledge));self.assertEqual(item.suggested_reason_id,self.newwhy.id)
        self.assertEqual(json.loads(item.sources_json)[0]['url'],'https://example.com/about')

    def test_unverified_or_unsafe_sources_are_not_saved(self):
        with patch('bank_chatgpt.generate_json',return_value=dict(verified=True,summary='Unverified',sources=[dict(title='Unsafe',url='javascript:alert(1)')])):
            response=self.post(f'/bank/ai-rules/who/{self.newwho.id}/research')
        self.assertEqual(response.status_code,422)
        self.assertIsNone(self.s.scalar(select(m.BankWhoKnowledge)))

    def test_two_scope_choices_only_in_page(self):
        page=self.client.get('/bank/ai-rules',headers=self.headers)
        self.assertEqual(page.status_code,200)
        self.assertIn('Foto segnaletiche',page.data.decode())
        self.assertIn('Conoscenza del WHO',page.data.decode())

if __name__=='__main__':unittest.main()
