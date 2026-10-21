"""Profile preview and confirmation with a missing Source owner."""
import unittest,json,sys
from sqlalchemy import select
import test_bank_profile_save_scope as fixtures
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import flow,ai_rule_operations as ops,rule_application_safety as safety
allocation=flow.allocation
class MissingWhom(fixtures.SaveControls):
 def make_ownerless(self):
  self.prepare();i=self.s.get(m.PaymentInstrument,self.txns[2].payment_instrument_id);i.legal_entity_id=None;i.owner_reporting_entity_id=None;self.s.commit()
 def test_missing_whom_is_visible_and_cannot_publish(self):
  self.make_ownerless();before=self.state();p=self.preview('CURRENT');self.assertFalse(p['can_apply']);r=p['rows'][0];self.assertEqual(r['after']['who'],'OLD WHO');self.assertEqual(r['missing_fields'],['WHOM']);self.assertIsNone(r['choice']);self.assertEqual(r['after']['whom'],None)
  response=self.save(p,'CURRENT');self.assertEqual(response.status_code,409);self.assertEqual(before,self.state());self.s.expire_all();self.assertEqual(ops.current_version(self.s.get(m.BankAiRule,self.rid)).version_no,1)
 def test_manual_whom_only_current_persists_and_rollback_preserves_later_edits(self):
  self.make_ownerless();before=self.state();p=self.post(f"/bank/flow/conversation/{self.chat['id']}/preview",scope='ALL',current_whom_id=self.entity2.id).get_json();self.assertTrue(p['can_apply']);self.assertEqual(p['reconcilable'],1);self.assertEqual(before,self.state())
  other=next(r for r in p['rows'] if r['transaction_id']!=self.tid);self.assertIsNone(other['choice'])
  result=self.save(p,'ALL');self.assertEqual(result.status_code,200,result.get_json());self.assertEqual(result.get_json()['updated'],1);self.s.expire_all()
  a=self.s.scalar(select(m.BankTransactionAllocation).where(m.BankTransactionAllocation.financial_transaction_id==self.tid));self.assertEqual(a.reporting_entity_id,self.entity2.id);self.assertEqual(a.decision_source,'HUMAN')
  v=ops.current_version(self.s.get(m.BankAiRule,self.rid));self.assertEqual(json.loads(v.spec)['whom_mode'],'SOURCE');self.assertEqual(v.version_no,2)
  a.notes='Later human change';self.s.commit();after=self.state();self.post(f"/bank/flow/runs/{self.run['id']}/stop");r=self.post(f"/bank/flow/runs/{self.run['id']}/rollback").get_json();self.assertEqual(r['restored'],0,r);self.assertEqual(len(r['skipped']),1);self.assertEqual(after,self.state())
 def test_invalid_whom_rejected_and_preview_selection_can_be_cleared(self):
  self.make_ownerless();before=self.state();url=f"/bank/flow/conversation/{self.chat['id']}/preview"
  self.assertEqual(self.post(url,scope='CURRENT',current_whom_id=9999999).status_code,409)
  self.assertTrue(self.post(url,scope='CURRENT',current_whom_id=self.entity.id).get_json()['can_apply'])
  self.assertFalse(self.post(url,scope='CURRENT',current_whom_id='').get_json()['can_apply']);self.assertEqual(before,self.state())
 def test_manual_whom_does_not_collapse_split_allocations(self):
  self.make_ownerless();txn=self.s.get(m.FinancialTransaction,self.tid);n=txn.amount_minor//2
  allocation.set_allocations(self.s,financial_transaction_id=self.tid,specs=[allocation.AllocationSpec(amount_minor=n,reporting_entity_id=self.entity.id,status=allocation.NEEDS_OPERATOR),allocation.AllocationSpec(amount_minor=txn.amount_minor-n,reporting_entity_id=self.entity2.id,status=allocation.NEEDS_OPERATOR)]);self.s.commit()
  # Open a fresh conversation because the old transaction snapshot must be invalidated.
  rec=self.s.get(m.BankFlowArtifact,self.chat['id']);data=json.loads(rec.payload);data['research_transaction_state']=safety.snapshot(self.s,txn);rec.payload=json.dumps(data);self.s.commit();before=self.state()
  p=self.post(f"/bank/flow/conversation/{self.chat['id']}/preview",scope='CURRENT',current_whom_id=self.entity.id).get_json();self.assertFalse(p['can_apply']);self.assertIn('split',p['rows'][0]['note']);self.assertEqual(before,self.state())


if __name__=='__main__':unittest.main()
