"""Synthetic workflow checks: no identity write before a complete photo."""
import json,unittest
from unittest.mock import patch
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
import test_bank_conversation_workflow as fixtures
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import flow,ai_rule_operations as ops,rule_application_safety as safety,reconciliation_status

class FlowTests(unittest.TestCase):
    def setUp(self):
        fixtures.ConversationWorkflow.setUp(self)
        self.app.testing=True
    tearDown=fixtures.ConversationWorkflow.tearDown
    decide=fixtures.ConversationWorkflow.decide
    post=fixtures.ConversationWorkflow.post
    state=fixtures.ConversationWorkflow.state

    def extractor(self):
        return dict(engine=flow.ENGINE,kind='EXTRACTOR',prefix='Zelle payment to',start='Zelle payment to',end_mode='last_code')

    def photo(self,**extra):
        return dict(engine=flow.ENGINE,kind='PHOTO',who='OLD WHO',aliases=[],allowed_why_ids=[self.why.id,self.newwhy.id],allowed_whom_ids=[self.entity.id,self.entity2.id],
            branches=[dict(conditions=[],why_id=self.why.id,whom_id=self.entity.id)],requirements=[],unresolved=[],**extra)

    def saved(self,spec,future=True):
        r=m.BankAiRule(title='Synthetic policy',status='ACTIVE',organization_kind='GENERAL' if spec['kind']=='EXTRACTOR' else 'RECOGNITION',apply_future=future)
        self.s.add(r);self.s.flush()
        v=m.BankAiRuleVersion(rule_id=r.id,version_no=1,rule_text='Synthetic human-approved policy',method='CODE',spec=json.dumps(spec),create_missing_who=False,override_protected=True)
        self.s.add(v);self.s.commit();return r.id

    def prepare(self,spec):
        response=self.post('/bank/flow/conversation',kind=spec['kind'])
        self.assertEqual(response.status_code,200,response.get_json());id=response.get_json()['id']
        answer=dict(ready=True,reply='Istruzione chiara e pronta da verificare.',title='Human validated',spec=spec)
        with patch('bank_chatgpt.generate_json',return_value=answer):
            response=self.post(f'/bank/flow/conversation/{id}',message='Definisci esattamente questi casi.')
        self.assertEqual(response.status_code,200,response.get_json());self.assertTrue(response.get_json()['ready']);return id

    def test_discovery_deduplicates_equivalent_specs_and_preserves_variants(self):
        import bank_flow_routes as routes
        base=self.extractor();equivalent={**base,'exclude':[],'suffix_policy':'none','numeric_name_exceptions':[]}
        variant={**base,'suffix_policy':'dates'}
        rows=[dict(title='First',spec=base),dict(title='Same format',spec=equivalent),dict(title='Variant',spec=variant)]
        unique=routes.unique_formats(rows)
        self.assertEqual([x['index'] for x in unique],[0]);self.assertEqual(len(unique[0]['variants']),2)
        self.assertEqual(routes.extractor_key(base),routes.extractor_key(equivalent))
        self.assertNotEqual(routes.extractor_key(base),routes.extractor_key(variant))
        response=self.post('/bank/flow/discover');scan=response.get_json()['id']
        routes.discovery(sessionmaker(self.engine),scan,generate=lambda _:dict(formats=[dict(title=x['title'],reply='Extract name',spec=x['spec']) for x in rows]))
        result=self.client.get(f'/bank/flow/discover/{scan}',headers=self.headers).get_json()
        self.assertEqual(len(result['formats']),1)
        chat=self.post('/bank/flow/conversation',scan_id=scan,index=result['formats'][0]['index'],kind='EXTRACTOR').get_json()
        self.assertEqual(self.post(f"/bank/flow/conversation/{chat['id']}/discard").status_code,200)
        remaining=self.client.get(f'/bank/flow/discover/{scan}',headers=self.headers).get_json()['formats']
        self.assertEqual(len(remaining),0)
        self.assertEqual(self.client.get(f"/bank/flow/conversation/{chat['id']}",headers=self.headers).status_code,409)

    def test_duplicate_creation_is_blocked_and_deleted_rules_stop_matching(self):
        spec=self.extractor();rid=self.saved(spec);before=self.state()
        chat=self.prepare({**spec,'suffix_policy':'none','exclude':[]})
        preview=self.post(f'/bank/flow/conversation/{chat}/preview').get_json()
        response=self.post(f'/bank/flow/conversation/{chat}/save',preview_id=preview['id'],action='FUTURE')
        self.assertEqual(response.status_code,409);self.assertIn('already exists',response.get_json()['error'])
        self.s.expire_all();self.assertEqual(self.s.scalar(select(m.BankAiRule).where(m.BankAiRule.title=='Human validated')),None)
        ops.delete_rule(self.s,rule_id=rid,account_id=None);self.s.commit()
        self.assertNotIn(rid,[r.id for r,_,_ in flow.entries(self.s)])
        self.assertEqual(self.state(),before)
        self.assertEqual(self.post('/bank/flow/conversation',rule_id=rid).status_code,409)

    def test_unlinked_discovery_refinement_updates_existing_rule_without_a_copy(self):
        import bank_flow_routes as routes
        base=self.extractor();rid=self.saved(base);rule_count=len(list(self.s.scalars(select(m.BankAiRule))))
        scan=self.post('/bank/flow/discover').get_json()['id'];draft={**base,'suffix_policy':'dates'}
        with sessionmaker(self.engine)() as db:
            record=db.get(m.BankFlowArtifact,scan);record.payload=json.dumps(dict(formats=[dict(title='Refined format',reply='Remove final dates.',spec=draft)]));db.commit()
        chat=self.post('/bank/flow/conversation',scan_id=scan,index=0,kind='EXTRACTOR').get_json()
        self.assertEqual(chat['rule_id'],rid)
        self.post(f"/bank/flow/conversation/{chat['id']}/draft",pending_message='')
        preview=self.post(f"/bank/flow/conversation/{chat['id']}/preview").get_json()
        response=self.post(f"/bank/flow/conversation/{chat['id']}/save",preview_id=preview['id'],action='FUTURE')
        self.assertEqual(response.status_code,200,response.get_json());self.assertEqual(response.get_json()['rule_id'],rid)
        with sessionmaker(self.engine)() as db:
            self.assertEqual(len(list(db.scalars(select(m.BankAiRule)))),rule_count)
            self.assertEqual(ops.current_version(db.get(m.BankAiRule,rid)).version_no,2)
            self.assertEqual(flow.unpack(ops.current_version(db.get(m.BankAiRule,rid))),draft)

    def test_ambiguous_existing_formats_require_explicit_update_target(self):
        import bank_flow_routes as routes
        base=self.extractor();first=self.saved(base);second=self.saved({**base,'suffix_policy':'dates'});rule_count=len(list(self.s.scalars(select(m.BankAiRule))))
        scan=self.post('/bank/flow/discover').get_json()['id']
        with sessionmaker(self.engine)() as db:
            record=db.get(m.BankFlowArtifact,scan);record.payload=json.dumps(dict(formats=[dict(title='Format',reply='Extract names.',spec=base)]));db.commit()
        chat=self.post('/bank/flow/conversation',scan_id=scan,index=0,kind='EXTRACTOR').get_json()
        self.assertEqual({x['id'] for x in chat['rule_candidates']},{first,second})
        self.assertEqual(self.post(f"/bank/flow/conversation/{chat['id']}/preview").status_code,409)
        selected=self.post(f"/bank/flow/conversation/{chat['id']}/target",rule_id=first)
        self.assertEqual(selected.status_code,200,selected.get_json());self.assertEqual(selected.get_json()['rule_id'],first)
        self.assertEqual(self.post(f"/bank/flow/conversation/{chat['id']}/target",rule_id=second).status_code,409)
        draft={**base,'suffix_policy':'review_numbers'}
        with patch('bank_chatgpt.generate_json',return_value=dict(ready=True,reply='Refined policy.',title='Updated',spec=draft)):
            self.post(f"/bank/flow/conversation/{chat['id']}",message='Review numeric endings.')
        self.post(f"/bank/flow/conversation/{chat['id']}/draft",pending_message='')
        preview=self.post(f"/bank/flow/conversation/{chat['id']}/preview").get_json()
        response=self.post(f"/bank/flow/conversation/{chat['id']}/save",preview_id=preview['id'],action='ALL')
        self.assertEqual(response.status_code,200,response.get_json());self.assertEqual(response.get_json()['rule_id'],first)
        with sessionmaker(self.engine)() as db:
            self.assertEqual(len(list(db.scalars(select(m.BankAiRule)))),rule_count)
            self.assertEqual(ops.current_version(db.get(m.BankAiRule,first)).version_no,2)
            self.assertEqual(ops.current_version(db.get(m.BankAiRule,second)).version_no,1)

    def test_three_toast_proposals_are_one_format_with_a_clarification(self):
        import bank_flow_routes as routes
        base=dict(engine=flow.ENGINE,kind='EXTRACTOR',prefix='TST*',start='TST*',end_mode='end')
        space={**base,'prefix':'TST* ','start':'TST* '}
        marker={**space,'end_mode':'marker','end':' -'}
        proposals=[dict(title='TST merchant',reply='Read through the end.',spec=base),dict(title='TST merchant',reply='Read after the space.',spec=space),dict(title='Toast merchant',reply='Stop before the location.',spec=marker)]
        grouped=routes.unique_formats(proposals)
        self.assertEqual(len(grouped),1);self.assertEqual(len(grouped[0]['variants']),2);self.assertTrue(grouped[0]['needs_clarification'])
        self.assertEqual(len(routes.unique_formats(grouped)),1)
        scan=self.post('/bank/flow/discover').get_json()['id']
        # Cached scans must be cleaned on read as well as new discovery output.
        with sessionmaker(self.engine)() as db:
            rec=db.get(m.BankFlowArtifact,scan);rec.payload=json.dumps(dict(status='PARTIAL',formats=proposals));db.commit()
        response=self.client.get(f'/bank/flow/discover/{scan}',headers=self.headers).get_json()
        self.assertEqual(len(response['formats']),1)
        chat=self.post('/bank/flow/conversation',scan_id=scan,index=response['formats'][0]['index'],kind='EXTRACTOR').get_json()
        self.assertFalse(chat['ready']);self.assertEqual(len(chat['format_variants']),2)
        with patch('bank_chatgpt.generate_json',side_effect=AssertionError('No guess before human clarification')):
            self.assertEqual(self.post(f"/bank/flow/conversation/{chat['id']}/preview").status_code,409)
        with patch('bank_chatgpt.generate_json',return_value=dict(ready=True,reply='Read to the end, preserving location.',title='Toast',spec=base)):
            self.post(f"/bank/flow/conversation/{chat['id']}",message='Read to the end, preserving location.')
        self.post(f"/bank/flow/conversation/{chat['id']}/draft",pending_message='')
        preview=self.post(f"/bank/flow/conversation/{chat['id']}/preview").get_json()
        result=self.post(f"/bank/flow/conversation/{chat['id']}/save",preview_id=preview['id'],action='FUTURE')
        self.assertEqual(result.status_code,200,result.get_json());rid=result.get_json()['rule_id']
        reopened=self.client.get(f'/bank/flow/discover/{scan}',headers=self.headers).get_json()['formats']
        self.assertEqual(len(reopened),1);self.assertFalse(reopened[0]['needs_clarification']);self.assertEqual(reopened[0]['rule_id'],rid)
        # The other old candidate cannot be reopened as a new rule.
        self.assertEqual(self.post('/bank/flow/conversation',scan_id=scan,index=2,kind='EXTRACTOR').status_code,409)

    def test_discovery_groups_toast_from_separate_generated_proposals(self):
        import bank_flow_routes as routes
        base=dict(engine=flow.ENGINE,kind='EXTRACTOR',prefix='TST*',start='TST*',end_mode='end')
        formats=[dict(title='TST',reply='Name',spec=base),dict(title='Toast',reply='Location suffix',spec={**base,'prefix':'TST* ','start':'TST* ','end_mode':'marker','end':' -'})]
        scan=self.post('/bank/flow/discover').get_json()['id']
        routes.discovery(sessionmaker(self.engine),scan,generate=lambda _:dict(formats=formats))
        result=self.client.get(f'/bank/flow/discover/{scan}',headers=self.headers).get_json()
        self.assertEqual(len(result['formats']),1);self.assertTrue(result['formats'][0]['needs_clarification'])
        self.assertEqual(len(result['formats'][0]['variants']),2)

    def research_fixture(self):
        what=m.BankAccountingClassification(code='WEB_WHAT',name='Web category',statement_type='PROFIT_LOSS',node_type='POSTING',normal_balance='DEBIT',active=True)
        other=m.BankAccountingClassification(code='WEB_OTHER',name='Other category',statement_type='PROFIT_LOSS',node_type='POSTING',normal_balance='DEBIT',active=True)
        control=m.BankAccountingClassification(code='WEB_CONTROL',name='Control account',statement_type='BALANCE_SHEET',node_type='POSTING',normal_balance='CREDIT',active=True)
        self.s.add_all([what,other,control]);self.s.flush()
        self.why.accounting_classification_id=what.id;self.newwhy.accounting_classification_id=other.id
        instrument=self.s.get(m.PaymentInstrument,self.txns[0].payment_instrument_id);instrument.owner_reporting_entity_id=self.entity.id
        self.s.commit();return what,other,control

    def researched(self,chat,who='OLD WHO',mode='profile'):
        answer=dict(probable_who=who,verified=True,summary='Verified public business activity.',sources=[dict(title='Official',url='https://example.com')],proposals=[])
        with patch('bank_profile_research.research',return_value=answer):
            response=self.post(f'/bank/flow/conversation/{chat}/research',mode=mode)
        self.assertEqual(response.status_code,200,response.get_json());return response.get_json()

    def test_research_updates_same_profile_future_and_repository_source_whom_and_rollback(self):
        from rfone_data_store.bank_reconciliation import economic_allocation as allocations
        what,other,_=self.research_fixture();rid=self.saved(self.photo());count=len(list(self.s.scalars(select(m.BankAiRule))))
        before=[safety.snapshot(self.s,t) for t in self.txns]
        chat=self.post('/bank/flow/conversation',rule_id=rid).get_json()['id'];self.researched(chat)
        chosen=self.post(f'/bank/flow/conversation/{chat}/research/choices',who='OLD WHO',why_ids=json.dumps([self.why.id]),what_ids=json.dumps([what.id]))
        self.assertEqual(chosen.status_code,200,chosen.get_json());self.assertEqual(chosen.get_json()['rule_id'],rid)
        self.assertEqual([safety.snapshot(self.s,t) for t in self.txns],before)
        preview=self.post(f'/bank/flow/conversation/{chat}/preview').get_json()
        self.assertEqual(preview['reconcilable'],2,preview)
        result=self.post(f'/bank/flow/conversation/{chat}/save',preview_id=preview['id'],action='FUTURE')
        self.assertEqual(result.status_code,200,result.get_json());self.assertEqual(result.get_json()['rule_id'],rid)
        self.s.expire_all();self.assertEqual([safety.snapshot(self.s,t) for t in self.txns],before)
        self.assertEqual(len(list(self.s.scalars(select(m.BankAiRule)))),count)
        self.assertEqual(ops.current_version(self.s.get(m.BankAiRule,rid)).version_no,2)
        allocations.set_allocations(self.s,financial_transaction_id=self.txns[0].id,specs=[allocations.AllocationSpec(amount_minor=self.txns[0].amount_minor,reporting_entity_id=self.entity2.id,status=allocations.NEEDS_OPERATOR,decision_source='HUMAN')]);self.s.commit()
        chat=self.post('/bank/flow/conversation',who_id=self.oldwho.id,kind='PHOTO').get_json()['id'];self.researched(chat)
        self.post(f'/bank/flow/conversation/{chat}/research/choices',who='OLD WHO',why_ids=json.dumps([self.newwhy.id]),what_ids=json.dumps([other.id]))
        preview=self.post(f'/bank/flow/conversation/{chat}/preview').get_json()
        by_id={x['transaction_id']:x for x in preview['rows']}
        self.assertEqual(by_id[self.txns[0].id]['after']['whom'],self.entity2.name)
        self.assertEqual(by_id[self.txns[1].id]['after']['whom'],self.entity.name)
        self.assertEqual(by_id[self.txns[1].id]['after']['what'],other.name)
        result=self.post(f'/bank/flow/conversation/{chat}/save',preview_id=preview['id'],action='ALL')
        self.assertEqual(result.status_code,200,result.get_json());self.assertEqual(result.get_json()['rule_id'],rid)
        self.s.expire_all();self.assertEqual(len(list(self.s.scalars(select(m.BankAiRule)))),count)
        for t in self.txns[:2]:
            txn=self.s.get(m.FinancialTransaction,t.id);self.assertEqual(txn.review_status,'REQUIRES_REVIEW')
            decision=self.s.get(m.BankTransactionExplanation,txn.explanation_id);self.assertEqual(decision.accounting_classification_id,other.id)
        allocations.set_allocations(self.s,financial_transaction_id=self.txns[1].id,specs=[allocations.AllocationSpec(amount_minor=self.txns[1].amount_minor,reporting_entity_id=self.entity2.id,status=allocations.NEEDS_OPERATOR,decision_source='HUMAN')]);self.s.commit()
        undo=safety.rollback_application(self.s,result.get_json()['applications'][0]);self.s.commit()
        self.assertEqual(undo['restored'],1);self.assertEqual(len(undo['skipped']),1)

    def test_research_from_unknown_transaction_creates_once_then_updates_from_profile(self):
        what,_,_=self.research_fixture();count=len(list(self.s.scalars(select(m.BankAiRule))))
        chat=self.post('/bank/flow/conversation',transaction_id=self.txns[2].id,kind='PHOTO').get_json()['id'];self.researched(chat,who='NEW SHOP',mode='transaction')
        chosen=self.post(f'/bank/flow/conversation/{chat}/research/choices',who='NEW SHOP',why_ids=json.dumps([self.why.id]),what_ids=json.dumps([what.id]))
        self.assertEqual(chosen.status_code,200,chosen.get_json())
        preview=self.post(f'/bank/flow/conversation/{chat}/preview').get_json();self.assertEqual(preview['matched'],1,preview)
        result=self.post(f'/bank/flow/conversation/{chat}/save',preview_id=preview['id'],action='ALL')
        self.assertEqual(result.status_code,200,result.get_json());rid=result.get_json()['rule_id'];self.s.expire_all()
        self.assertEqual(len(list(self.s.scalars(select(m.BankAiRule)))),count+1)
        who=self.s.scalar(select(m.BankOccurrence).where(m.BankOccurrence.canonical_name=='NEW SHOP'))
        reopened=self.post('/bank/flow/conversation',who_id=who.id,kind='PHOTO').get_json();self.assertEqual(reopened['rule_id'],rid)
        self.researched(reopened['id'],who='NEW SHOP')
        selected=self.post(f"/bank/flow/conversation/{reopened['id']}/research/choices",who='new shop',why_ids=json.dumps([self.why.id]),what_ids=json.dumps([what.id]))
        self.assertEqual(selected.status_code,200,selected.get_json());self.assertEqual(selected.get_json()['rule_id'],rid)
        p=self.post(f"/bank/flow/conversation/{reopened['id']}/preview").get_json()
        saved=self.post(f"/bank/flow/conversation/{reopened['id']}/save",preview_id=p['id'],action='FUTURE')
        self.assertEqual(saved.status_code,200,saved.get_json());self.assertEqual(saved.get_json()['rule_id'],rid)
        self.s.expire_all();self.assertEqual(len(list(self.s.scalars(select(m.BankAiRule)))),count+1)
        self.assertEqual(ops.current_version(self.s.get(m.BankAiRule,rid)).version_no,2)

    def test_multiple_why_research_requires_conditions_in_same_profile(self):
        what,other,_=self.research_fixture();rid=self.saved(self.photo())
        self.txns[0].description_original='COFFEE';self.txns[1].description_original='FOOD';self.s.commit()
        chat=self.post('/bank/flow/conversation',rule_id=rid).get_json()['id'];self.researched(chat)
        choices=self.post(f'/bank/flow/conversation/{chat}/research/choices',who='OLD WHO',why_ids=json.dumps([self.why.id,self.newwhy.id]),what_ids=json.dumps([what.id,other.id]))
        self.assertEqual(choices.status_code,200,choices.get_json());self.assertFalse(choices.get_json()['ready'])
        self.assertEqual(self.post(f'/bank/flow/conversation/{chat}/preview').status_code,409)
        spec=dict(engine=flow.ENGINE,kind='PHOTO',who='OLD WHO',allowed_why_ids=[self.why.id,self.newwhy.id],allowed_whom_ids=[],requirements=[],unresolved=[],branches=[dict(conditions=[dict(field='description',op='contains',value='COFFEE')],why_id=self.why.id,destination_id=what.id),dict(conditions=[dict(field='description',op='contains',value='FOOD')],why_id=self.newwhy.id,destination_id=other.id)])
        with patch('bank_chatgpt.generate_json',return_value=dict(ready=True,reply='Incomplete policy.',title='OLD WHO',spec={**spec,'branches':spec['branches'][:1]})):
            incomplete=self.post(f'/bank/flow/conversation/{chat}',message='Try a policy missing the second case.')
        self.assertFalse(incomplete.get_json()['ready']);self.assertIn('every selected',incomplete.get_json()['messages'][-1]['text'])
        with patch('bank_chatgpt.generate_json',return_value=dict(ready=True,reply='Coffee uses the first pair; food uses the second.',title='OLD WHO',spec=spec)):
            response=self.post(f'/bank/flow/conversation/{chat}',message='Use the first pair for COFFEE and the second for FOOD.')
        self.assertEqual(response.status_code,200,response.get_json());self.assertTrue(response.get_json()['ready'],response.get_json())
        preview=self.post(f'/bank/flow/conversation/{chat}/preview').get_json();self.assertEqual(preview['reconcilable'],2,preview)
        result=self.post(f'/bank/flow/conversation/{chat}/save',preview_id=preview['id'],action='FUTURE')
        self.assertEqual(result.status_code,200,result.get_json());self.assertEqual(result.get_json()['rule_id'],rid)

    def test_research_manual_fallback_catalog_validation_stale_row_and_control_account(self):
        what,_,control=self.research_fixture();chat=self.post('/bank/flow/conversation',transaction_id=self.txns[2].id,kind='PHOTO').get_json()['id']
        with patch('bank_profile_research.research',side_effect=RuntimeError('Provider unavailable')):
            fallback=self.post(f'/bank/flow/conversation/{chat}/research',mode='transaction')
        self.assertEqual(fallback.status_code,200,fallback.get_json());self.assertFalse(fallback.get_json()['research']['verified'])
        invalid=self.post(f'/bank/flow/conversation/{chat}/research/choices',who='MANUAL SHOP',why_ids=json.dumps([self.why.id]),what_ids=json.dumps([control.id]))
        self.assertEqual(invalid.status_code,409)
        self.txns[2].description_original+=' CHANGED';self.s.commit()
        stale=self.post(f'/bank/flow/conversation/{chat}/research/choices',who='MANUAL SHOP',why_ids=json.dumps([self.why.id]),what_ids=json.dumps([what.id]))
        self.assertEqual(stale.status_code,409);self.assertIn('changed',stale.get_json()['error'])
        self.why.accounting_classification_id=control.id;self.s.commit()
        profile=self.post('/bank/flow/conversation',who_id=self.oldwho.id,kind='PHOTO').get_json()['id'];self.researched(profile)
        chosen=self.post(f'/bank/flow/conversation/{profile}/research/choices',who='OLD WHO',why_ids=json.dumps([self.why.id]),what_ids='[]')
        self.assertEqual(chosen.status_code,200,chosen.get_json());self.assertEqual(chosen.get_json()['spec']['branches'][0]['destination_id'],control.id)

    def test_shared_research_engine_filters_invented_catalog_ids_and_keeps_known_identity(self):
        from bank_profile_research import research
        catalog=dict(why=[dict(id=1,name='Reason')],what=[dict(id=2,name='Category')],destinations=[])
        prompts=[]
        def generate(prompt,**kwargs):
            prompts.append(prompt);self.assertTrue(kwargs['web_research'])
            return dict(verified=True,probable_who='SIMILAR COMPANY',summary='Public activity',sources=[dict(title='Official',url='https://example.com'),dict(url='javascript:alert(1)')],proposals=[dict(why_id=1,what_id=2),dict(why_id=999,what_id=2),dict(why_id=True,what_id=2)])
        answer=research(who='EXACT COMPANY',description='PRIVATE BANK 123456789',catalog=catalog,generate=generate)
        self.assertEqual(answer['probable_who'],'EXACT COMPANY');self.assertEqual(len(answer['proposals']),1);self.assertEqual(len(answer['sources']),1)
        self.assertNotIn('PRIVATE BANK',prompts[0])
        bad=research(who='EXACT COMPANY',catalog=catalog,generate=lambda *a,**k:dict(verified=True,summary='No sources',sources=[],proposals=[dict(why_id=1,what_id=2)]))
        self.assertEqual(bad['proposals'],[]);self.assertFalse(bad['verified'])

    def test_research_upgrades_legacy_profile_without_new_rule_and_blocks_missing_source(self):
        what,_,_=self.research_fixture();count=len(list(self.s.scalars(select(m.BankAiRule))))
        chat=self.post('/bank/flow/conversation',rule_id=self.rule.id).get_json()['id'];self.researched(chat,who='NEW WHO')
        selected=self.post(f'/bank/flow/conversation/{chat}/research/choices',who='NEW WHO',why_ids=json.dumps([self.why.id]),what_ids=json.dumps([what.id]))
        self.assertEqual(selected.status_code,200,selected.get_json());self.assertEqual(selected.get_json()['rule_id'],self.rule.id)
        p=self.post(f'/bank/flow/conversation/{chat}/preview').get_json()
        result=self.post(f'/bank/flow/conversation/{chat}/save',preview_id=p['id'],action='FUTURE')
        self.assertEqual(result.status_code,200,result.get_json());self.s.expire_all()
        self.assertEqual(len(list(self.s.scalars(select(m.BankAiRule)))),count)
        self.assertEqual(flow.unpack(ops.current_version(self.s.get(m.BankAiRule,self.rule.id)))['whom_mode'],'SOURCE')
        inst=self.s.get(m.PaymentInstrument,self.txns[2].payment_instrument_id);inst.owner_reporting_entity_id=None;self.s.commit()
        spec=flow.unpack(ops.current_version(self.s.get(m.BankAiRule,self.rule.id)));entry=(self.s.get(m.BankAiRule,self.rule.id),ops.current_version(self.s.get(m.BankAiRule,self.rule.id)),spec)
        self.assertIsNone(flow.choose(self.s,self.txns[2],entry,'NEW WHO'))

    def test_zelle_formats_and_ach_extract_only_identity(self):
        spec=self.extractor()
        cases=[(' Zelle payment to Fernanda Mardones JPM99c128bfg ','FERNANDA MARDONES'),('zelle payment to Leo Windows Cleaning 30541248046','LEO WINDOWS CLEANING'),('Zelle payment to Studio 54 123ABC','STUDIO 54'),('Zelle payment to JPM99c128bfg',None),('Zelle payment to Human Name',None),('Other payment to A 123',None)]
        for desc,expected in cases:self.assertEqual(flow.extract(spec,desc),expected)
        ach=dict(engine=flow.ENGINE,kind='EXTRACTOR',start='ORIG CO NAME:',end_mode='marker',end=' ORIG ID:')
        self.assertEqual(flow.extract(ach,'ORIG CO NAME:MERCHANT BANKCD ORIG ID:G592126793 DESC DATE:260105'),'MERCHANT BANKCD')
        rid=self.saved(spec);txn=self.txns[2];txn.description_original='Zelle payment to OLD WHO JPM123';self.s.commit();before=safety.snapshot(self.s,txn)
        self.assertFalse(flow.import_new(self.s,txn));self.s.flush()
        self.assertEqual(safety.snapshot(self.s,txn),before)
        job=self.s.scalar(select(m.BankImportReconciliation));self.assertEqual(job.status,'QUEUED');self.assertEqual(json.loads(job.context_json)['extracted_who'],'OLD WHO')

    def test_complete_photo_reconciles_and_rollback_skips_later_change(self):
        self.saved(self.extractor());self.saved(self.photo())
        txn=self.txns[2];txn.description_original='Zelle payment to OLD WHO JPM123';self.s.commit()
        self.assertTrue(flow.import_new(self.s,txn));self.s.commit();self.s.refresh(txn)
        e=self.s.get(m.BankTransactionExplanation,txn.explanation_id);self.assertEqual(e.occurrence_id,self.oldwho.id);self.assertEqual(e.transaction_reason_id,self.why.id)
        allocations=list(self.s.scalars(select(m.BankTransactionAllocation).where(m.BankTransactionAllocation.financial_transaction_id==txn.id)))
        self.assertEqual(allocations[0].reporting_entity_id,self.entity.id);self.assertEqual(txn.review_status,'ACCEPTED')
        self.assertIn(reconciliation_status.status_of(txn,e,allocations),(reconciliation_status.RECONCILED,reconciliation_status.RECONCILED_ACCOUNTING_PENDING))
        app=self.s.scalar(select(m.BankAiRuleApplication).order_by(m.BankAiRuleApplication.id.desc()))
        self.decide(txn,self.newwho.id,self.newwhy.id);self.s.commit()
        result=safety.rollback_application(self.s,app.id);self.assertEqual(result['restored'],0);self.assertEqual(len(result['skipped']),1)

    def test_photo_conditions_and_conflicts_do_not_guess(self):
        spec=self.photo();spec['branches']=[dict(conditions=[dict(field='source_id',op='is',value=self.txns[0].payment_instrument_id)],why_id=self.why.id,whom_id=self.entity.id),dict(conditions=[dict(field='source_class',op='is',value='PERSONAL')],why_id=self.newwhy.id,whom_id=self.entity2.id)]
        rid=self.saved(spec);entry=next(e for e in flow.entries(self.s) if e[0].id==rid)
        choice=flow.choose(self.s,self.txns[0],entry,'OLD WHO');self.assertEqual(choice['why_id'],self.why.id)
        entry[2]['branches'].append(dict(conditions=[],why_id=self.newwhy.id,whom_id=self.entity2.id))
        self.assertIsNone(flow.choose(self.s,self.txns[0],entry,'OLD WHO'))
        before=self.state();self.assertEqual(self.state(),before)

    def test_required_lookup_must_be_connected_and_verified(self):
        spec=self.photo();spec['requirements']=[dict(provider='purchase_details',instruction='Find order category from statement reference')]
        with self.assertRaisesRegex(ValueError,'source'):flow.validate(self.s,spec,[])
        flow.validate(self.s,spec,['purchase_details'])
        spec['branches'][0]['conditions']=[dict(field='category',op='is',value='FOOD')]
        rid=self.saved(spec);entry=next(e for e in flow.entries(self.s) if e[0].id==rid)
        self.assertIsNone(flow.choose(self.s,self.txns[0],entry,'OLD WHO'))
        self.assertIsNotNone(flow.choose(self.s,self.txns[0],entry,'OLD WHO',evidence={'purchase_details':dict(verified=True,facts={'category':'FOOD'})}))

    def test_chat_preview_future_and_archive_are_bound_to_actual_rows(self):
        self.saved(self.extractor());txn=self.txns[2];txn.description_original='Zelle payment to OLD WHO JPM123';self.s.commit()
        before=self.state();chat=self.prepare(self.photo())
        p=self.post(f'/bank/flow/conversation/{chat}/preview').get_json()
        self.assertTrue(p['ok'],p);self.assertEqual(p['reconcilable'],3);self.assertEqual(self.state(),before)
        result=self.post(f'/bank/flow/conversation/{chat}/save',preview_id=p['id'],action='FUTURE')
        self.assertEqual(result.status_code,200,result.get_json());self.assertEqual(self.state(),before)
        self.assertEqual(self.post(f'/bank/flow/conversation/{chat}/save',preview_id=p['id'],action='ALL').status_code,409)
        rid=result.get_json()['rule_id'];data=self.post('/bank/flow/conversation',rule_id=rid).get_json()
        with patch('bank_chatgpt.generate_json',return_value=dict(ready=True,reply='Confermo gli stessi casi.',title='Policy',spec=self.photo())):
            self.post(f"/bank/flow/conversation/{data['id']}",message='Applica anche al passato')
        p=self.post(f"/bank/flow/conversation/{data['id']}/preview").get_json()
        result=self.post(f"/bank/flow/conversation/{data['id']}/save",preview_id=p['id'],action='ALL')
        self.assertEqual(result.status_code,200,result.get_json());self.assertEqual(result.get_json()['updated'],3)
        self.s.expire_all();aid=result.get_json()['applications'][-1]
        self.assertEqual(self.post(f'/bank/ai-rules/applications/{aid}/rollback').status_code,200)

    def test_extractor_archive_without_photos_queues_complete_jobs(self):
        # No photo can classify these rows: saving must queue fully initialized jobs.
        for i,txn in enumerate(self.txns):txn.description_original=f'ORIG CO NAME:EXAMPLE {i} ORIG ID:ABC123'
        self.s.commit()
        spec=dict(engine=flow.ENGINE,kind='EXTRACTOR',start='ORIG CO NAME:',end_mode='marker',end='ORIG ID:')
        before=self.state();chat=self.prepare(spec)
        preview=self.post(f'/bank/flow/conversation/{chat}/preview').get_json()
        self.assertEqual(preview['reconcilable'],0)
        response=self.post(f'/bank/flow/conversation/{chat}/save',preview_id=preview['id'],action='ALL')
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(response.get_json()['updated'],0)
        self.s.expire_all();self.assertEqual(self.state(),before)
        jobs=list(self.s.scalars(select(m.BankImportReconciliation)))
        self.assertGreater(len(jobs),1)
        for job in jobs:
            self.assertEqual(job.status,'QUEUED')
            self.assertEqual(job.stage,'PHOTOS')
            self.assertTrue(job.input_state)
            self.assertTrue(json.loads(job.eligible_versions_json))
            self.assertEqual(json.loads(job.context_json)['engine'],flow.ENGINE)
        # A subsequent application also resets existing jobs safely.
        chat=self.prepare(spec)
        preview=self.post(f'/bank/flow/conversation/{chat}/preview').get_json()
        response=self.post(f'/bank/flow/conversation/{chat}/save',preview_id=preview['id'],action='ALL')
        self.assertEqual(response.status_code,200,response.get_json())
        self.s.expire_all();self.assertEqual(len(list(self.s.scalars(select(m.BankImportReconciliation)))),len(jobs))

    def test_preview_photo_uses_extracted_who_then_returns_to_final_rule_application(self):
        for txn in self.txns:txn.description_original='ORIG CO NAME:NEW WHO ORIG ID:123'
        self.s.commit();before=self.state()
        spec=dict(engine=flow.ENGINE,kind='EXTRACTOR',start='ORIG CO NAME:',end_mode='marker',end='ORIG ID:')
        parent=self.prepare(spec);preview=self.post(f'/bank/flow/conversation/{parent}/preview').get_json()
        child=self.post('/bank/flow/conversation',kind='PHOTO',transaction_id=self.txns[0].id,parent_preview_id=preview['id'])
        self.assertEqual(child.status_code,200,child.get_json());child=child.get_json()
        self.assertEqual(child['who'],'NEW WHO');self.assertEqual(child['parent_chat_id'],parent)
        self.assertNotIn('current_values',child)  # Never copy a previous WHO’s classification.
        photo=self.photo();photo['who']='NEW WHO'
        with patch('bank_chatgpt.generate_json',return_value=dict(ready=True,reply='Choose these values for NEW WHO.',title='New profile',spec=photo)):
            response=self.post(f"/bank/flow/conversation/{child['id']}",message='Always use these WHY and WHOM values.')
        self.assertTrue(response.get_json()['ready'],response.get_json())
        cp=self.post(f"/bank/flow/conversation/{child['id']}/preview").get_json()
        self.assertEqual(cp['reconcilable'],3,cp)
        self.assertEqual(self.state(),before)
        self.assertEqual(self.post(f"/bank/flow/conversation/{child['id']}/save",preview_id=cp['id'],action='ALL').status_code,409)
        result=self.post(f"/bank/flow/conversation/{child['id']}/save",preview_id=cp['id'],action='FUTURE')
        self.assertEqual(result.status_code,200,result.get_json());self.assertEqual(result.get_json()['updated'],0)
        self.assertEqual(self.state(),before)
        self.assertEqual(self.post(f'/bank/flow/conversation/{parent}/save',preview_id=preview['id'],action='ALL').status_code,409)
        preview=self.post(f'/bank/flow/conversation/{parent}/preview').get_json()
        self.assertEqual(preview['reconcilable'],3,preview)
        result=self.post(f'/bank/flow/conversation/{parent}/save',preview_id=preview['id'],action='ALL')
        self.assertEqual(result.status_code,200,result.get_json());self.assertEqual(result.get_json()['updated'],3)
        app=result.get_json()['applications'][0]
        rollback=self.post(f'/bank/ai-rules/applications/{app}/rollback').get_json();self.assertEqual(rollback['restored'],3)

    def test_preview_photo_rejects_unselected_rows_and_changed_who(self):
        for txn in self.txns:txn.description_original='Zelle payment to OLD WHO JPM123'
        self.s.commit();parent=self.prepare(self.extractor());preview=self.post(f'/bank/flow/conversation/{parent}/preview').get_json()
        self.assertEqual(self.post('/bank/flow/conversation',kind='PHOTO',transaction_id=999999,parent_preview_id=preview['id']).status_code,409)
        child=self.post('/bank/flow/conversation',kind='PHOTO',transaction_id=self.txns[0].id,parent_preview_id=preview['id']).get_json()
        photo=self.photo();photo['who']='A DIFFERENT WHO'
        with patch('bank_chatgpt.generate_json',return_value=dict(ready=True,reply='Wrong WHO',title='Wrong',spec=photo)):
            response=self.post(f"/bank/flow/conversation/{child['id']}",message='Choose values')
        self.assertEqual(response.status_code,200,response.get_json());self.assertFalse(response.get_json()['ready'])
        self.assertEqual(self.post(f"/bank/flow/conversation/{child['id']}/preview").status_code,409)

    def test_save_rule_draft_without_preview_keeps_pending_text_and_incomplete_chat(self):
        before=self.state();chat=self.post('/bank/flow/conversation',kind='EXTRACTOR').get_json()
        path=f"/bank/flow/conversation/{chat['id']}/draft"
        self.assertEqual(self.client.post(path,headers=self.headers).status_code,400)
        self.assertEqual(self.client.post(path,data={'csrf_token':'test-csrf'}).status_code,401)
        response=self.post(path,pending_message='Remove trailing numbers, including 09/28.')
        self.assertEqual(response.status_code,200,response.get_json());saved=response.get_json()
        self.assertTrue(saved['saved_draft']);self.assertFalse(saved.get('ready',False))
        reopened=self.client.get(f"/bank/flow/conversation/{chat['id']}",headers=self.headers).get_json()
        self.assertEqual(reopened['messages'],chat['messages']);self.assertEqual(reopened['pending_message'],'Remove trailing numbers, including 09/28.')
        listing=self.client.get('/bank/flow/snapshot',headers=self.headers).get_json()
        self.assertIn(chat['id'],[d['id'] for d in listing['drafts']])
        self.assertEqual(self.state(),before)
        with patch('bank_chatgpt.generate_json',return_value=dict(ready=False,reply='Specify the description format.',spec=None)):
            self.assertEqual(self.post(f"/bank/flow/conversation/{chat['id']}/preview").status_code,409)
        self.assertEqual(self.post(f"/bank/flow/conversation/{chat['id']}/save",action='FUTURE').status_code,409)

    def test_saved_rule_changes_do_not_activate_until_explicit_apply(self):
        rid=self.saved(self.extractor(),future=False);rule=self.s.get(m.BankAiRule,rid);original_version=ops.current_version(rule).id
        chat=self.post('/bank/flow/conversation',rule_id=rid).get_json();spec=self.extractor();spec['prefix']='Zelle payment to'
        with patch('bank_chatgpt.generate_json',return_value=dict(ready=True,reply='Updated extraction instructions.',title='Updated title',spec=spec)):
            response=self.post(f"/bank/flow/conversation/{chat['id']}",message='Refine this format')
        self.assertTrue(response.get_json()['ready']);before=self.state()
        response=self.post(f"/bank/flow/conversation/{chat['id']}/draft",pending_message='')
        self.assertEqual(response.status_code,200,response.get_json())
        self.s.expire_all();rule=self.s.get(m.BankAiRule,rid)
        self.assertEqual(ops.current_version(rule).id,original_version);self.assertFalse(rule.apply_future);self.assertEqual(self.state(),before)
        reopened=self.post('/bank/flow/conversation',rule_id=rid).get_json();self.assertEqual(reopened['id'],chat['id']);self.assertEqual(reopened['messages'][-1]['text'],'Updated extraction instructions.')
        preview=self.post(f"/bank/flow/conversation/{chat['id']}/preview").get_json()
        response=self.post(f"/bank/flow/conversation/{chat['id']}/save",preview_id=preview['id'],action='FUTURE')
        self.assertEqual(response.status_code,200,response.get_json());self.s.expire_all()
        rule=self.s.get(m.BankAiRule,rid);self.assertNotEqual(ops.current_version(rule).id,original_version);self.assertTrue(rule.apply_future)
        listing=self.client.get('/bank/flow/snapshot',headers=self.headers).get_json();self.assertNotIn(chat['id'],[d['id'] for d in listing['drafts']]);self.assertEqual(self.state(),before)

    def test_numeric_suffixes_remove_dates_and_preserve_or_review_name_numbers(self):
        spec=dict(engine=flow.ENGINE,kind='EXTRACTOR',prefix='TST*',start='TST*',end_mode='end',suffix_policy='review_numbers',numeric_name_exceptions=['SEASONS 52'])
        flow.validate(self.s,spec)
        cases=[('TST*SALT & EMBER BOSTON FL 06/30','SALT & EMBER BOSTON FL',False),('TST*SEASONS 52','SEASONS 52',False),('TST*SEASONS 52 06/30','SEASONS 52',False),('TST*PLACE 123',None,True),('TST*PLACE 09/99',None,True),('TST*PLACE REF123','PLACE REF123',False),('TST*STUDIO 54 WINTER PARK FL 06/30','STUDIO 54 WINTER PARK FL',False),('TST*06/30',None,False)]
        for text,expected,uncertain in cases:
            self.assertEqual(flow.extract(spec,text),expected,text)
            parts=flow.extract(spec,text,highlight=True)
            if parts:
                self.assertEqual(parts['before']+parts['who']+parts['after'],text)
                self.assertEqual(parts['uncertain'],uncertain)
        all_numbers={**spec,'suffix_policy':'numbers'}
        self.assertEqual(flow.extract(all_numbers,'TST*PLACE 123 09/28'),'PLACE')
        self.assertEqual(flow.extract(all_numbers,'TST*SEASONS 52'),'SEASONS 52')
        dates={**spec,'suffix_policy':'dates'}
        self.assertEqual(flow.extract(dates,'TST*PLACE 123'),'PLACE 123')
        old={k:v for k,v in spec.items() if k not in ('suffix_policy','numeric_name_exceptions')}
        self.assertEqual(flow.extract(old,'TST*PLACE 06/30'),'PLACE 06/30')

    def test_saved_incomplete_extractor_can_preview_supported_suffix_policy(self):
        samples=['TST*SALT & EMBER BOSTON FL 06/30','TST*SEASONS 52','TST*UNKNOWN PLACE 123']
        for txn,text in zip(self.txns,samples):txn.description_original=text
        self.s.commit();before=self.state()
        chat=self.post('/bank/flow/conversation',kind='EXTRACTOR').get_json()
        with patch('bank_chatgpt.generate_json',return_value=dict(ready=False,reply='Review these numeric cases.',spec=None)):
            self.post(f"/bank/flow/conversation/{chat['id']}",message='For TST*, remove final dates and keep SEASONS 52.')
        self.post(f"/bank/flow/conversation/{chat['id']}/draft",pending_message='')
        spec=dict(engine=flow.ENGINE,kind='EXTRACTOR',prefix='TST*',start='TST*',end_mode='end',suffix_policy='review_numbers',numeric_name_exceptions=['SEASONS 52'])
        with patch('bank_chatgpt.generate_json',return_value=dict(ready=True,reply='Remove dates; preserve SEASONS 52; flag unknown numeric names per row.',title='TST names',spec=spec)) as generate:
            response=self.post(f"/bank/flow/conversation/{chat['id']}/preview")
        self.assertEqual(response.status_code,200,response.get_json());preview=response.get_json()
        self.assertEqual(preview['matched'],3);self.assertEqual(preview['reconcilable'],0)
        rows={r['description']:r for r in preview['rows']}
        self.assertEqual(rows[samples[0]]['extracted_who'],'SALT & EMBER BOSTON FL')
        self.assertEqual(rows[samples[1]]['extracted_who'],'SEASONS 52')
        self.assertTrue(rows[samples[2]]['who_highlight']['uncertain']);self.assertIsNone(rows[samples[2]]['choice'])
        self.assertIsNone(rows[samples[2]]['extracted_who']);self.assertIn('final number',rows[samples[2]]['note'])
        self.assertEqual(self.state(),before)
        self.assertEqual(generate.call_count,1)
        refreshed=self.client.get(f"/bank/flow/conversation/{chat['id']}",headers=self.headers).get_json();self.assertTrue(refreshed['ready']);self.assertTrue(refreshed['saved_draft'])
        # Even applying this extractor cannot write WHO/WHY/WHOM without a profile.
        response=self.post(f"/bank/flow/conversation/{chat['id']}/save",preview_id=preview['id'],action='ALL')
        self.assertEqual(response.status_code,200,response.get_json());self.assertEqual(response.get_json()['updated'],0);self.assertEqual(self.state(),before)

    def test_preview_selects_saved_draft_or_published_rule_never_unsaved_chat(self):
        base=dict(engine=flow.ENGINE,kind='EXTRACTOR',prefix='TST*',start='TST*',end_mode='end')
        rid=self.saved(base,future=True)
        for txn in self.txns:txn.description_original='TST*EXAMPLE FL 06/30'
        self.s.commit();before=self.state();chat=self.post('/bank/flow/conversation',rule_id=rid).get_json()
        draft={**base,'suffix_policy':'dates'}
        with patch('bank_chatgpt.generate_json',return_value=dict(ready=True,reply='Remove final dates.',title='TST dates',spec=draft)):
            self.post(f"/bank/flow/conversation/{chat['id']}",message='Remove final dates.')
        p=self.post(f"/bank/flow/conversation/{chat['id']}/preview").get_json()
        self.assertEqual(p['source'],'rule');self.assertEqual(p['rows'][0]['extracted_who'],'EXAMPLE FL 06/30')
        self.assertEqual(self.post(f"/bank/flow/conversation/{chat['id']}/draft",pending_message='').status_code,200)
        # Subsequent unsaved edits must not replace the saved draft in Preview or Save.
        other={**base,'start':'UNSAVED PREFIX'}
        with patch('bank_chatgpt.generate_json',return_value=dict(ready=True,reply='Unsaved different extraction.',title='Unsaved title',spec=other)):
            self.post(f"/bank/flow/conversation/{chat['id']}",message='Change the start marker, but do not save this edit.')
        p=self.post(f"/bank/flow/conversation/{chat['id']}/preview").get_json()
        self.assertEqual(p['source'],'draft');self.assertEqual(p['rows'][0]['extracted_who'],'EXAMPLE FL');self.assertEqual(p['definition_text'],'Remove final dates.')
        self.s.expire_all();self.assertEqual(flow.unpack(ops.current_version(self.s.get(m.BankAiRule,rid))),base);self.assertEqual(self.state(),before)
        result=self.post(f"/bank/flow/conversation/{chat['id']}/save",preview_id=p['id'],action='FUTURE')
        self.assertEqual(result.status_code,200,result.get_json())
        with sessionmaker(self.engine)() as fresh:
            rule=fresh.get(m.BankAiRule,rid);v=ops.current_version(rule)
            self.assertEqual(flow.unpack(v),draft);self.assertEqual(v.rule_text,'Remove final dates.');self.assertTrue(rule.apply_future)
        reopened=self.post('/bank/flow/conversation',rule_id=rid).get_json();self.assertEqual(reopened['previous_spec'],draft);self.assertEqual(reopened['previous_text'],'Remove final dates.')
        self.assertEqual(self.state(),before)

    def test_both_publish_actions_replace_the_selected_rule_definition(self):
        for action in ('FUTURE','ALL'):
            with self.subTest(action=action):
                base=dict(engine=flow.ENGINE,kind='EXTRACTOR',prefix='TST'+action+'*',start='TST'+action+'*',end_mode='end')
                rid=self.saved(base,future=True)
                for txn in self.txns:txn.description_original='TST'+action+'*EXAMPLE 06/30'
                self.s.commit();before=self.state()
                chat=self.post('/bank/flow/conversation',rule_id=rid).get_json()
                draft={**base,'suffix_policy':'dates'}
                text='Trim the final date. '+action
                with patch('bank_chatgpt.generate_json',return_value=dict(ready=True,reply=text,title='Refined TST',spec=draft)):
                    self.post(f"/bank/flow/conversation/{chat['id']}",message='Remove dates.')
                self.post(f"/bank/flow/conversation/{chat['id']}/draft",pending_message='')
                preview=self.post(f"/bank/flow/conversation/{chat['id']}/preview").get_json()
                result=self.post(f"/bank/flow/conversation/{chat['id']}/save",preview_id=preview['id'],action=action)
                self.assertEqual(result.status_code,200,result.get_json());self.assertEqual(result.get_json()['rule_id'],rid)
                with sessionmaker(self.engine)() as fresh:
                    version=ops.current_version(fresh.get(m.BankAiRule,rid))
                    self.assertEqual(version.version_no,2);self.assertEqual(version.rule_text,text);self.assertEqual(flow.unpack(version),draft)
                reopened=self.post('/bank/flow/conversation',rule_id=rid).get_json()
                self.assertEqual(reopened['published_text'],text);self.assertEqual(reopened['previous_spec'],draft)
                snapshot=self.client.get('/bank/flow/snapshot',headers=self.headers).get_json()
                self.assertEqual(next(x for x in snapshot['rules'] if x['id']==rid)['text'],text)
                if action=='FUTURE':self.assertEqual(self.state(),before)

    def test_published_discovery_reopens_the_same_rule_and_current_definition(self):
        import bank_flow_routes as routes
        response=self.post('/bank/flow/discover');scanid=response.get_json()['id']
        routes.discovery(sessionmaker(self.engine),scanid,generate=lambda _:dict(formats=[dict(title='Zelle',reply='Standard proposed',spec=self.extractor())]))
        chat=self.post('/bank/flow/conversation',scan_id=scanid,index=0,kind='EXTRACTOR').get_json()
        self.post(f"/bank/flow/conversation/{chat['id']}/draft",pending_message='')
        preview=self.post(f"/bank/flow/conversation/{chat['id']}/preview").get_json()
        saved=self.post(f"/bank/flow/conversation/{chat['id']}/save",preview_id=preview['id'],action='FUTURE').get_json()
        rid=saved['rule_id']
        reopened=self.post('/bank/flow/conversation',scan_id=scanid,index=0,kind='EXTRACTOR').get_json()
        self.assertEqual(reopened['rule_id'],rid);self.assertEqual(reopened['previous_text'],preview['definition_text'])
        changed={**self.extractor(),'suffix_policy':'dates'}
        with patch('bank_chatgpt.generate_json',return_value=dict(ready=True,reply='Updated discovery rule.',title='Zelle refined',spec=changed)):
            self.post(f"/bank/flow/conversation/{reopened['id']}",message='Remove dates.')
        self.post(f"/bank/flow/conversation/{reopened['id']}/draft",pending_message='')
        p=self.post(f"/bank/flow/conversation/{reopened['id']}/preview").get_json()
        result=self.post(f"/bank/flow/conversation/{reopened['id']}/save",preview_id=p['id'],action='ALL')
        self.assertEqual(result.status_code,200,result.get_json());self.assertEqual(result.get_json()['rule_id'],rid)
        again=self.post('/bank/flow/conversation',scan_id=scanid,index=0,kind='EXTRACTOR').get_json()
        self.assertEqual(again['previous_text'],'Updated discovery rule.');self.assertEqual(again['rule_id'],rid)

    def test_stale_preview_and_deleted_rule_cannot_apply(self):
        chat=self.prepare(self.extractor());p=self.post(f'/bank/flow/conversation/{chat}/preview').get_json()
        self.txns[0].description_original+=' changed';self.s.commit()
        result=self.post(f'/bank/flow/conversation/{chat}/save',preview_id=p['id'],action='ALL')
        self.assertEqual(result.status_code,409);self.assertIn('changed',result.get_json()['error'])
        self.assertEqual(self.s.scalar(select(m.BankAiRule).where(m.BankAiRule.title=='Human validated')),None)

    def test_ai_photo_match_applies_only_safe_and_complete_photo(self):
        rid=self.saved(self.photo());txn=self.txns[2];txn.description_original='Unfamiliar merchant text';self.s.commit();flow.import_new(self.s,txn);self.s.commit()
        import bank_import_worker as worker
        factory=sessionmaker(self.engine);id=worker.claim(factory)
        worker.process(factory,id,match_fn=lambda *_:dict(matches=[dict(photo_id=rid,certain=True,confidence=.99)]),research_fn=lambda _:self.fail('No web lookup after complete safe photo'))
        self.s.expire_all();job=self.s.get(m.BankImportReconciliation,id);self.assertEqual(job.status,'MATCHED',job.last_error)
        self.assertEqual(self.s.get(m.BankTransactionExplanation,self.s.get(m.FinancialTransaction,txn.id).explanation_id).occurrence_id,self.oldwho.id)

    def test_uncertain_ai_goes_to_web_without_writing_identity(self):
        rid=self.saved(self.photo());txn=self.txns[2];flow.import_new(self.s,txn);self.s.commit();before=self.state()
        import bank_import_worker as worker
        factory=sessionmaker(self.engine);id=worker.claim(factory)
        worker.process(factory,id,match_fn=lambda *_:dict(matches=[dict(photo_id=rid,certain=False,confidence=.8)]),research_fn=lambda _:dict(probable_who='PROBABLE WHO',summary='Uncertain identity',sources=[dict(title='Official',url='https://example.com')]))
        self.s.expire_all();job=self.s.get(m.BankImportReconciliation,id);self.assertEqual(job.status,'PROPOSED',job.last_error);self.assertEqual(self.state(),before)

    def test_manual_change_during_ai_is_preserved(self):
        rid=self.saved(self.photo());txn=self.txns[2];flow.import_new(self.s,txn);self.s.commit()
        import bank_import_worker as worker
        factory=sessionmaker(self.engine);id=worker.claim(factory)
        def match(*args):
            self.decide(txn,self.newwho.id,self.newwhy.id);self.s.commit()
            return dict(matches=[dict(photo_id=rid,certain=True,confidence=.99)])
        worker.process(factory,id,match_fn=match,research_fn=lambda _:self.fail('Do not research a stale record'))
        self.s.expire_all();job=self.s.get(m.BankImportReconciliation,id);self.assertEqual(job.status,'STALE')
        self.assertEqual(self.s.get(m.BankTransactionExplanation,self.s.get(m.FinancialTransaction,txn.id).explanation_id).occurrence_id,self.newwho.id)

    def test_discovery_scans_identical_repeated_descriptions_and_never_activates(self):
        import bank_flow_routes as routes
        response=self.post('/bank/flow/discover');self.assertEqual(response.status_code,200,response.get_json());id=response.get_json()['id']
        count=len(flow.entries(self.s));routes.discovery(sessionmaker(self.engine),id,generate=lambda _:dict(formats=[dict(title='Zelle',reply='Standard proposed',spec=self.extractor())]))
        result=self.client.get(f'/bank/flow/discover/{id}',headers=self.headers).get_json()
        self.assertEqual(result['status'],'COMPLETE');self.assertEqual(result['examined'],3);self.assertEqual(len(result['formats']),1);self.assertEqual(len(flow.entries(self.s)),count)
        self.assertEqual(self.post('/bank/flow/conversation',scan_id=id,index=0,kind='EXTRACTOR').status_code,200)

    def test_auth_csrf_and_catalog_creation_are_explicit(self):
        for path in ('/bank/flow/discover','/bank/flow/conversation','/bank/flow/catalog'):
            self.assertEqual(self.client.post(path,headers=self.headers).status_code,400)
            self.assertEqual(self.client.post(path,data={'csrf_token':'test-csrf'}).status_code,401)
        self.assertEqual(self.post('/bank/flow/catalog',kind='WHY',name='New possible reason').status_code,409)
        response=self.post('/bank/flow/catalog',confirmed='yes',kind='WHY',name='New possible reason')
        self.assertEqual(response.status_code,200,response.get_json())
        response=self.post('/bank/flow/catalog',confirmed='yes',kind='WHOM',name='New virtual beneficiary')
        self.assertEqual(response.status_code,200,response.get_json())

    def test_known_who_retrieves_required_facts_before_identity_ai(self):
        self.saved(self.extractor());spec=self.photo()
        spec['requirements']=[dict(provider='purchase_details',instruction='Retrieve the actual order category')]
        spec['branches'][0]['conditions']=[dict(field='category',op='is',value='FOOD')]
        self.saved(spec);txn=self.txns[2];txn.description_original='Zelle payment to OLD WHO JPMabc';self.s.commit()
        self.assertFalse(flow.import_new(self.s,txn));self.s.commit()
        import bank_import_worker as worker
        factory=sessionmaker(self.engine);id=worker.claim(factory)
        worker.process(factory,id,match_fn=lambda *_:self.fail('Known WHO does not need identity AI'),research_fn=lambda _:self.fail('No web lookup'),
            evidence_fn=lambda *_:{'purchase_details':dict(verified=True,facts={'category':'FOOD'},source='Synthetic order')})
        self.s.expire_all();job=self.s.get(m.BankImportReconciliation,id);self.assertEqual(job.status,'MATCHED',job.last_error)

    def test_branch_ai_call_preserves_a_concurrent_manual_change(self):
        self.saved(self.extractor());spec=self.photo();spec['branches'][0].update(mode='AI',instruction='Use verified facts to decide this case')
        self.saved(spec);txn=self.txns[2];txn.description_original='Zelle payment to OLD WHO JPM123';self.s.commit();flow.import_new(self.s,txn);self.s.commit()
        import bank_import_worker as worker
        factory=sessionmaker(self.engine);id=worker.claim(factory)
        def generate(_):
            self.decide(txn,self.newwho.id,self.newwhy.id);self.s.commit()
            return dict(certain=True,confidence=.99,branch_index=0)
        worker.process(factory,id,generate=generate,match_fn=lambda *_:self.fail('No identity call'),research_fn=lambda _:self.fail('No web call'))
        self.s.expire_all();self.assertEqual(self.s.get(m.BankImportReconciliation,id).status,'STALE')

    def test_archive_groups_changes_in_one_guarded_rollback(self):
        self.saved(self.extractor());self.txns[2].description_original='Zelle payment to OLD WHO JPM123';self.s.commit()
        chat=self.prepare(self.photo());p=self.post(f'/bank/flow/conversation/{chat}/preview').get_json()
        result=self.post(f'/bank/flow/conversation/{chat}/save',preview_id=p['id'],action='ALL').get_json()
        self.assertTrue(result['ok'],result);self.assertEqual(result['updated'],3);self.assertEqual(len(result['applications']),1)
        self.s.expire_all();self.decide(self.txns[1],self.newwho.id,self.newwhy.id);self.s.commit()
        result=self.post(f"/bank/ai-rules/applications/{result['applications'][0]}/rollback").get_json()
        self.assertEqual(result['restored'],2);self.assertEqual(len(result['skipped']),1)

    def test_incomplete_external_source_stays_in_chat_not_active(self):
        chat=self.post('/bank/flow/conversation',kind='PHOTO').get_json();spec=self.photo()
        spec['requirements']=[dict(provider='not_connected',instruction='Check a source not yet identified')]
        with patch('bank_chatgpt.generate_json',return_value=dict(ready=True,reply='Proposta',title='Incomplete',spec=spec)):
            response=self.post(f"/bank/flow/conversation/{chat['id']}",message='Controlla anche una fonte esterna')
        self.assertEqual(response.status_code,200,response.get_json());self.assertFalse(response.get_json()['ready'])
        self.assertEqual(self.post(f"/bank/flow/conversation/{chat['id']}/preview").status_code,409)

    def test_actual_csv_import_is_idempotent_and_automatic_write_is_reversible(self):
        from rfone_data_store.bank_reconciliation import service
        self.saved(self.extractor());self.saved(self.photo())
        content=b'Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\nDEBIT,02/01/2026,Zelle payment to OLD WHO JPM123abc,-33.00,ACH_DEBIT,1000.00,\n'
        first=service.import_csv(self.s,file_bytes=content,original_file_name='chase_1234.csv',uploaded_by_account_id=None,payment_instrument_id=self.txns[0].payment_instrument_id);self.s.commit()
        job=self.s.scalar(select(m.BankImportReconciliation));self.assertEqual(job.status,'MATCHED')
        txn=self.s.get(m.FinancialTransaction,job.financial_transaction_id);original=txn.description_original
        app=self.s.scalar(select(m.BankAiRuleApplication).where(m.BankAiRuleApplication.rule_id!=self.rule.id).order_by(m.BankAiRuleApplication.id.desc()))
        result=safety.rollback_application(self.s,app.id);self.assertEqual(result['restored'],1,result);self.s.commit()
        self.assertEqual(txn.description_original,original)
        again=service.import_csv(self.s,file_bytes=content,original_file_name='same.csv',uploaded_by_account_id=None,payment_instrument_id=self.txns[0].payment_instrument_id);self.s.commit()
        self.assertFalse(again.created);self.assertEqual(len(list(self.s.scalars(select(m.BankImportReconciliation)))),1)

    def test_rfone_source_reads_only_the_chosen_counterparty(self):
        resolver=self.app.extensions['bank_photo_evidence']['rfone']
        answer=resolver(dict(who='OLD WHO',transaction_id=self.txns[0].id),dict(provider='rfone',dataset='transaction_history',instruction='Controlla lo storico di questo WHO'))
        self.assertTrue(answer['verified']);self.assertEqual(answer['facts']['who'],'OLD WHO');self.assertEqual(len(answer['facts']['history']),1)
        self.assertNotIn('description',answer['facts']['history'][0])
        spec=self.photo();spec['requirements']=[dict(provider='rfone',dataset='unknown',instruction='Read unknown data')]
        with self.assertRaisesRegex(ValueError,'Specify'):flow.validate(self.s,spec,self.app.extensions['bank_photo_evidence'])

    def test_public_source_does_not_send_bank_details_or_claim_private_access(self):
        resolver=self.app.extensions['bank_photo_evidence']['public_web']
        requirement=dict(provider='public_web',instruction='Identify the public business activity')
        with patch('bank_chatgpt.generate_json',return_value=dict(verified=True,facts={'category':'FOOD'},sources=[dict(title='Official',url='https://example.com')])) as call:
            answer=resolver(dict(who='OLD WHO',description='PRIVATE_BANK_REFERENCE_12345',amount_minor=-93000),requirement)
        self.assertTrue(answer['verified']);self.assertNotIn('PRIVATE_BANK_REFERENCE_12345',call.call_args.args[0]);self.assertNotIn('93000',call.call_args.args[0]);self.assertTrue(call.call_args.kwargs['web_research'])
        spec=self.photo();spec['requirements']=[dict(**requirement,requires_auth=True)]
        with self.assertRaisesRegex(ValueError,'private'):flow.validate(self.s,spec,self.app.extensions['bank_photo_evidence'])

if __name__=='__main__':unittest.main()
