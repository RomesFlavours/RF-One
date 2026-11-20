"""ADP Payroll Summary import. Run with the RF-One venv, data-store/web on PYTHONPATH; no live DB writes.

Optional: set ADP_SAMPLE_DIR to a folder with the real reports to also check them (never committed).
"""
import io
import os
from pathlib import Path
import unittest

import openpyxl
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import adp_reports as adp

HEADERS = ["Pay Frequency", "Department", "Check Date", "Name", "Hours", "Total Paid", "Tax Withheld",
           "Deductions", "Net Pay", "Payment Details/Check No", "Employer Liability", "Total Expenses"]
ROWS = [
    ["Biweekly", "", "01/21/2026 ", "Doe, Jane", 49.19, 540.11, 216.66, 0, 323.45, "0", 154.25, 694.36],
    ["Biweekly", "", "01/21/2026  - Void", "Doe, Jane", -49.19, -540.11, -164.85, 0, -375.26, "0", -129.52, -669.63],
    ["Biweekly", "", "01/21/2026 ", "Roe, Ann", 95.18, 1109.92, 1109.92, 0, 0, "\n\t\t\xa0\n\t", 480.26, 1590.18],
    ["Biweekly", "", "01/22/2026 ", "SAMPLE CPA PA", 0, 345, 0, 0, 345, "DD", 0, 345],
]


def workbook(rows=ROWS, count=None, totals=None):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Payroll Summary"
    for line in ("Company: SAMPLE LLC", "Report: Payroll Summary", "Check Dates From: 1/21/2026 - Payroll 1",
                 "To: 1/22/2026 - Payroll 1"):
        sheet.append([line])
    sheet.append([])
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    sheet.append([])
    paid = sum(1 for r in rows if "Void" not in r[2] and r[8] != 0)
    sheet.append([f"Company Totals and Count :  {paid if count is None else count}"])
    sums = [round(sum(r[i] for r in rows), 2) for i in (4, 5, 6, 7, 8)] + [""] + \
           [round(sum(r[i] for r in rows), 2) for i in (10, 11)]
    sheet.append(["", "", "", ""] + (totals or sums))
    sheet.append(["Pay Frequency Totals and Count"])
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


class AdpImportTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        m.BankFlowArtifact.__table__.create(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def lines(self):
        return self.db.execute(text("SELECT * FROM bank_adp_payroll_lines ORDER BY source_row")).mappings().all()

    def test_all_rows_and_fields_kept(self):
        saved, created = adp.ingest(self.db, "a.xlsx", workbook(), None)
        self.assertTrue(created)
        rows = self.lines()
        self.assertEqual(len(rows), 4)
        void = rows[1]
        self.assertEqual((void["is_void"], void["check_date"], void["net_pay_minor"], void["hours"]),
                         (1, "2026-01-21", -37526, "-49.19"))
        self.assertEqual(void["check_date_original"], "01/21/2026  - Void")
        zero = rows[2]
        self.assertEqual((zero["net_pay_minor"], zero["payment_details"]), (0, ""))
        self.assertIn("\xa0", zero["payment_details_original"])
        self.assertEqual(rows[0]["source_row"], 7)   # Excel row number: 4 title rows, blank, header
        self.assertEqual(rows[0]["company"], "SAMPLE LLC")
        report = self.db.execute(text("SELECT * FROM bank_adp_reports")).mappings().one()
        self.assertEqual((report["line_count"], report["declared_count"], report["file_name"]), (4, 2, "a.xlsx"))
        self.assertEqual(saved["payments"][0], ["Doe, Jane", 32345, "2026-01-21"])

    def test_same_file_twice_no_duplicates(self):
        adp.ingest(self.db, "a.xlsx", workbook(), None)
        _, created = adp.ingest(self.db, "renamed.xlsx", workbook(), None)
        self.assertFalse(created)
        self.assertEqual(len(self.lines()), 4)
        self.assertEqual(self.db.execute(text("SELECT COUNT(*) FROM bank_adp_reports")).scalar(), 1)

    def test_rejects_count_or_total_mismatch(self):
        with self.assertRaises(ValueError):
            adp.parse(workbook(count=4))   # 4 rows, but only 2 payments
        bad = [round(sum(r[i] for r in ROWS), 2) for i in (4, 5, 6, 7)] + [1.0, "", 0, 0]
        with self.assertRaises(ValueError):
            adp.parse(workbook(totals=bad))

    def test_payroll_verification_view_unchanged(self):
        saved, _ = adp.ingest(self.db, "a.xlsx", workbook(), None)
        payments = adp.Payments([saved])
        from datetime import date
        self.assertEqual(payments.matches("CPA SAMPLE PA", -34500, date(2026, 1, 23), 3), [date(2026, 1, 22)])
        self.assertEqual(payments.matches("Jane Doe", -32345, date(2026, 1, 21), 3), [date(2026, 1, 21)])

    @unittest.skipUnless(os.environ.get("ADP_SAMPLE_DIR"), "real reports not provided")
    def test_real_reports(self):
        for path in sorted(Path(os.environ["ADP_SAMPLE_DIR"]).glob("*.xlsx")):
            report = adp.parse(path.read_bytes())
            self.assertEqual(adp.payment_count(report["lines"]), report["declared_count"], path.name)
            self.assertEqual(adp.line_totals(report["lines"]), report["declared_totals"], path.name)


if __name__ == "__main__":
    unittest.main()
