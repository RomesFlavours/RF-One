"""Isolated equivalence, invalidation, query-plan and evidence-delta regressions."""
import copy
from contextlib import closing
import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'backups/performance-20261117/baseline'
sys.path[:0] = [str(ROOT), str(ROOT/'03 Software/RF-One Web'), str(ROOT/'03 Software/RF-One Data Store')]
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session, sessionmaker
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import who_search_text as who, paypal_reports as pp
from rfone_data_store.bank_reconciliation import card_configuration as cards, export
import bank_amazon as amazon
import bank_trial_sources as trial


def original(name, path):
    spec = importlib.util.spec_from_file_location(name, BASELINE/path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CacheTests(unittest.TestCase):
    def test_own_external_commits_rollback_and_existing_snapshot(self):
        with tempfile.TemporaryDirectory(prefix='rfbank-cache-', dir=BASELINE.parent) as folder:
            path = Path(folder)/'cache.db'
            engine = create_engine('sqlite:///'+path.as_posix())
            with engine.begin() as db:
                db.exec_driver_sql('PRAGMA journal_mode=WAL')
                db.exec_driver_sql('CREATE TABLE dependency (id INTEGER PRIMARY KEY, value TEXT)')
                db.exec_driver_sql("INSERT INTO dependency VALUES (1,'old')")
            factory = sessionmaker(engine)
            def calculate(db):
                return [dict(value=db.scalar(text('SELECT value FROM dependency WHERE id=1')))]
            try:
                with patch.object(who, '_movements', side_effect=calculate) as compute:
                    with factory() as db:
                        first = who.movements(db)
                        # A second pooled connection must reuse the same unchanged snapshot.
                        with factory() as other_db:
                            self.assertEqual(who.movements(other_db), first)
                        self.assertEqual(compute.call_count, 1)
                    first[0]['value'] = 'caller mutation'
                    with factory() as db:
                        self.assertEqual(who.movements(db), [dict(value='old')])
                    self.assertEqual(compute.call_count, 1)
                    with factory() as db:
                        db.execute(text("UPDATE dependency SET value='own'"));db.commit()
                    with factory() as db:
                        self.assertEqual(who.movements(db), [dict(value='own')])
                    with closing(sqlite3.connect(path)) as other, other:
                        other.execute("UPDATE dependency SET value='external'")
                    with factory() as db:
                        self.assertEqual(who.movements(db), [dict(value='external')])
                    with factory() as db:
                        db.execute(text("UPDATE dependency SET value='rolled back'"));db.rollback()
                    with factory() as db:
                        self.assertEqual(who.movements(db), [dict(value='external')])
                    with factory() as db:
                        db.execute(text('BEGIN'))
                        self.assertEqual(db.scalar(text('SELECT value FROM dependency')), 'external')
                        with closing(sqlite3.connect(path)) as other, other:
                            other.execute("UPDATE dependency SET value='newer'")
                        self.assertEqual(who.movements(db), [dict(value='external')])
                    with factory() as db:
                        self.assertEqual(who.movements(db), [dict(value='newer')])
            finally:
                who._movement_cache.clear()
                who._snapshot_digests.clear()
                engine.dispose()

    def test_filters_counts_and_all_pages_equal_original(self):
        rows = json.loads((BASELINE.parent/'before-rows.json').read_text(encoding='utf-8'))
        with patch.object(who, 'movements', return_value=rows):
            for show in ['', 'null', 'review', 'RULE', 'TEXT']:
                for query in ['', 'paypal', 'zelle', 'not a real merchant XYZ']:
                    expected = [r for r in rows if (not show or
                        (not r['by'] if show=='null' else r['by'] in ('RULES_DISAGREE','TEXT_AMBIGUOUS')
                         if show=='review' else r['by']==show)) and
                        (not query or query.lower() in (r['description']+' '+' '.join(r['whos'])).lower())]
                    page = who.movement_page(None, per_page=37, show=show, search=query)
                    actual = []
                    for index in range(1, page['pages']+1):
                        actual.extend(who.movement_page(None, page=index, per_page=37, show=show, search=query)['movements'])
                    self.assertEqual(actual, expected)
                    self.assertEqual(page['filtered'], len(expected))
                    self.assertEqual(page['total'], len(rows))


class OwnerTests(unittest.TestCase):
    def test_historic_boundaries_missing_date_and_legacy_fallback(self):
        from datetime import date
        from types import SimpleNamespace as NS
        a, b = NS(id=2,instrument_type='BANK_ACCOUNT'), NS(id=3,instrument_type='BANK_ACCOUNT')
        card = NS(id=1,linked_instrument_id=3,instrument_type='CREDIT_CARD')
        history = [NS(credit_card_payment_instrument_id=1, settlement_bank_account_id=3,
                      valid_from=date(2026,2,1),valid_to=None),
                   NS(credit_card_payment_instrument_id=1, settlement_bank_account_id=2,
                      valid_from=date(2026,1,1),valid_to=date(2026,2,1))]
        instruments={1:card,2:a,3:b}
        for day, expected in [(date(2026,1,1),2),(date(2026,1,31),2),
                              (date(2026,2,1),3),(date(2025,12,31),3),(None,3)]:
            actual=cards.settlement_account_on(None,credit_card_payment_instrument_id=1,
                on_date=day,assignments=history,instruments=instruments)
            self.assertEqual(actual.id,expected)
        card.linked_instrument_id=None
        self.assertIsNone(cards.settlement_account_on(None,credit_card_payment_instrument_id=1,
            on_date=date(2025,12,31),assignments=history,instruments=instruments))

    def test_bulk_ownership_matches_canonical_at_every_transaction_date(self):
        engine = create_engine('sqlite:///'+(BASELINE.parent/'baseline.db').as_posix())
        try:
            with Session(engine) as db:
                index = export.OwnerIndex(db)
                for txn in db.scalars(select(m.FinancialTransaction)):
                    instrument = index.instruments.get(txn.payment_instrument_id)
                    expected = cards.accounting_account_for(db, instrument=instrument,
                        on_date=txn.posting_date) if instrument is not None else None
                    actual = index.account_for(txn.payment_instrument_id, txn.posting_date)
                    self.assertEqual(actual.id if actual else None, expected.id if expected else None)
        finally:
            engine.dispose()


class LookupTests(unittest.TestCase):
    def test_indexed_plan_reuse_security_and_multiple_matches(self):
        engine = create_engine('sqlite://')
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE evidence (account INTEGER, day TEXT, amount INTEGER, memo TEXT)')
            connection.exec_driver_sql('INSERT INTO evidence VALUES (?,?,?,?)',
                [(i%10, '2026-01-01', i%17, str(i)) for i in range(5000)])
        catalog={'bank.evidence':['account','day','amount','memo']}
        query='SELECT memo FROM s1 WHERE account=:source_id AND day=:day AND amount=:amount_minor'
        cache={}
        try:
            with Session(engine) as db:
                a=trial.Lookup(db, dict(sources=['bank.evidence'],query=query),catalog,populate=True,workspace_cache=cache)
                b=trial.Lookup(db, dict(sources=['bank.evidence'],query=query+' ORDER BY memo'),catalog,populate=True,workspace_cache=cache)
                self.assertIs(a.conn,b.conn)
                old_trial=original('_original_trial',Path('03 Software/RF-One Web/bank_trial_sources.py'))
                old_lookup=old_trial.Lookup(db,dict(sources=['bank.evidence'],query=query),dict(catalog),populate=True)
                # Compare only the trusted internal image, not an executable user SELECT.
                old_lookup.conn.set_authorizer(None)
                self.assertEqual(hashlib.sha256(old_lookup.conn.serialize()).hexdigest(), a.evidence_digest)
                old_lookup.conn.close()
                params=dict(trial.bindings(), source_id=1,day='2026-01-01',amount_minor=1)
                plan=a.conn.execute('EXPLAIN QUERY PLAN '+a.query,params).fetchall()
                self.assertTrue(any('SEARCH' in row[3] and 'INDEX' in row[3] for row in plan),plan)
                self.assertEqual(len(a.find(params)),2)  # ambiguity is not hidden
                # An internal indexing error cannot leave a shared workspace writable.
                quote = trial.quoted
                def reject_index(value):
                    if value.startswith('ix_'):
                        raise ValueError('injected index error')
                    return quote(value)
                with patch.object(trial, 'quoted', side_effect=reject_index):
                    with self.assertRaises(ValueError):
                        trial.Lookup(db,dict(sources=['bank.evidence'],query=query),catalog,
                                     populate=True,workspace_cache=cache)
                for sql in ['DELETE FROM s1','PRAGMA query_only=OFF','SELECT * FROM sqlite_master']:
                    with self.assertRaises(sqlite3.DatabaseError):a.conn.execute(sql)
                a.conn.close()
        finally:engine.dispose()


class EvidenceTests(unittest.TestCase):
    def test_startup_projection_serializes_concurrent_writers(self):
        with tempfile.TemporaryDirectory(prefix='rfbank-projection-',dir=BASELINE.parent) as folder:
            path=Path(folder)/'projection.db'
            engine=create_engine('sqlite:///'+path.as_posix())
            try:
                m.BankFlowArtifact.__table__.create(engine)
                with Session(engine) as db:
                    pp.sync(db)
                    with closing(sqlite3.connect(path,timeout=.01)) as competitor:
                        with self.assertRaises(sqlite3.OperationalError):
                            competitor.execute('BEGIN IMMEDIATE')
            finally:engine.dispose()

    def setUp(self):
        self.engines=[create_engine('sqlite://'),create_engine('sqlite://')]
        for e in self.engines:m.BankFlowArtifact.__table__.create(e)
        self.dbs=[Session(e) for e in self.engines]
        self.old_pp=original('rfone_data_store.bank_reconciliation._original_paypal',
            Path('03 Software/RF-One Data Store/rfone_data_store/bank_reconciliation/paypal_reports.py'))
        self.old_amazon=original('_original_amazon',Path('03 Software/RF-One Web/bank_amazon.py'))

    def tearDown(self):
        for db in self.dbs:db.close()
        for e in self.engines:e.dispose()

    def add(self, kind, payload):
        for db in self.dbs:
            db.add(m.BankFlowArtifact(kind=kind,payload=json.dumps(payload)));db.flush()

    def compare(self, old, new, tables):
        old(self.dbs[0]);new(self.dbs[1])
        for table in tables:
            a=list(self.dbs[0].execute(text('SELECT * FROM '+table+' ORDER BY 1,2')))
            b=list(self.dbs[1].execute(text('SELECT * FROM '+table+' ORDER BY 1,2')))
            self.assertEqual(a,b,table)
        changed=self.dbs[1].scalar(text('SELECT total_changes()'))
        new(self.dbs[1])
        self.assertEqual(changed,self.dbs[1].scalar(text('SELECT total_changes()')))

    def test_paypal_overlap_status_conflicts_corrections_and_removal(self):
        event=dict(transaction_id='P1',currency='USD',date='2026-01-01',name='SHOP',type='Purchase',
            amount_minor=-100,fees_minor=0,total_minor=-100,status='Pending',reference_id='',funding=[])
        report=dict(file_name='a.csv',format='CSV',account=None,events=[event,dict(event)])
        self.add(pp.KIND,report)
        self.compare(self.old_pp.sync,pp.sync,['bank_paypal_observations','bank_paypal_transactions'])
        event=dict(event,status='Completed',total_minor=-200,amount_minor=-200,reference_id='REF')
        self.add(pp.KIND,dict(file_name='b.pdf',format='PDF',account='owner@example.test',events=[event]))
        self.compare(self.old_pp.sync,pp.sync,['bank_paypal_observations','bank_paypal_transactions'])
        self.add(pp.KIND,dict(file_name='other-account.csv',format='CSV',account='other@example.test',
            events=[dict(event),dict(event,transaction_id='REFUND',type='Refund',amount_minor=100,total_minor=100,reference_id='P1'),
                    dict(event,currency='EUR')]))
        self.compare(self.old_pp.sync,pp.sync,['bank_paypal_observations','bank_paypal_transactions'])
        for db in self.dbs:
            row=db.scalars(select(m.BankFlowArtifact).order_by(m.BankFlowArtifact.id)).first()
            obj=json.loads(row.payload);obj['events'][0]['name']='CORRECTED';row.payload=json.dumps(obj);db.flush()
        self.compare(self.old_pp.sync,pp.sync,['bank_paypal_observations','bank_paypal_transactions'])
        for db in self.dbs:db.execute(text('DELETE FROM bank_flow_artifacts WHERE id=1'))
        self.compare(self.old_pp.sync,pp.sync,['bank_paypal_observations','bank_paypal_transactions'])

    def test_amazon_current_rows_duplicates_corrections_and_removal(self):
        def row(line,charge,title='Fan',order='ORDER'):
            return dict(line=line,charge=charge,fields={'Order ID':order,'Order Date':'2026-01-01',
                'Payment Date':'2026-01-02','Title':title,'ASIN':'ASIN1','Item Quantity':'1',
                'Item Net Total':'10.00','Order Net Total':'20.00','Currency':'USD'})
        self.add(amazon.REPORT,dict(file_name='first.csv',rows=[row(1,'C1'),row(2,'C1'),row(3,'')]))
        self.compare(self.old_amazon.sync_items,amazon.sync_items,['bank_amazon_items'])
        self.add(amazon.REPORT,dict(file_name='second.csv',rows=[row(1,'C1','Updated'),row(2,'')]))
        self.compare(self.old_amazon.sync_items,amazon.sync_items,['bank_amazon_items'])
        for db in self.dbs:
            record=db.get(m.BankFlowArtifact,2);obj=json.loads(record.payload)
            obj['rows'][0]['fields']['Item Quantity']='2';record.payload=json.dumps(obj);db.flush()
        self.compare(self.old_amazon.sync_items,amazon.sync_items,['bank_amazon_items'])
        for db in self.dbs:db.execute(text('DELETE FROM bank_flow_artifacts WHERE id=2'))
        self.compare(self.old_amazon.sync_items,amazon.sync_items,['bank_amazon_items'])


if __name__=='__main__':unittest.main(verbosity=2)
