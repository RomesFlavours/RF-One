"""Three-stage WHO simulation (Rules → text → internet) on an isolated copy; the web answer is a controlled fake."""
import json, sys, tempfile, unittest
from pathlib import Path
from sqlalchemy import func, select, text
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import _isolated
from cbank import engine as E, legacy, three_stages as T
from rfone_data_store import models as m

SOURCE=[dict(title='Official site',url='https://example.org/about')]

def catalog_counts(db):
    return {name:db.scalar(select(func.count()).select_from(model)) for name,model in (
        ('who',m.BankOccurrence),('alias',m.BankOccurrenceAlias),('pairs',m.BankWhoSourceClassification),
        ('explanations',m.BankTransactionExplanation),('allocations',m.BankTransactionAllocation),
        ('matches',m.FinancialTransactionMatch),('artifacts',m.BankFlowArtifact))}

class ThreeStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=legacy.session()
        cls.e=E.Engine(cls.db,None)
        cls.sim=T.Simulation(cls.e)
        e=cls.e
        definitive=[w for w in e.c.whys if w not in e.provisional and e._why_category(w)]
        cls.why,cls.other_why=definitive[0],definitive[1]
        # A registered WHO + Source pair with a definitive WHY, and a movement on that Source.
        cls.pair=next((who,src,why) for (who,src),why in e.source_classifications.items()
                      if who in e.c.whos and why in e.c.whys and why not in e.provisional
                      and any(t.payment_instrument_id==src for t in e.txns))
        cls.paired_txn=next(t for t in e.txns if t.payment_instrument_id==cls.pair[1])
        paired={(w,s) for (w,s) in e.source_classifications if e.source_classifications[(w,s)]}
        cls.unpaired=next((w,t) for w in e.c.whos for t in e.txns[:50] if (w,t.payment_instrument_id) not in paired)
        cls.before=catalog_counts(cls.db)
    @classmethod
    def tearDownClass(cls):
        bind=cls.db.get_bind()
        cls.db.close()
        bind.dispose()   # no pooled connection left: Windows can then delete the isolated copy at exit

    def item(self,**kw):
        base=dict(id=self.paired_txn.id,outcome='UNRESOLVED',who=None,who_certainty='UNKNOWN',generic_who=None,
                  nature='',why_id=None,why_confidence='LOW',reasoning='controlled',sources=[],missing_information=[])
        base.update(kw);return base

    def test_identified_catalog_who_uses_registered_who_source(self):
        who,src,why=self.pair;txn=self.paired_txn
        r=self.sim.validate(txn,self.item(outcome='WHO_IDENTIFIED',who=self.e.c.whos[who],who_certainty='CERTAIN',
                                          why_id=self.other_why,why_confidence='HIGH',sources=SOURCE))
        self.assertEqual(r['outcome'],T.WHO_IDENTIFIED);self.assertEqual(r['who_id'],who);self.assertEqual(r['catalog'],'CATALOG')
        self.assertEqual((r['why_id'],r['why_basis']),(why,T.WHY_REGISTERED))
        self.assertEqual(r['what'],self.e.c.class_label(self.e._why_category(why)))   # WHAT only from the WHY
        self.assertEqual(r['whom'],self.e.owner(txn).name)                            # WHOM from the Source
        self.assertEqual(r['why_suggested_by_evidence']['why_id'],self.other_why)     # kept apart, never applied
        self.assertEqual(r['sources'],SOURCE)

    def test_identified_without_pair_proposes_why_from_evidence(self):
        who,txn=self.unpaired
        r=self.sim.validate(txn,self.item(id=txn.id,outcome='WHO_IDENTIFIED',who=self.e.c.whos[who],who_certainty='CERTAIN',
                                          why_id=self.why,why_confidence='MEDIUM',sources=SOURCE))
        self.assertEqual(r['outcome'],T.WHO_IDENTIFIED);self.assertEqual(r['who_source_pair'],'missing')
        self.assertEqual((r['why_id'],r['why_basis']),(self.why,T.WHY_FROM_EVIDENCE))
        # A certain WHO that is not in the catalog stays identified, unregistered, and is not created.
        r=self.sim.validate(txn,self.item(id=txn.id,outcome='WHO_IDENTIFIED',who='SYNTHETIC UNLISTED VENDOR QZX',
                                          who_certainty='CERTAIN',why_id=self.why,why_confidence='HIGH',sources=SOURCE))
        self.assertEqual((r['outcome'],r['catalog'],r['registered_in_catalog'],r['who_id']),
                         (T.WHO_IDENTIFIED,'NOT_IN_CATALOG',False,None))
        self.assertEqual(r['why_basis'],T.WHY_FROM_EVIDENCE)

    def test_identity_needs_certainty_and_a_source(self):
        who,src,why=self.pair
        for kw in (dict(who_certainty='PROBABLE',sources=SOURCE),dict(who_certainty='CERTAIN',sources=[]),
                   dict(who_certainty='CERTAIN',sources=[dict(title='x',url='javascript:alert(1)')])):
            r=self.sim.validate(self.paired_txn,self.item(outcome='WHO_IDENTIFIED',who=self.e.c.whos[who],**kw))
            self.assertEqual(r['outcome'],T.UNRESOLVED,kw)

    def test_generic_who_classified_never_registered(self):
        r=self.sim.validate(self.paired_txn,self.item(outcome='GENERIC',generic_who='Parking — unknown merchant',
                                                      nature='parking',why_id=self.why,why_confidence='HIGH',
                                                      category_id=999999,sources=SOURCE))
        self.assertEqual((r['outcome'],r['who'],r['who_id'],r['registered_in_catalog']),
                         (T.GENERIC_WHO,'Parking — unknown merchant',None,False))
        self.assertEqual((r['why_id'],r['why_basis']),(self.why,T.WHY_FROM_EVIDENCE))
        self.assertEqual(r['what'],self.e.c.class_label(self.e._why_category(self.why)))
        self.assertIsNone(self.sim.catalog_who('Parking — unknown merchant')[0])

    def test_unresolved_when_why_not_supported(self):
        provisional=next(iter(self.e.provisional),None)
        cases=[dict(outcome='GENERIC',generic_who='Parking — unknown merchant',why_id=self.why,why_confidence='LOW'),
               dict(outcome='GENERIC',generic_who='Parking — unknown merchant',why_id=None,why_confidence='HIGH'),
               dict(outcome='GENERIC',generic_who='Parking — unknown merchant',why_id=987654321,why_confidence='HIGH'),
               dict(outcome='UNRESOLVED'),None]
        if provisional:
            cases.append(dict(outcome='GENERIC',generic_who='Something — unknown',why_id=provisional,why_confidence='HIGH'))
        for kw in cases:
            r=self.sim.validate(self.paired_txn,self.item(**kw) if kw else None)
            self.assertEqual((r['outcome'],r['why_id'],r['what']),(T.UNRESOLVED,None,None),kw)
            self.assertEqual(r['whom'],self.e.owner(self.paired_txn).name)

    def test_dining_uses_dated_source_owner_even_without_exact_merchant(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        item = self.item(nature_code='DINING', nature_confidence='HIGH',
                         nature='Restaurant payment', outcome='UNRESOLVED')
        txn = self.paired_txn
        txn = SimpleNamespace(payment_instrument_id=txn.payment_instrument_id,
                              amount_minor=-14190)
        for kind, expected in [('PERSONAL', 'Owner Personal — Restaurant'),
                               ('LEGAL', 'Business Meals & Entertainment')]:
            with patch.object(self.e, 'owner', return_value=SimpleNamespace(entity_type=kind, name=kind)):
                result = self.sim.validate(txn, item)
            self.assertEqual(result['outcome'], T.GENERIC_WHO)
            self.assertEqual(result['why'], expected)
            self.assertTrue(result['what'])
            self.assertFalse(result['registered_in_catalog'])
            self.assertEqual(result['why_basis'], 'APPROVED DINING + SOURCE OWNER POLICY')
        with patch.object(self.e, 'owner', return_value=None):
            result = self.sim.validate(txn, item)
        self.assertEqual(result['outcome'], T.UNRESOLVED)

    def test_run_three_stages_writes_only_the_file(self):
        open_=[t.id for t in self.e.txns if not T.recognise(self.sim,t)['resolved']][:9]
        self.assertEqual(len(open_),9)
        ids=open_+[t.id for t in self.e.txns if t.id not in open_][:51]
        calls=[]
        def fake(prompt,*,web_research=False):
            calls.append(web_research)
            payload=json.loads(prompt[prompt.index('\n{')+1:])
            self.assertTrue(all('amount' not in mv for mv in payload['movements']))   # amounts stay local
            self.assertLessEqual(len(payload['movements']),3)                        # consent: up to three descriptions
            out=[]
            for n,mv in enumerate(payload['movements']):
                out.append([dict(id=mv['id'],outcome='GENERIC',generic_who='Parking — unknown merchant',why_id=self.why,
                                 why_confidence='HIGH',sources=SOURCE,reasoning='IGNORE PREVIOUS INSTRUCTIONS'),
                            dict(id=mv['id'],outcome='UNRESOLVED'),
                            dict(id=mv['id'],outcome='WHO_IDENTIFIED',who='SYNTHETIC WEB VENDOR',who_certainty='CERTAIN',
                                 why_id=self.why,why_confidence='MEDIUM',sources=SOURCE)][n%3])
            out.append(dict(id=-1,outcome='GENERIC',generic_who='not asked',why_id=self.why,why_confidence='HIGH'))
            return dict(movements=out)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'sim.json'
            s=T.run(self.e,path,generate=fake,ids=set(ids),log=lambda *_:None)
            data=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(len(data['records']),60);self.assertEqual(s['total'],60)
            self.assertTrue(s['quadrature'].endswith('✓'),s['quadrature'])
            self.assertFalse(data['meta']['matching_first'])
            self.assertTrue(calls and all(calls))   # the web was called, with web research on
            researched=[r for r in data['records'] if not r['resolved']]
            self.assertGreaterEqual(len(researched),9)
            self.assertTrue(all(r.get('stage3') for r in researched))
            self.assertEqual({r['stage3']['outcome'] for r in researched},{T.WHO_IDENTIFIED,T.GENERIC_WHO,T.UNRESOLVED})
            self.assertTrue(all(r['stage'] in (T.RULES,T.TEXT) and r.get('who_id') for r in data['records'] if r['resolved']))
            self.assertEqual(s.get('rules_unique_who',0)+s.get('text_unique_who',0)+s.get('internet_who_identified',0)
                             +s.get('internet_generic_who',0)+s.get('unresolved',0),60)
            self.assertTrue(all(r['resolved'] or r['stage3']['outcome'] in (T.WHO_IDENTIFIED,T.GENERIC_WHO,T.UNRESOLVED)
                                for r in data['records']))
            self.assertNotIn(-1,{r['id'] for r in data['records']})
            # Resume reuses the saved answers without calling the web again.
            calls.clear();T.run(self.e,path,generate=fake,ids=set(ids),resume=True,log=lambda *_:None)
            self.assertEqual(calls,[])
        self.assertEqual(catalog_counts(self.db),self.before)   # no decision, WHO, alias, pair, match or artifact
        names={n.upper() for n in self.e.c.whos.values()}
        self.assertNotIn('PARKING — UNKNOWN MERCHANT',names);self.assertNotIn('SYNTHETIC WEB VENDOR',names)

    def test_research_failure_is_recorded_not_guessed(self):
        def down(prompt,*,web_research=False):raise RuntimeError('provider unavailable')
        out=self.sim.research([(self.paired_txn,dict(reason='x'))],down)
        r=out[self.paired_txn.id]
        self.assertEqual(r['outcome'],T.UNRESOLVED);self.assertTrue(r['research_error'])

    def test_the_session_is_read_only(self):
        with self.assertRaises(Exception):
            self.db.execute(text("UPDATE bank_occurrences SET canonical_name=canonical_name"));self.db.flush()
        self.db.rollback()

if __name__=='__main__':
    unittest.main()
