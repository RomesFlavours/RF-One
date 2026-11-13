"""Exact WHO/Source purpose, uniqueness, and merge safety on an isolated migrated copy."""
import sys, unittest
from pathlib import Path
from types import SimpleNamespace as NS
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import _isolated
from cbank import config, engine as E, legacy, store
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import source_classification as sc, manual_reconciliation as manual

class PairStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = create_engine('sqlite:///'+config.BANK_DB.as_posix())
    def setUp(self):
        self.db=Session(self.sql)
        self.sources=list(self.db.scalars(select(m.PaymentInstrument.id)))[:2]
        self.whys=list(self.db.scalars(select(m.BankTransactionReason.id).where(m.BankTransactionReason.status=='ACTIVE')))[:2]
        self.who=manual.create_who(self.db,name='SYNTHETIC NORTH VENDOR').occurrence.id
    def tearDown(self):
        self.db.rollback();self.db.close()
    def test_one_catalog_who_two_unique_classifications(self):
        for source,why in zip(self.sources,self.whys):
            sc.save(self.db,occurrence_id=self.who,payment_instrument_id=source,transaction_reason_id=why)
        rows=list(self.db.scalars(select(m.BankWhoSourceClassification).where(m.BankWhoSourceClassification.occurrence_id==self.who)))
        self.assertEqual(len(rows),2)
        self.assertEqual({r.occurrence_id for r in rows},{self.who})
        self.assertEqual({r.transaction_reason_id for r in rows},set(self.whys))
        with self.assertRaises(ValueError):
            sc.save(self.db,occurrence_id=self.who,payment_instrument_id=self.sources[0],transaction_reason_id=self.whys[0])
    def test_database_also_refuses_duplicate_pair(self):
        sc.save(self.db,occurrence_id=self.who,payment_instrument_id=self.sources[0])
        self.db.add(m.BankWhoSourceClassification(occurrence_id=self.who,payment_instrument_id=self.sources[0]))
        with self.assertRaises(IntegrityError):self.db.flush()
    def test_merge_refuses_incompatible_purposes_on_same_source(self):
        other=manual.create_who(self.db,name='SYNTHETIC SOUTH VENDOR').occurrence.id
        sc.save(self.db,occurrence_id=self.who,payment_instrument_id=self.sources[0],transaction_reason_id=self.whys[0])
        sc.save(self.db,occurrence_id=other,payment_instrument_id=self.sources[0],transaction_reason_id=self.whys[1])
        with self.assertRaises(ValueError):sc.merge_pairs(self.db,self.who,other)
    def test_labels_are_physically_absent_in_current_schema(self):
        from sqlalchemy import inspect
        schema=inspect(self.db.bind)
        self.assertNotIn('bank_who_labels',schema.get_table_names())
        self.assertNotIn('bank_occurrence_labels',schema.get_table_names())
        columns={x['name'] for x in schema.get_columns('bank_who_profiles')}
        self.assertFalse(columns & {'label_status','label_question','label_attempts','activity'})

class ExactPairEngineTests(unittest.TestCase):
    def test_no_global_or_other_source_fallback_and_derived_fields(self):
        e=E.Engine(legacy.session(),store.connect(':memory:'))
        template=next(t for t in e.txns if t.id not in e.matches and not E.matching.is_card_payment_out(t,e.c.instruments,e.card_payment_out))
        who=next(iter(e.c.whos));name=e.c.whos[who]
        e.recogniser=NS(recognise=lambda *a,**kw:NS(outcome='FOUND',who=name,method='TEXT',known=True,evidence='controlled',legacy_hits=[]))
        instruments=[i for i in e.c.instruments.values() if e.c.owner(NS(payment_instrument_id=i.id,posting_date=template.posting_date,transaction_date=template.transaction_date))][:2]
        txns=[]
        for n,i in enumerate(instruments):
            values={k:v for k,v in template.__dict__.items() if not k.startswith('_')}
            values.update(id=-100-n,payment_instrument_id=i.id,explanation_id=None,description_original='SYNTHETIC ORDINARY PURCHASE')
            txns.append(NS(**values))
        whys=[w for w,row in e.c.whys.items() if row.accounting_classification_id and w not in e.provisional][:2]
        e.source_classifications={(who,instruments[0].id):whys[0]}
        a,b=[e.evaluate(t) for t in txns]
        self.assertEqual(a['why_id'],whys[0]);self.assertIsNone(b['why_id'])
        self.assertEqual(a['category_id'],e.c.whys[whys[0]].accounting_classification_id)
        for r in (a,b):self.assertEqual(r['beneficiary_id'],r['payer_id'])
        e.source_classifications[(who,instruments[1].id)]=whys[1]
        self.assertEqual(e.evaluate(txns[1])['why_id'],whys[1])
        self.assertEqual(e.evaluate(txns[0])['why_id'],whys[0])
        e.db.close()
