"""Profile composer scopes: exact preview publication and guarded rollback."""
from pathlib import Path
import sys,json,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'RF-One Web'))
import bank_flow_routes
from test_bank_flow_v2 import FlowTests
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import ai_rule_operations as ops,rule_application_safety as safety
from sqlalchemy import select,func

class SaveControls(unittest.TestCase):
 setUp=FlowTests.setUp;tearDown=FlowTests.tearDown;post=FlowTests.post;state=FlowTests.state;decide=FlowTests.decide
 research_fixture=FlowTests.research_fixture;saved=FlowTests.saved;photo=FlowTests.photo
 def prepare(self,guided=True):
  self.what,_,_=self.research_fixture();self.rid=self.saved(self.photo())
  self.txns[1].explanation_id=None;self.s.commit()
  self.before=self.state();self.count=self.s.scalar(select(func.count()).select_from(m.BankAiRule))
  self.run=None
  if guided:
   self.run=self.post('/bank/flow/runs').get_json()
   while self.run['phase']=='AUTO':self.run=self.post(f"/bank/flow/runs/{self.run['id']}/auto").get_json()
   self.run=self.post(f"/bank/flow/runs/{self.run['id']}/next").get_json();tid=self.run['current_id']
  else:tid=self.txns[2].id
  self.tid=tid
  r=self.post('/bank/flow/conversation',kind='PHOTO',transaction_id=tid,**({'run_id':self.run['id']} if guided else {}));self.assertEqual(r.status_code,200,r.get_json());self.chat=r.get_json()
  if not self.chat.get('research'):
   with patch('bank_profile_research.research',return_value=dict(probable_who='OLD WHO',summary='Test',sources=[],proposals=[])):
    self.post(f"/bank/flow/conversation/{self.chat['id']}/research",mode='transaction')
  r=self.post(f"/bank/flow/conversation/{self.chat['id']}/research/choices",who='OLD WHO',why_ids=json.dumps([self.why.id]),what_ids=json.dumps([self.what.id]));self.assertEqual(r.status_code,200,r.get_json());self.chat=r.get_json()
 def preview(self,scope):
  r=self.post(f"/bank/flow/conversation/{self.chat['id']}/preview",scope=scope);self.assertEqual(r.status_code,200,r.get_json());return r.get_json()
 def save(self,p,scope):return self.post(f"/bank/flow/conversation/{self.chat['id']}/save",preview_id=p['id'],action=scope)
 def test_current_scope_and_profile_persistence(self):
  self.prepare();p=self.preview('CURRENT');self.assertEqual([r['transaction_id'] for r in p['rows']],[self.tid]);self.assertEqual(self.state(),self.before)
  r=self.save(p,'CURRENT');self.assertEqual(r.status_code,200,r.get_json());self.assertEqual(r.get_json()['updated'],1);self.assertEqual(r.get_json()['rule_id'],self.rid)
  self.s.expire_all();self.assertEqual(self.s.scalar(select(func.count()).select_from(m.BankAiRule)),self.count)
  version=ops.current_version(self.s.get(m.BankAiRule,self.rid));self.assertEqual(version.version_no,2);self.assertEqual(json.loads(version.spec),self.chat['spec'])
  reopened=self.post('/bank/flow/conversation',rule_id=self.rid).get_json();self.assertEqual(reopened['previous_spec'],self.chat['spec'])
  after=self.state();self.assertEqual(after[0],self.before[0]);self.assertEqual(sum(a!=b for a,b in zip(after,self.before)),1)
 def test_all_scope_pending_only_same_description_same_source_and_rollback(self):
  self.prepare();p=self.preview('ALL');self.assertEqual({r['transaction_id'] for r in p['rows']},{self.txns[1].id,self.txns[2].id});self.assertEqual(self.state(),self.before)
  r=self.save(p,'ALL');self.assertEqual(r.status_code,200,r.get_json());self.assertEqual(r.get_json()['updated'],2);self.assertEqual(r.get_json()['rule_id'],self.rid)
  run=self.post(f"/bank/flow/runs/{self.run['id']}/next").get_json();self.assertEqual(run['phase'],'COMPLETE');self.assertEqual(run['updated'],2)
  self.s.expire_all();self.assertEqual(self.s.scalar(select(func.count()).select_from(m.BankAiRule)),self.count);self.assertEqual(self.state()[0],self.before[0])
  self.decide(self.txns[1],self.newwho.id,self.newwhy.id);self.s.commit();later=self.state()[1]
  undo=self.post(f"/bank/flow/runs/{self.run['id']}/rollback");self.assertEqual(undo.status_code,200,undo.get_json());self.assertEqual(undo.get_json()['restored'],1);self.assertEqual(len(undo.get_json()['skipped']),1);self.assertEqual(self.state()[1],later)
 def test_scope_cannot_be_changed_after_preview(self):
  self.prepare();p=self.preview('CURRENT');r=self.save(p,'ALL');self.assertEqual(r.status_code,409);self.assertEqual(self.state(),self.before);self.assertEqual(ops.current_version(self.s.get(m.BankAiRule,self.rid)).version_no,1)
 def test_stop_blocks_repository_save(self):
  self.prepare();p=self.preview('ALL');self.post(f"/bank/flow/runs/{self.run['id']}/stop");self.assertEqual(self.save(p,'ALL').status_code,409);self.assertEqual(self.state(),self.before)
 def test_newly_reconciled_row_blocks_repository_save(self):
  self.prepare();p=self.preview('ALL');self.decide(self.txns[2],self.newwho.id,self.newwhy.id);self.s.commit();changed=self.state();self.assertEqual(self.save(p,'ALL').status_code,409);self.assertEqual(self.state(),changed)
 def test_current_scope_without_run(self):
  self.prepare(guided=False);p=self.preview('CURRENT');self.assertEqual(len(p['rows']),1);r=self.save(p,'CURRENT');self.assertEqual(r.status_code,200,r.get_json());self.assertEqual(r.get_json()['updated'],1);self.assertEqual(self.state()[:2],self.before[:2])
 def test_similar_description_other_source_is_not_assumed_same_who(self):
  self.prepare();instrument=m.PaymentInstrument(instrument_type='BANK_ACCOUNT',display_name='Other source',currency='USD',status='ACTIVE');self.s.add(instrument);self.s.flush();next(t for t in self.txns[1:] if t.id!=self.tid).payment_instrument_id=instrument.id;self.s.commit();p=self.preview('ALL');self.assertEqual([r['transaction_id'] for r in p['rows']],[self.tid])
 def test_chat_instruction_is_saved_as_exact_previewed_definition(self):
  self.prepare();spec={**self.chat['spec'],'branches':[dict(conditions=[dict(field='description',op='is',value='SYNTHETIC RULE TEST')],why_id=self.why.id,destination_id=self.what.id,mode='CODE')]}
  reply='For SYNTHETIC RULE TEST use the chosen WHY and WHAT. WHOM follows Source.'
  with patch('bank_chatgpt.generate_json',return_value=dict(ready=True,title='OLD WHO',reply=reply,spec=spec)):
   r=self.post(f"/bank/flow/conversation/{self.chat['id']}",message='Use this only for this exact description.');self.assertEqual(r.status_code,200,r.get_json())
  p=self.preview('ALL');self.assertEqual(p['definition_text'],reply);r=self.save(p,'ALL');self.assertEqual(r.status_code,200,r.get_json());self.s.expire_all();v=ops.current_version(self.s.get(m.BankAiRule,self.rid));self.assertEqual(v.rule_text,reply);self.assertEqual(json.loads(v.spec),spec)

if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SaveControls));sys.exit(not result.wasSuccessful())
