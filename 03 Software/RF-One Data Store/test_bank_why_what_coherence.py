"""Recognition-profile editor: WHAT derives from WHY. An incoherent WHY/WHAT pair is refused by the server."""
from pathlib import Path
import sys,json,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'RF-One Web'))
import test_bank_flow_v2
FlowTests=test_bank_flow_v2.FlowTests

class WhyWhatCoherence(FlowTests):
 """The FlowTests fixture (synthetic, disposable database); only the tests below run (load_tests)."""
 def chat(self):
  self.what,self.other,_=self.research_fixture()
  r=self.post('/bank/flow/conversation',kind='PHOTO',transaction_id=self.txns[2].id);self.assertEqual(r.status_code,200,r.get_json());chat=r.get_json()
  if not chat.get('research'):
   with patch('bank_profile_research.research',return_value=dict(probable_who='OLD WHO',summary='Test',sources=[],proposals=[])):
    self.post(f"/bank/flow/conversation/{chat['id']}/research",mode='transaction')
  return chat
 def choose(self,chat,why,what):
  return self.post(f"/bank/flow/conversation/{chat['id']}/research/choices",who='OLD WHO',why_ids=json.dumps(why),what_ids=json.dumps(what))
 def test_incoherent_pair_is_refused_and_nothing_changes(self):
  chat=self.chat();before=self.state()
  r=self.choose(chat,[self.why.id],[self.other.id])
  self.assertEqual(r.status_code,409,r.get_json());self.assertIn('WHAT derives from WHY',r.get_json()['error'])
  self.assertEqual(self.state(),before)
 def test_coherent_pair_is_accepted(self):
  chat=self.chat();r=self.choose(chat,[self.why.id],[self.what.id]);self.assertEqual(r.status_code,200,r.get_json())
 def test_two_whys_accept_their_own_whats_only(self):
  chat=self.chat()
  self.assertEqual(self.choose(chat,[self.why.id,self.newwhy.id],[self.what.id,self.other.id]).status_code,200)

def load_tests(loader,tests,pattern):
 return unittest.TestSuite(WhyWhatCoherence(n) for n in ('test_incoherent_pair_is_refused_and_nothing_changes','test_coherent_pair_is_accepted','test_two_whys_accept_their_own_whats_only'))

if __name__=='__main__':unittest.main()
