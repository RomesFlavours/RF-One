"""Pending-only reconciliation and historical proposal regressions."""
import json,sys,unittest
from unittest.mock import patch
from sqlalchemy import select,func
import test_bank_flow_v2 as fixture
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import flow,rule_application_safety as safety,reconciliation_runner as runner

class PendingFix(unittest.TestCase):
 setUp=fixture.FlowTests.setUp
 tearDown=fixture.FlowTests.tearDown
 decide=fixture.FlowTests.decide
 post=fixture.FlowTests.post
 state=fixture.FlowTests.state
 photo=fixture.FlowTests.photo
 extractor=fixture.FlowTests.extractor
 saved=fixture.FlowTests.saved
 research_fixture=fixture.FlowTests.research_fixture
 def start(self,tid=None):
  r=self.post('/bank/flow/runs',**({'transaction_id':tid} if tid else {}));self.assertEqual(r.status_code,200,r.get_json());run=r.get_json()
  while run['phase']=='AUTO':run=self.action(run,'auto')
  return run
 def action(self,run,action):
  r=self.post(f"/bank/flow/runs/{run['id']}/{action}");self.assertEqual(r.status_code,200,r.get_json());return r.get_json()
 def test_queue_and_single_protect_historical_who_even_without_what(self):
  before=self.state();self.assertEqual([t.id for t in runner.pending(self.s)],[self.txns[2].id])
  r=self.post('/bank/flow/runs',transaction_id=self.txns[0].id);self.assertEqual(r.status_code,409)
  run=self.start();self.assertEqual(run['ids'],[self.txns[2].id]);self.assertEqual(self.state(),before)
 def test_zero_changes_goes_directly_to_guided_history_without_web(self):
  self.research_fixture();run=self.start();self.assertEqual(run['phase'],'GUIDED');run=self.action(run,'next')
  with patch('bank_profile_research.research',side_effect=AssertionError('No web before history')):
   r=self.post('/bank/flow/conversation',kind='PHOTO',transaction_id=self.txns[2].id,run_id=run['id'])
  self.assertEqual(r.status_code,200,r.get_json());chat=r.get_json();self.assertEqual(chat['research']['probable_who'],'OLD WHO');self.assertTrue(chat['history']);self.assertEqual(chat['research']['proposals'][0]['why_id'],self.why.id)
 def test_automatic_preview_applies_only_unresolved_and_rollback(self):
  self.research_fixture();self.oldwho.default_transaction_reason_id=self.why.id
  self.txns[2].description_original='Zelle payment to OLD WHO 123456';self.s.commit();self.saved(self.extractor())
  before=self.state();run=self.start();self.assertEqual(run['phase'],'PREVIEW');self.assertEqual(run['ids'],[self.txns[2].id]);self.assertEqual(self.state(),before)
  run=self.action(run,'apply');self.assertEqual(run['phase'],'COMPLETE');after=self.state();self.assertEqual(before[:2],after[:2]);self.assertEqual(runner.pending(self.s),[])
  undo=self.action(run,'rollback');self.assertEqual(undo['restored'],1)
 def test_core_and_import_refuse_resolved_row(self):
  self.research_fixture();before=self.state();p=runner.plan(self.s,self.txns[0]);self.assertIsNone(p['choice'])
  with self.assertRaisesRegex(ValueError,'already reconciled'):runner.apply(self.s,self.txns[0],{},1)
  self.assertFalse(runner.imported(self.s,self.txns[0],flow.entries(self.s)));self.s.commit();self.assertEqual(before,self.state())
 def test_history_accepts_changed_zelle_reference_and_ach_preserves_purpose(self):
  self.research_fixture();self.txns[0].description_original='Zelle payment to OLD WHO JPM99old123';self.txns[2].description_original='Zelle payment to OLD WHO JPM99new456';self.s.commit()
  before=self.state();h=runner.history(self.s,self.txns[2]);self.assertEqual(h[0]['who'],'OLD WHO');self.assertEqual(h[0]['destination_id'],self.why.accounting_classification_id);self.assertEqual(self.state(),before)
  self.assertNotEqual(runner.history_key('ORIG CO NAME:OLD WHO ORIG ID:123 CO ENTRY DESCR:DEPOSIT SEC:CCD'),runner.history_key('ORIG CO NAME:OLD WHO ORIG ID:456 CO ENTRY DESCR:CHARGE SEC:CCD'))
 def test_guided_save_updates_same_photo_and_advances_with_protection(self):
  what,_,_=self.research_fixture();rid=self.saved(self.photo());n=self.s.scalar(select(func.count()).select_from(m.BankAiRule));run=self.start();run=self.action(run,'next');tid=run['current_id']
  chat=self.post('/bank/flow/conversation',kind='PHOTO',transaction_id=tid,run_id=run['id']).get_json();self.assertTrue(chat['research'])
  r=self.post(f"/bank/flow/conversation/{chat['id']}/research/choices",who='OLD WHO',why_ids=json.dumps([self.why.id]),what_ids=json.dumps([what.id]));self.assertEqual(r.status_code,200,r.get_json())
  p=self.post(f"/bank/flow/conversation/{chat['id']}/preview");self.assertEqual(p.status_code,200,p.get_json());before=self.state()
  r=self.post(f"/bank/flow/conversation/{chat['id']}/save",preview_id=p.get_json()['id'],action='CURRENT');self.assertEqual(r.status_code,200,r.get_json());self.assertEqual(r.get_json()['rule_id'],rid)
  after=self.state();self.assertEqual(before[:2],after[:2]);self.assertNotEqual(before[2],after[2]);self.s.expire_all();self.assertEqual(self.s.scalar(select(func.count()).select_from(m.BankAiRule)),n)
  self.assertEqual(self.action(run,'next')['phase'],'COMPLETE')
 def test_stop_blocks_late_research(self):
  self.research_fixture();self.txns[2].description_original='No historical match';self.s.commit();run=self.start();run=self.action(run,'next');chat=self.post('/bank/flow/conversation',kind='PHOTO',transaction_id=self.txns[2].id,run_id=run['id']).get_json()
  def late(**kwargs):self.action(run,'stop');return dict(probable_who='OLD WHO',sources=[],proposals=[],summary='Late')
  before=self.state()
  with patch('bank_profile_research.research',side_effect=late):r=self.post(f"/bank/flow/conversation/{chat['id']}/research",mode='transaction')
  self.assertEqual(r.status_code,409);self.assertEqual(before,self.state())
 def test_reconciled_after_preview_is_not_overwritten(self):
  self.research_fixture();self.oldwho.default_transaction_reason_id=self.why.id;self.txns[2].description_original='Zelle payment to OLD WHO 123456';self.s.commit();self.saved(self.extractor());run=self.start()
  self.decide(self.txns[2],self.newwho.id,self.newwhy.id);self.s.commit();before=self.state();r=self.post(f"/bank/flow/runs/{run['id']}/apply");self.assertEqual(r.status_code,409);self.assertEqual(before,self.state())

if __name__=='__main__':
 r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PendingFix));sys.exit(not r.wasSuccessful())
