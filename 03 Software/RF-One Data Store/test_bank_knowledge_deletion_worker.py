import unittest
from sqlalchemy import select
from test_bank_import_pipeline import ImportPipeline as Pipeline
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import ai_rule_operations as ops

class KnowledgeDeletionWorker(unittest.TestCase):
    setUp=Pipeline.setUp
    tearDown=Pipeline.tearDown
    decide=Pipeline.decide
    new=Pipeline.new
    run_worker=Pipeline.run_worker
    findings=Pipeline.findings
    post=Pipeline.post

    def test_deletion_during_research_cannot_recreate_card(self):
        txn=self.new('NEW WHO payment');self.decide(txn,self.newwho.id,None)
        ops.apply_to_new_transaction(self.s,txn,None);self.s.commit()
        def research(*args):
            response=self.post(f'/bank/ai-rules/who/{self.newwho.id}/manage',action='delete')
            self.assertEqual(response.status_code,200)
            return self.findings(*args)
        job=self.run_worker(research_fn=research)
        self.assertEqual(job.status,'PROPOSED',job.last_error)
        card=self.s.scalar(select(m.BankWhoKnowledge).where(m.BankWhoKnowledge.occurrence_id==self.newwho.id))
        self.assertIsNotNone(card.deleted_at);self.assertEqual(card.summary,'');self.assertEqual(card.sources_json,'[]')

if __name__=='__main__':unittest.main()
