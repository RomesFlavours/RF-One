"""Run with the RF-One venv, data-store/web on PYTHONPATH; no live DB writes."""
import copy
import csv
import io
import os
from pathlib import Path
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import paypal_reports as pp
from bank_work_routes import receive


def sample(identifier='PAY1', status='Pending', amount='-10.00'):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=sorted(pp.HEADERS | {'TimeZone'}))
    writer.writeheader()
    writer.writerow(dict(Date='03/01/2026', Time='12:00:00', TimeZone='PST', Name='Example',
        Type='General Authorization', Status=status, Currency='USD', Amount=amount,
        Fees='0.00', Total=amount, **{'Transaction ID': identifier}))
    return stream.getvalue().encode('utf-8-sig')


class PayPalImportTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        m.BankFlowArtifact.__table__.create(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_repeat_and_overlapping_status_update(self):
        first, created = pp.ingest(self.db, 'a.csv', sample(), None)
        self.assertTrue(created)
        repeat, created = pp.ingest(self.db, 'renamed.csv', sample(), None)
        self.assertFalse(created)
        self.assertEqual(repeat['new_transactions'], 0)
        later, created = pp.ingest(self.db, 'b.csv', sample(status='Completed'), None)
        self.assertTrue(created)
        self.assertEqual(later['new_transactions'], 0)
        merged = pp.evidence(pp.reports(self.db))
        self.assertEqual(len(merged), 1)
        self.assertEqual({e['status'] for e in merged[0]['observations']}, {'Pending', 'Completed'})

    def test_source_upload_path(self):
        result = receive(self.db, 'paypal.csv', sample(), None)
        self.assertEqual(result['state'], 'PAYPAL_LOADED')
        self.assertEqual(result['new_rows'], 1)
        result = receive(self.db, 'paypal.csv', sample(), None)
        self.assertEqual(result['state'], 'ALREADY_LOADED')
        self.assertEqual(len(pp.reports(self.db)), 1)

    def test_malformed_no_partial_import(self):
        bad = sample().replace(b'-10.00', b'bad')
        with self.assertRaises(ValueError):
            pp.ingest(self.db, 'bad.csv', bad, None)
        self.assertEqual(pp.reports(self.db), [])

    def test_no_implicit_account_or_status_resolution(self):
        report = pp.parse_csv(sample())
        self.assertIsNone(report['account'])
        conflict = copy.deepcopy(report)
        conflict['events'][0]['total_minor'] = -2000
        self.assertTrue(pp.evidence([report, conflict])[0]['conflict'])
        a, b = copy.deepcopy(report), copy.deepcopy(report)
        a['account'], b['account'] = 'one@example.com', 'two@example.com'
        self.assertTrue(pp.evidence([a, b])[0]['conflict'])

    def test_identical_observations_not_counted_twice(self):
        report = pp.parse_csv(sample())
        report['events'].append(copy.deepcopy(report['events'][0]))
        self.assertEqual(len(pp.evidence([report, report])[0]['observations']), 1)

    def test_supplied_sources(self):
        root = Path(__file__).resolve().parent.parent
        csv_path = root / 'Documents/Specificatori Bancari/Paypal/Paypal Year to 12 Nov 26.CSV'
        pdf_path = Path(os.environ['TEMP']) / 'statement-Mar-2026.pdf'
        if not csv_path.exists() or not pdf_path.exists():
            self.skipTest('Optional user-provided sample files are unavailable.')
        first = receive(self.db, csv_path.name, csv_path.read_bytes(), None)
        self.assertEqual(first['rows'], 343)
        pdf = receive(self.db, pdf_path.name, pdf_path.read_bytes(), None)
        self.assertEqual(pdf['state'], 'PAYPAL_LOADED')
        self.assertEqual(pdf['rows'], 23)
        self.assertEqual(pdf['new_rows'], 0)
        merged = pp.evidence(pp.reports(self.db))
        self.assertEqual(len(merged), 282)
        katom = next(e for e in merged if e['transaction_id'] == '0TG21520VF5225147')
        self.assertIn('Chase - Checking x-3376', katom['funding'])
        refund = next(e for e in merged if e['transaction_id'] == '9T6688860C619194K')
        self.assertEqual(refund['reference_ids'], ['0TG21520VF5225147'])
        again = receive(self.db, pdf_path.name, pdf_path.read_bytes(), None)
        self.assertEqual(again['state'], 'ALREADY_LOADED')
        self.assertEqual(len(pp.reports(self.db)), 2)


if __name__ == '__main__':
    unittest.main()
