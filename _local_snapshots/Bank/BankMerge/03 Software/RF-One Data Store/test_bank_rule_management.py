import unittest
from unittest.mock import patch
from sqlalchemy import select
from test_bank_conversation_workflow import ConversationWorkflow as Workflow
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import ai_rule_operations as operations

class RuleManagement(unittest.TestCase):
    setUp=Workflow.setUp
    tearDown=Workflow.tearDown
    post=Workflow.post
    context=Workflow.context
    state=Workflow.state
    decide=Workflow.decide

    def snapshot(self):
        return self.client.get('/bank/ai-rules/snapshot',headers=self.headers).get_json()

    def test_rename_both_rule_groups_changes_only_label(self):
        before=self.state()
        for kind in ('GENERAL','RECOGNITION'):
            self.rule.organization_kind=kind;self.s.commit()
            version=operations.current_version(self.s.get(m.BankAiRule,self.rule.id)).id
            response=self.post(f'/bank/ai-rules/rules/{self.rule.id}/title',user_title='  Nome nuovo  ')
            self.assertEqual(response.status_code,200,response.get_json())
            self.s.expire_all()
            rule=self.s.get(m.BankAiRule,self.rule.id)
            self.assertEqual(rule.user_title,'Nome nuovo')
            self.assertEqual(operations.current_version(rule).id,version)
            self.assertEqual(self.state(),before)

    def test_delete_both_rule_groups_removes_future_and_rejects_stale_save(self):
        before=self.state();context=self.context(rule_id=self.rule.id)
        response=self.post(f'/bank/ai-rules/rules/{self.rule.id}/delete',response_format='json')
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertNotIn(self.rule.id,[r['id'] for r in self.snapshot()['learned_rules']])
        self.s.expire_all();rule=self.s.get(m.BankAiRule,self.rule.id)
        self.assertIsNotNone(rule.deleted_at);self.assertFalse(rule.apply_future)
        stale=self.post('/bank/ai-rules/chat/decision',confirmation_token=context['confirmation_token'],action='FUTURE')
        self.assertNotEqual(stale.status_code,200)
        self.assertEqual(self.state(),before)

    def test_who_rename_delete_persists_without_renaming_counterparty(self):
        before=self.state();wid=self.oldwho.id
        path=f'/bank/ai-rules/who/{wid}/manage'
        self.assertEqual(self.post(path,action='rename',title='Mia scheda').status_code,200)
        card=next(k for k in self.snapshot()['knowledge'] if k['who_id']==wid)
        self.assertEqual(card['title'],'Mia scheda');self.assertEqual(card['who'],'OLD WHO')
        self.assertEqual(self.post(path,action='delete').status_code,200)
        self.assertNotIn(wid,[k['who_id'] for k in self.snapshot()['knowledge']])
        with patch('bank_chatgpt.generate_json',side_effect=AssertionError('No research on deleted card')):
            self.assertEqual(self.post(f'/bank/ai-rules/who/{wid}/research').status_code,404)
        self.assertEqual(self.post(path,action='rename',title='Resurrect').status_code,404)
        self.s.expire_all();card=self.s.scalar(select(m.BankWhoKnowledge).where(m.BankWhoKnowledge.occurrence_id==wid))
        self.assertEqual(card.summary,'');self.assertEqual(card.sources_json,'[]');self.assertIsNotNone(card.deleted_at)
        self.assertEqual(self.s.get(m.BankOccurrence,wid).canonical_name,'OLD WHO');self.assertEqual(self.state(),before)

    def test_delete_keeps_history_and_guarded_rollback(self):
        c=self.context(rule_id=self.rule.id)
        p=self.post('/bank/ai-rules/chat/decision',confirmation_token=c['confirmation_token'],action='PAST_AND_FUTURE').get_json()
        applied=self.post('/bank/ai-rules/chat/apply',confirmation_token=c['confirmation_token'],preview_id=p['preview_id']).get_json()
        aid=applied['application']['application_id']
        self.assertEqual(self.post(f'/bank/ai-rules/rules/{self.rule.id}/delete',response_format='json').status_code,200)
        history=self.client.get(f'/bank/ai-rules/rules/{self.rule.id}/applications',headers=self.headers)
        self.assertEqual(history.status_code,200);self.assertTrue(history.get_json()['applications'][0]['can_rollback'])
        self.s.expire_all();self.decide(self.txns[1],self.oldwho.id,self.why.id);self.s.commit()
        undone=self.post(f'/bank/ai-rules/applications/{aid}/rollback').get_json()
        self.assertEqual(undone['restored'],2);self.assertEqual(len(undone['skipped']),1)

    def test_management_requires_auth_csrf_and_valid_input(self):
        for path,data in [(f'/bank/ai-rules/rules/{self.rule.id}/title',{'user_title':'X'}),
                          (f'/bank/ai-rules/rules/{self.rule.id}/delete',{'response_format':'json'}),
                          (f'/bank/ai-rules/who/{self.oldwho.id}/manage',{'action':'delete'})]:
            self.assertEqual(self.client.post(path,data=data,headers=self.headers).status_code,400)
            self.assertEqual(self.client.post(path,data={'csrf_token':'test-csrf',**data}).status_code,401)
        self.assertEqual(self.post(f'/bank/ai-rules/who/{self.oldwho.id}/manage',action='rename',title=' ').status_code,400)

if __name__=='__main__':unittest.main()
