"""Regression: Review reads approved WHO rules without writing movement decisions.
Runs only on a SQLite backup of the local Bank, like WHO Search Text tests.
"""
import atexit
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent / 'RF-One Data Store')]
SOURCE = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'RF-One/Bank/rfone.db'
FOLDER = tempfile.mkdtemp(prefix='bank_review_who_')
atexit.register(shutil.rmtree, FOLDER, ignore_errors=True)
COPY = Path(FOLDER) / 'bank.db'
with sqlite3.connect('file:' + SOURCE.as_posix() + '?mode=ro', uri=True) as src:
    with sqlite3.connect(COPY) as dst:
        src.backup(dst)
# Test copies use the current schema (as the C-Bank tests do); the operational database is never migrated here.
from rfone_data_store.database import run_migrations_to_head
run_migrations_to_head('sqlite:///' + COPY.as_posix())
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import flow, review_queues as Q, row_reconciliation as R, review_who

class ReviewWhoTests(unittest.TestCase):
    def setUp(self):
        self.db = Session(create_engine('sqlite:///' + COPY.as_posix()))
        self.txn = self.db.scalar(select(m.FinancialTransaction).where(
            m.FinancialTransaction.accounting_status == 'CANONICAL'))
        self.txn.description_original = 'PAYPAL *CLEVERBRIDG CCLEA'
        self.txn.explanation_id = None
        self.txn.duplicate_status = 'NONE'
        # Control the rule set on the throwaway copy, independent of local approvals.
        for rule in self.db.scalars(select(m.BankAiRule)):
            rule.apply_future = False
        self.rule = m.BankAiRule(title='PayPal regression', organization_kind='GENERAL',
                                 status='ACTIVE', apply_future=True)
        self.db.add(self.rule)
        self.db.flush()
        self.spec = dict(engine=flow.ENGINE, kind='EXTRACTOR', start='PAYPAL *',
                         end_mode='end', require=['PAYPAL *'], name_cleanup='none')
        self.db.add(m.BankAiRuleVersion(rule_id=self.rule.id, version_no=1,
            rule_text='PayPal WHO', spec=json.dumps(self.spec), method='CODE'))
        self.db.flush()
        self.filters = Q.ReviewFilters(allowed_ids=frozenset([self.txn.id]))

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def test_preview_queue_counts_row_and_column_filter_agree_without_writes(self):
        before = self.db.connection().exec_driver_sql('select count(*) from bank_transaction_explanations').scalar()
        self.assertEqual(flow.extract(self.spec, self.txn.description_original), 'CLEVERBRIDG CCLEA')
        self.assertEqual(Q.counts(self.db, self.filters), {Q.TO_RECONCILE:0,Q.RECONCILED:1})
        self.assertNotIn(self.txn.id, Q.to_reconcile_ids(self.db,[self.txn.id]))
        self.assertEqual(Q.reconciled_ids(self.db,self.filters),{self.txn.id})
        self.assertEqual([t.id for t in Q.queue(self.db,Q.RECONCILED,self.filters)], [self.txn.id])
        row = R.rows_view(self.db,[self.txn])['rows'][0]
        self.assertEqual(row['who'],'CLEVERBRIDG CCLEA')
        self.assertIsNone(row['why_id'])
        self.assertIsNone(row['what_id'])
        self.assertEqual(Q.column_texts(self.db,[self.txn])[self.txn.id]['who'],row['who'])
        self.assertIsNone(self.txn.explanation_id)
        self.assertEqual(self.db.connection().exec_driver_sql('select count(*) from bank_transaction_explanations').scalar(),before)
        self.assertFalse(self.db.dirty)

    def test_pause_invalidates_projection_and_duplicate_remains_without_who(self):
        self.assertIn(self.txn.id,review_who.proposals(self.db))
        self.txn.duplicate_status='CANDIDATE_DUPLICATE'
        self.db.flush()
        self.assertEqual(Q.counts(self.db,self.filters)[Q.TO_RECONCILE],1)
        self.rule.apply_future=False
        self.txn.description_original='ZZZ UNRECOGNISABLE 739291'
        self.db.flush()
        self.assertNotIn(self.txn.id,review_who.proposals(self.db))

    def test_existing_human_who_is_preserved(self):
        decision = self.db.scalar(select(m.BankTransactionExplanation).where(
            m.BankTransactionExplanation.occurrence_id.is_not(None),
            m.BankTransactionExplanation.decision_source == 'HUMAN'))
        self.assertIsNotNone(decision)
        self.txn.explanation_id=decision.id
        self.db.flush()
        self.assertNotIn(self.txn.id,review_who.proposals(self.db))
        row=R.rows_view(self.db,[self.txn])['rows'][0]
        self.assertEqual(row['who_id'],decision.occurrence_id)
        self.assertEqual(row['who_source'],'person')

    def test_conflicting_rules_stay_without_who(self):
        second=m.BankAiRule(title='Conflicting WHO', organization_kind='GENERAL',status='ACTIVE',apply_future=True)
        self.db.add(second);self.db.flush()
        self.db.add(m.BankAiRuleVersion(rule_id=second.id,version_no=1,rule_text='Conflict',method='CODE',
            spec=json.dumps(dict(self.spec,start='*CLEVER',require=['PAYPAL']))))
        self.db.flush()
        self.assertEqual(Q.counts(self.db,self.filters)[Q.TO_RECONCILE],1)

class ReviewHttpTests(unittest.TestCase):
    def test_real_paypal_example_leaves_without_who_and_shows_who(self):
        os.environ['RFONE_DATABASE_URL']='sqlite:///' + COPY.as_posix()
        os.environ['RFONE_WEB_TEST_SECRET_KEY']='isolated-review-who-test'
        os.environ['RFONE_BANK_SINGLE_ENGINE']='1'
        import app as web_app
        import auth
        with Session(create_engine('sqlite:///' + COPY.as_posix())) as db:
            txn=db.scalar(select(m.FinancialTransaction).where(
                m.FinancialTransaction.description_original=='PAYPAL *CLEVERBRIDG CCLEA'))
            self.assertIsNotNone(txn)
            admin=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.is_admin.is_(True),m.RFOneAccount.status=='ACTIVE'))
            tid=txn.id
            before=txn.explanation_id
            aid,version=admin.id,admin.session_version
        client=web_app.app.test_client()
        with client.session_transaction() as session:
            session[auth.SESSION_ACCOUNT_KEY]=aid
            session[auth.SESSION_VERSION_KEY]=version
        missing=client.get('/bank/review?view=to_reconcile&search=CLEVERBRIDG')
        found=client.get('/bank/review?view=reconciled&search=CLEVERBRIDG')
        self.assertEqual(missing.status_code,200)
        self.assertEqual(found.status_code,200)
        self.assertNotIn(f'data-transaction-id="{tid}"',missing.data.decode())
        self.assertIn(f'data-row-id="{tid}"',found.data.decode())
        self.assertIn('CLEVERBRIDG CCLEA',found.data.decode())
        with Session(create_engine('sqlite:///' + COPY.as_posix())) as db:
            self.assertEqual(db.get(m.FinancialTransaction,tid).explanation_id,before)

if __name__=='__main__':unittest.main()
