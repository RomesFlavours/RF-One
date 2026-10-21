"""Synthetic end-to-end import pipeline, durable queue and reusable photo tests."""
import sys,json,unittest
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from unittest.mock import patch
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
import test_bank_conversation_workflow as fixture
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import ai_rules,ai_rule_operations as ops,import_pipeline as pipeline,economic_allocation as allocation,rule_application_safety as safety

class ImportPipeline(unittest.TestCase):
    setUp=fixture.ConversationWorkflow.setUp
    tearDown=fixture.ConversationWorkflow.tearDown
    decide=fixture.ConversationWorkflow.decide
    context=fixture.ConversationWorkflow.context
    post=fixture.ConversationWorkflow.post
    state=fixture.ConversationWorkflow.state

    def new(self,description='SYNTHETIC RULE TEST',source_id=None):
        t=m.FinancialTransaction(payment_instrument_id=source_id or self.txns[0].payment_instrument_id,posting_date=date(2026,2,1),amount_minor=-3300,
            description_original=description,description_normalized=description.upper(),status='COMPLETED',classification='UNKNOWN',duplicate_status='NONE',accounting_status='CANONICAL')
        self.s.add(t);self.s.flush();return t
    def for_whom(self,txn,entity=None):
        allocation.set_allocations(self.s,financial_transaction_id=txn.id,specs=[allocation.AllocationSpec(amount_minor=txn.amount_minor,
            reporting_entity_id=(entity or self.entity).id,status=m.ALLOCATION_NEEDS_OPERATOR,decision_source='HUMAN')]);self.s.commit()
    def prepare(self,txn):
        r=self.post(f'/bank/ai-rules/capture/{txn.id}',pattern='SYNTHETIC RULE TEST',match_op='contains')
        self.assertEqual(r.status_code,200,r.get_json());return r.get_json()
    def run_worker(self,**kwargs):
        import bank_import_worker as worker
        factory=sessionmaker(self.engine);job_id=worker.claim(factory);self.assertIsNotNone(job_id)
        worker.process(factory,job_id,**kwargs);self.s.expire_all();return self.s.get(m.BankImportReconciliation,job_id)
    def findings(self,name,reasons):
        return dict(summary='A verified single business activity.',sources=[dict(title='Official',url='https://example.com/about')],suggested_reason_id=self.newwhy.id)

    def test_general_extraction_then_photo_overrides_general_without_research(self):
        self.rule.apply_future=True;self.rule.organization_kind='RECOGNITION'
        text='If description contains "SYNTHETIC", WHO is "OLD WHO" and WHY is "Old reason".'
        raw=dict(kind='STRUCTURED',conditions=[dict(field='description',op='contains',value='SYNTHETIC')],who=dict(mode='fixed',name='OLD WHO'),why=dict(mode='fixed',name='Old reason'),coverage=[dict(instruction='all',represented_by='conditions WHO WHY')])
        saved=ops.save_rule(self.s,rule_id=None,rule_text=text,create_missing_who=False,apply_future=True,origin_transaction_id=self.txns[0].id,account_id=None,generate=lambda _:raw)
        saved.rule.organization_kind='GENERAL';self.s.commit()
        t=self.new();self.assertTrue(ops.apply_to_new_transaction(self.s,t,ops.import_context(self.s)));self.s.commit()
        e=self.s.get(m.BankTransactionExplanation,t.explanation_id);self.assertEqual(e.occurrence_id,self.newwho.id);self.assertEqual(e.transaction_reason_id,self.newwhy.id)
        job=self.s.scalar(select(m.BankImportReconciliation));self.assertEqual(job.status,'MATCHED')
        import bank_import_worker as worker
        self.assertIsNone(worker.claim(sessionmaker(self.engine)))

    def test_actual_csv_import_runs_pipeline_once_and_duplicate_upload_does_not(self):
        from rfone_data_store.bank_reconciliation import service
        self.rule.apply_future=True;self.s.commit()
        content=b'Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\nDEBIT,02/01/2026,SYNTHETIC RULE TEST,-33.00,ACH_DEBIT,1000.00,\n'
        first=service.import_csv(self.s,file_bytes=content,original_file_name='chase_1234.csv',uploaded_by_account_id=None,payment_instrument_id=self.txns[0].payment_instrument_id);self.s.commit()
        self.assertEqual(first.normalized_row_count,1)
        job=self.s.scalar(select(m.BankImportReconciliation));self.assertIsNotNone(job);self.assertEqual(job.status,'MATCHED')
        txn=self.s.get(m.FinancialTransaction,job.financial_transaction_id)
        self.assertEqual(self.s.get(m.BankTransactionExplanation,txn.explanation_id).occurrence_id,self.newwho.id)
        again=service.import_csv(self.s,file_bytes=content,original_file_name='same.csv',uploaded_by_account_id=None,payment_instrument_id=self.txns[0].payment_instrument_id);self.s.commit()
        self.assertFalse(again.created);self.assertEqual(len(list(self.s.scalars(select(m.BankImportReconciliation)))),1)

    def test_actual_csv_unmatched_job_survives_all_normalization_annotations(self):
        from rfone_data_store.bank_reconciliation import service
        content=b'Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\nDEBIT,02/02/2026,Payment to VERIFIED MERCHANT,-33.01,ACH_DEBIT,1000.00,\n'
        result=service.import_csv(self.s,file_bytes=content,original_file_name='chase_1234.csv',uploaded_by_account_id=None,payment_instrument_id=self.txns[0].payment_instrument_id);self.s.commit()
        job=self.s.scalar(select(m.BankImportReconciliation));self.assertEqual(job.status,'QUEUED')
        job=self.run_worker(extract_fn=lambda _:dict(certain=True,who='VERIFIED MERCHANT',evidence='VERIFIED MERCHANT'),research_fn=self.findings)
        self.assertEqual(job.status,'PROPOSED',job.last_error)

    def test_extracted_who_is_rechecked_against_photo_before_research(self):
        self.for_whom(self.txns[0])
        r=self.post(f'/bank/ai-rules/capture/{self.txns[0].id}',pattern='OLD WHO',match_op='who');self.assertEqual(r.status_code,200,r.get_json())
        self.assertEqual(self.post('/bank/ai-rules/chat/decision',confirmation_token=r.get_json()['confirmation_token'],action='FUTURE').status_code,200)
        self.s.expire_all();txn=self.new('Payment to OLD WHO bank reference');ops.apply_to_new_transaction(self.s,txn,ops.import_context(self.s));self.s.commit()
        job=self.run_worker(extract_fn=lambda _:dict(certain=True,who='OLD WHO',evidence='OLD WHO'),research_fn=lambda *_:self.fail('Photo must prevent web lookup'))
        self.assertEqual(job.status,'MATCHED',job.last_error);self.s.refresh(txn)
        self.assertEqual(self.s.get(m.BankTransactionExplanation,txn.explanation_id).transaction_reason_id,self.why.id)

    def test_import_rollback_leaves_no_jobs_or_provider_work(self):
        t=self.new();ops.apply_to_new_transaction(self.s,t,None);self.s.rollback()
        self.assertIsNone(self.s.scalar(select(m.BankImportReconciliation)))

    def test_unmatched_extracts_literal_who_and_researches_proposal_only(self):
        t=self.new('Payment to VERIFIED MERCHANT');ops.apply_to_new_transaction(self.s,t,None);self.s.commit()
        job=self.run_worker(extract_fn=lambda _:dict(certain=True,who='VERIFIED MERCHANT',evidence='VERIFIED MERCHANT'),research_fn=self.findings)
        self.assertEqual(job.status,'PROPOSED');self.s.refresh(t)
        e=self.s.get(m.BankTransactionExplanation,t.explanation_id);self.assertIsNone(e.transaction_reason_id)
        self.assertEqual(self.s.get(m.BankOccurrence,e.occurrence_id).canonical_name,'VERIFIED MERCHANT')
        proposal=json.loads(job.proposal_json);self.assertEqual(proposal['suggested_reason_id'],self.newwhy.id)
        response=self.client.get('/bank/import-reconciliation/status',query_string=dict(ids=t.id),headers=self.headers)
        self.assertEqual(response.get_json()['items'][0]['proposal']['suggested_why'],'New reason')

    def test_known_who_reuses_recent_research_on_next_record(self):
        for _ in range(2):
            t=self.new('NEW WHO payment');self.decide(t,self.newwho.id,None)
            ops.apply_to_new_transaction(self.s,t,None);self.s.commit()
            job=self.run_worker(extract_fn=lambda _:self.fail('Known WHO must not be extracted'),research_fn=self.findings if _==0 else lambda *_:self.fail('Reuse sourced WHO knowledge'))
            self.assertEqual(job.status,'PROPOSED')

    def test_future_photo_does_not_apply_to_a_movement_already_queued(self):
        txn=self.new('Payment OLD WHO');ops.apply_to_new_transaction(self.s,txn,None);self.s.commit()
        self.for_whom(self.txns[0]);response=self.post(f'/bank/ai-rules/capture/{self.txns[0].id}',pattern='OLD WHO',match_op='who')
        self.assertEqual(response.status_code,200,response.get_json());draft=response.get_json()
        self.assertEqual(self.post('/bank/ai-rules/chat/decision',confirmation_token=draft['confirmation_token'],action='FUTURE').status_code,200)
        job=self.run_worker(extract_fn=lambda _:dict(certain=True,who='OLD WHO',evidence='OLD WHO'),research_fn=self.findings)
        self.assertEqual(job.status,'PROPOSED');self.s.refresh(txn)
        self.assertIsNone(self.s.get(m.BankTransactionExplanation,txn.explanation_id).transaction_reason_id)

    def test_manual_change_during_extraction_stops_stale_job(self):
        t=self.new('Payment VERIFIED MERCHANT');ops.apply_to_new_transaction(self.s,t,None);self.s.commit()
        def extract(_):
            self.decide(t,self.oldwho.id,self.why.id);self.s.commit()
            return dict(certain=True,who='VERIFIED MERCHANT',evidence='VERIFIED MERCHANT')
        job=self.run_worker(extract_fn=extract,research_fn=lambda *_:self.fail('Stale job must not research'))
        self.assertEqual(job.status,'STALE');self.s.refresh(t);self.assertEqual(self.s.get(m.BankTransactionExplanation,t.explanation_id).occurrence_id,self.oldwho.id)

    def test_manual_change_during_research_preserves_later_decision(self):
        t=self.new();self.decide(t,self.newwho.id,None);ops.apply_to_new_transaction(self.s,t,None);self.s.commit()
        def research(*args):self.decide(t,self.oldwho.id,self.why.id);self.s.commit();return self.findings(*args)
        job=self.run_worker(research_fn=research)
        self.assertEqual(job.status,'STALE');self.assertIsNone(job.proposal_json)

    def test_provider_failure_is_visible_and_retry_is_csrf_protected(self):
        t=self.new();ops.apply_to_new_transaction(self.s,t,None);self.s.commit()
        def fail(_):raise RuntimeError('provider unavailable')
        job=self.run_worker(extract_fn=fail);self.assertEqual(job.status,'ERROR')
        self.assertEqual(self.client.post(f'/bank/import-reconciliation/{t.id}/retry',headers=self.headers).status_code,400)
        self.assertEqual(self.post(f'/bank/import-reconciliation/{t.id}/retry').status_code,200)
        self.s.expire_all();self.assertEqual(self.s.get(m.BankImportReconciliation,job.id).status,'QUEUED')

    def test_untrusted_nonliteral_extraction_is_not_applied(self):
        t=self.new();ops.apply_to_new_transaction(self.s,t,None);self.s.commit()
        job=self.run_worker(extract_fn=lambda _:dict(certain=True,who='INVENTED',evidence='not in bank text'),research_fn=lambda *_:self.fail('No verified WHO'))
        self.assertEqual(job.status,'AMBIGUOUS');self.s.refresh(t);self.assertIsNone(t.explanation_id)

    def test_capture_future_only_and_reuse_on_subsequent_import(self):
        self.rule.apply_future=True;self.s.commit()
        self.for_whom(self.txns[0]);draft=self.prepare(self.txns[0]);before=self.state()
        result=self.post('/bank/ai-rules/chat/decision',confirmation_token=draft['confirmation_token'],action='FUTURE',organization_kind='RECOGNITION')
        self.assertEqual(result.status_code,200,result.get_json());self.assertEqual(self.state(),before)
        self.s.expire_all();t=self.new();ops.apply_to_new_transaction(self.s,t,ops.import_context(self.s));self.s.commit()
        e=self.s.get(m.BankTransactionExplanation,t.explanation_id);self.assertEqual((e.occurrence_id,e.transaction_reason_id),(self.oldwho.id,self.why.id))
        a=self.s.scalar(select(m.BankTransactionAllocation).where(m.BankTransactionAllocation.financial_transaction_id==t.id));self.assertEqual(a.reporting_entity_id,self.entity.id)
        # Another Source must not match this photo.
        other=m.PaymentInstrument(instrument_type='BANK_ACCOUNT',display_name='Other',institution='CHASE',last_four='9876',currency='USD',status='ACTIVE');self.s.add(other);self.s.flush()
        other_txn=self.new(source_id=other.id);ops.apply_to_new_transaction(self.s,other_txn,ops.import_context(self.s));self.s.commit();self.assertEqual(self.s.get(m.BankTransactionExplanation,other_txn.explanation_id).occurrence_id,self.newwho.id)
        self.assertIsNone(self.s.scalar(select(m.BankTransactionAllocation).where(m.BankTransactionAllocation.financial_transaction_id==other_txn.id)))

    def test_capture_archive_preview_then_guarded_rollback(self):
        self.for_whom(self.txns[0]);draft=self.prepare(self.txns[0]);before=self.state()
        preview=self.post('/bank/ai-rules/chat/decision',confirmation_token=draft['confirmation_token'],action='PAST_AND_FUTURE',organization_kind='RECOGNITION').get_json()
        self.assertTrue(preview['ok'],preview);self.assertEqual(self.state(),before)
        result=self.post('/bank/ai-rules/chat/apply',confirmation_token=preview['confirmation_token'],preview_id=preview['preview_id'])
        self.assertEqual(result.status_code,200,result.get_json());aid=result.get_json()['application']['application_id']
        self.s.expire_all();self.decide(self.txns[1],self.newwho.id,self.newwhy.id);self.s.commit()
        undone=self.post(f'/bank/ai-rules/applications/{aid}/rollback').get_json();self.assertGreaterEqual(undone['restored'],1);self.assertTrue(any(x['id']==self.txns[1].id for x in undone['skipped']))

    def test_photo_preserves_captured_destination_when_why_mapping_changes(self):
        first=m.BankAccountingClassification(code='TEST_A',name='Captured destination',statement_type='PROFIT_LOSS',active=True)
        other=m.BankAccountingClassification(code='TEST_B',name='Later mapping',statement_type='PROFIT_LOSS',active=True)
        self.s.add_all([first,other]);self.s.flush();self.why.accounting_classification_id=first.id
        self.decide(self.txns[0],self.oldwho.id,self.why.id);self.s.commit();self.for_whom(self.txns[0]);draft=self.prepare(self.txns[0])
        result=self.post('/bank/ai-rules/chat/decision',confirmation_token=draft['confirmation_token'],action='FUTURE');self.assertEqual(result.status_code,200,result.get_json())
        self.s.expire_all();self.why.accounting_classification_id=other.id;self.s.commit()
        txn=self.new();ops.apply_to_new_transaction(self.s,txn,ops.import_context(self.s));self.s.commit()
        e=self.s.get(m.BankTransactionExplanation,txn.explanation_id);self.assertEqual(e.accounting_classification_id,first.id)
        self.assertEqual(e.accounting_destination_source,m.DESTINATION_SOURCE_TRANSACTION)

    def test_note_and_direction_distinguish_repeated_payments(self):
        self.txns[0].source_memo='TIP for service';self.s.commit();self.for_whom(self.txns[0])
        response=self.post(f'/bank/ai-rules/capture/{self.txns[0].id}',pattern='SYNTHETIC RULE TEST',match_op='contains',memo_pattern='TIP')
        self.assertEqual(response.status_code,200,response.get_json());draft=response.get_json()
        self.assertEqual(self.post('/bank/ai-rules/chat/decision',confirmation_token=draft['confirmation_token'],action='FUTURE').status_code,200)
        self.s.expire_all();hit=self.new();hit.source_memo='TIP another date';ops.apply_to_new_transaction(self.s,hit,ops.import_context(self.s))
        miss=self.new();miss.source_memo='Invoice';ops.apply_to_new_transaction(self.s,miss,ops.import_context(self.s));self.s.commit()
        self.assertIsNotNone(hit.explanation_id);self.assertIsNone(miss.explanation_id)

    def test_conflicting_equally_specific_photos_are_ambiguous(self):
        self.rule.apply_future=True;self.s.commit()
        text='If description contains "SYNTHETIC RULE TEST", WHO is "OLD WHO" and WHY is "Old reason".'
        raw=dict(kind='STRUCTURED',conditions=[dict(field='description',op='contains',value='SYNTHETIC RULE TEST')],who=dict(mode='fixed',name='OLD WHO'),why=dict(mode='fixed',name='Old reason'),coverage=[dict(instruction='all',represented_by='conditions WHO WHY')])
        ops.save_rule(self.s,rule_id=None,rule_text=text,create_missing_who=False,apply_future=True,origin_transaction_id=self.txns[0].id,account_id=None,generate=lambda _:raw)
        self.s.commit();txn=self.new();ops.apply_to_new_transaction(self.s,txn,ops.import_context(self.s));self.s.commit()
        self.assertIsNone(txn.explanation_id)
        job=self.s.scalar(select(m.BankImportReconciliation));self.assertEqual(job.status,'AMBIGUOUS')

    def test_each_photo_in_a_compatible_import_application_has_guarded_rollback(self):
        self.rule.apply_future=True
        text=self.text+' WHOM "Entity One".'
        raw=self.generate('');raw['for_whom']=dict(mode='fixed',entity='Entity One')
        saved=ops.save_rule(self.s,rule_id=None,rule_text=text,create_missing_who=False,apply_future=True,origin_transaction_id=self.txns[0].id,account_id=None,generate=lambda _:raw)
        rid=saved.rule.id;self.s.commit();txn=self.new();context=ops.import_context(self.s)
        ops.apply_to_new_transaction(self.s,txn,context);ops.finish_import(context);self.s.commit()
        app=self.s.scalar(select(m.BankAiRuleApplication).where(m.BankAiRuleApplication.rule_id==rid,m.BankAiRuleApplication.mode=='IMPORT'))
        self.assertTrue(safety.serialize_application(app)['can_rollback'])
        result=safety.rollback_application(self.s,app.id);self.s.commit();self.assertEqual(result['restored'],1)
        self.s.refresh(txn);self.assertIsNone(self.s.get(m.BankTransactionExplanation,txn.explanation_id).occurrence_id)

    def test_capture_refuses_missing_values_and_later_edits(self):
        self.assertEqual(self.client.get(f'/bank/ai-rules/capture/{self.txns[2].id}',headers=self.headers).status_code,409)
        self.for_whom(self.txns[0]);draft=self.prepare(self.txns[0]);self.decide(self.txns[0],self.newwho.id,self.newwhy.id);self.s.commit()
        result=self.post('/bank/ai-rules/chat/decision',confirmation_token=draft['confirmation_token'],action='FUTURE');self.assertEqual(result.status_code,409)

    def test_job_claim_lease_and_idempotent_reconcile(self):
        t=self.new();ops.apply_to_new_transaction(self.s,t,None);ops.apply_to_new_transaction(self.s,t,None);self.s.commit()
        import bank_import_worker as worker
        factory=sessionmaker(self.engine);jid=worker.claim(factory);self.assertIsNotNone(jid);self.assertIsNone(worker.claim(factory))
        self.s.expire_all();job=self.s.get(m.BankImportReconciliation,jid);job.lease_until=datetime.now(timezone.utc)-timedelta(minutes=1);self.s.commit()
        self.assertEqual(worker.claim(factory),jid);self.assertEqual(len(list(self.s.scalars(select(m.BankImportReconciliation)))),1)

if __name__=='__main__':unittest.main()
