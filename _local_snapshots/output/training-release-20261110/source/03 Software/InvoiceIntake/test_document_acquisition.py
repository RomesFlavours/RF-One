#!/usr/bin/env python
"""INVOICE_SCAN_ACQUISITION_001 — acquisition of scanned/photographed invoices.

Deterministic checks with a FAKE Textract client (no AWS call). The real
AWS Textract behaviour on real documents is verified separately (task
report); simulated responses never replace that.

Isolation: a throwaway RF-One database (RFONE_DATABASE_URL), and the
module's uploads/ and acquisition store redirected to a temporary folder.

Checks:
  - a page Textract cannot read -> acquisition FAILED, no invoice, no
    supplier, original preserved; retry once the service works -> the
    invoice is created exactly once; further retries create nothing;
  - the identical file uploaded again -> no new invoice, no new file;
  - a save that breaks between two invoices of one file -> FAILED; the
    retry saves only the missing invoice;
  - an unexpected reader error -> FAILED (never an HTTP 500 / an invoice);
  - pages grouped into invoices by the invoice number read on each page;
    several supplier readings kept; unreadable amounts flagged;
  - exact amount check: no 5% tolerance; total vs balance due; an invoice
    with no line is never complete; quantity x unit price != amount flagged.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
_TMP = tempfile.mkdtemp(prefix="invoice_acq_test_")
os.environ["RFONE_DATABASE_URL"] = "sqlite:///" + os.path.join(_TMP, "rfone.db").replace(os.sep, "/")

import document_acquisition as acq  # noqa: E402
import document_reader  # noqa: E402
import purchased_bridge  # noqa: E402
from providers import textract_provider as tp  # noqa: E402

acq.UPLOAD_DIR = os.path.join(_TMP, "uploads")
acq.MIRROR_DIR = os.path.join(acq.UPLOAD_DIR, "_provider_mirror")
STORE_PATH = os.path.join(_TMP, "acq.db")

PASSED, FAILED = [], []


def check(description, condition):
    (PASSED if condition else FAILED).append(description)
    if not condition:
        print("FAILED:", description)


def field(ftype, value, label=None, page=1, conf=99.0):
    return {"Type": {"Text": ftype}, "LabelDetection": {"Text": label} if label else None,
            "ValueDetection": {"Text": value, "Confidence": conf,
                               "Geometry": {"BoundingBox": {"Left": 0.1, "Top": 0.2, "Width": 0.1, "Height": 0.02}}},
            "PageNumber": page}


def page_response(summary, lines):
    return {"ExpenseDocuments": [{"ExpenseIndex": 1, "SummaryFields": summary,
                                  "LineItemGroups": [{"LineItems": [{"LineItemExpenseFields": l} for l in lines]}]}],
            "Blocks": []}


GOOD_PAGE = page_response(
    [field("VENDOR_NAME", "Acme Foods"), field("INVOICE_RECEIPT_ID", "A-100"), field("INVOICE_RECEIPT_DATE", "07/01/2026"),
     field("SUBTOTAL", "30.00"), field("TAX", "1.50"), field("TOTAL", "31.50")],
    [[field("ITEM", "Tomatoes"), field("QUANTITY", "2"), field("UNIT_PRICE", "10.00"), field("PRICE", "20.00")],
     [field("ITEM", "Basil"), field("QUANTITY", "1"), field("UNIT_PRICE", "10.00"), field("PRICE", "10.00")]],
)


class FakeTextract:
    def __init__(self, responses, fail_pages=()):
        self.responses, self.fail_pages, self.calls = list(responses), set(fail_pages), 0

    def analyze_expense(self, Document):
        self.calls += 1
        if self.calls in self.fail_pages:
            raise RuntimeError("ThrottlingException: Rate exceeded (simulated)")
        return self.responses[(self.calls - 1) % len(self.responses)]


def reader_with(client):
    return lambda path: document_reader.read_document(path, textract_client_factory=lambda: client)


def count(sql):
    con = sqlite3.connect(os.environ["RFONE_DATABASE_URL"].replace("sqlite:///", ""))
    try:
        return con.execute(sql).fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        con.close()


def main():
    store = acq.AcquisitionStore(STORE_PATH)
    photo = b"\xff\xd8\xff fake jpeg bytes 1"

    # 1. a page not read -> FAILED, nothing created; retry -> created once
    outcome = acq.acquire_bytes(photo, "photo.jpg", store=store, reader=reader_with(FakeTextract([GOOD_PAGE], fail_pages={1})))
    check("a page Textract cannot read -> acquisition FAILED", outcome.status == acq.STATUS_FAILED)
    check("the error names the page and the service reason", "page 1" in (outcome.error or "") and "Throttling" in (outcome.error or ""))
    check("no invoice and no supplier created by a failed read",
          count("select count(*) from purchase_documents") == 0 and count("select count(*) from suppliers") == 0)
    check("the original is preserved for the retry", len(os.listdir(acq.UPLOAD_DIR)) == 1)
    retry = acq.retry(outcome.acquisition_id, store=store, reader=reader_with(FakeTextract([GOOD_PAGE])))
    check("retry once the service works -> ACQUIRED with exactly one invoice",
          retry.status == acq.STATUS_ACQUIRED and len(retry.purchase_document_ids) == 1
          and count("select count(*) from purchase_documents") == 1)
    again = acq.retry(outcome.acquisition_id, store=store, reader=reader_with(FakeTextract([GOOD_PAGE])))
    check("a further retry creates nothing", again.already_acquired and count("select count(*) from purchase_documents") == 1)

    # 2. identical file again
    dup = acq.acquire_bytes(photo, "photo-copy.jpg", store=store, reader=reader_with(FakeTextract([GOOD_PAGE])))
    check("identical content uploaded again -> already acquired, same invoice, no new file",
          dup.already_acquired and dup.purchase_document_ids == retry.purchase_document_ids
          and len([f for f in os.listdir(acq.UPLOAD_DIR) if not f.startswith("_")]) == 1)

    # 3. save breaks between two invoices of one file -> retry saves only the missing one
    two_invoices = [GOOD_PAGE, page_response(
        [field("VENDOR_NAME", "Acme Foods"), field("INVOICE_RECEIPT_ID", "A-200"), field("TOTAL", "10.00")],
        [[field("ITEM", "Oil"), field("QUANTITY", "1"), field("UNIT_PRICE", "10.00"), field("PRICE", "10.00")]])]
    original_save = purchased_bridge.save_read_invoice
    calls = {"n": 0}

    def flaky_save(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("database is locked (simulated)")
        return original_save(*a, **k)

    purchased_bridge.save_read_invoice = flaky_save
    def reader_two(path):
        # Same mapping as a real two-page scan, built from the simulated pages
        # (the fake file itself is not a real PDF to split).
        results = [{"page": i + 1, "response": r} for i, r in enumerate(two_invoices)]
        mapped = tp.map_pages_to_invoices(results)
        invoices = [document_reader.ReadInvoice(
            header=m["header"], lines=m["lines"], amounts=m["amounts"], pages=m["pages"], raw_text=m["text"],
            provenance=m["provenance"], conflicts=m["conflicts"], unreadable=m["unreadable"],
            page_range_label=f"p{m['pages'][0]}") for m in mapped]
        return document_reader.ReadResult(document_reader.METHOD_TEXTRACT, 2, [1, 2], invoices, {"textract_pages": results})
    part = acq.acquire_bytes(b"%PDF fake two-invoice scan", "two.pdf", store=store, reader=reader_two)
    purchased_bridge.save_read_invoice = original_save
    check("a save interrupted between two invoices -> FAILED, the first invoice kept",
          part.status == acq.STATUS_FAILED and len(part.purchase_document_ids) == 1)
    done = acq.retry(part.acquisition_id, store=store, reader=reader_two)
    check("the retry saves only the missing invoice (2 in total, none twice)",
          done.status == acq.STATUS_ACQUIRED and len(done.purchase_document_ids) == 2
          and count("select count(*) from purchase_documents where document_number in ('A-100','A-200')") == 2)

    # 4. unexpected reader error
    def broken(path):
        raise KeyError("other_fields")

    bad = acq.acquire_bytes(b"\xff\xd8 another photo", "bad.jpg", store=store, reader=broken)
    check("an unexpected reader error -> FAILED with a message, no invoice", bad.status == acq.STATUS_FAILED and "KeyError" in (bad.error or ""))

    # 5. grouping, supplier readings, unreadable amounts
    pages = [
        {"page": 1, "response": page_response([field("VENDOR_NAME", "KEITH CO."), field("INVOICE_RECEIPT_ID", "90079477"),
                                               field("TOTAL", "302.74")], [])},
        {"page": 2, "response": page_response([field("VENDOR_NAME", "BEN E KEITH FOODS"), field("INVOICE_RECEIPT_ID", "90080721"),
                                               field("VENDOR_NAME", "Ben E. Keith Lockbox"), field("SUBTOTAL", "Totals $ * Total")], [])},
        {"page": 3, "response": page_response([field("TAX", ".89"), field("TOTAL", "1257.66")], [])},
    ]
    invoices = tp.map_pages_to_invoices(pages)
    check("pages grouped by invoice number: [1] and [2, 3]", [i["pages"] for i in invoices] == [[1], [2, 3]])
    check("a page without a number continues the current invoice (total and tax of page 3)",
          invoices[1]["amounts"].get("total") == "1257.66" and invoices[1]["amounts"].get("tax") == "0.89")
    check("several supplier readings on one invoice are all kept",
          invoices[1]["header"].get("supplier_name_readings") == ["BEN E KEITH FOODS", "Ben E. Keith Lockbox"])
    check("an amount that is not a number is flagged unreadable, never coerced",
          [u["field"] for u in invoices[1]["unreadable"]] == ["subtotal"])
    check("each value keeps its page and position",
          invoices[1]["provenance"]["total"]["page"] == 3 and invoices[1]["provenance"]["total"]["bbox"] is not None)

    # 6. exact amount check
    def reasons(lines, total, amounts):
        rl = [{"line_type": t, "source_amount_minor": a, "quantity": None, "_unit_price_exact": None} for t, a in lines]
        return purchased_bridge._reading_reasons(rl, total, {"amounts": amounts})

    check("a 4% difference is no longer accepted (lines 1452.00 vs total 1394.39)",
          any("unexplained difference" in r for r in reasons([("PRODUCT", 145200)], 139439, {})))
    check("lines + tax = total exactly -> no reason", reasons([("PRODUCT", 3000)], 3150, {"subtotal": "30.00", "tax": "1.50"}) == [])
    check("balance due different from total without any payment shown -> flagged",
          any("no payment or credit" in r for r in reasons([("PRODUCT", 145200)], 145200, {"balance_due": "1394.39"})))
    check("total - paid = balance -> no reason",
          reasons([("PRODUCT", 145200)], 145200, {"balance_due": "1394.39", "amount_paid": "-57.61"}) == [])
    check("an invoice with no line is never complete", any("no invoice line" in r for r in reasons([], 3150, {})))
    rl = [{"line_type": "PRODUCT", "source_amount_minor": 14990, "quantity": __import__("decimal").Decimal("1"),
           "_unit_price_exact": __import__("decimal").Decimal("14.990")}]
    check("quantity x unit price != amount is flagged (Samuels photo: 1 x 14.990 vs 149.90)",
          any("quantity 1 x unit price 14.990" in r for r in purchased_bridge._reading_reasons(rl, None, {})))
    check("a credit memo (negative line and total) balances with signed amounts",
          reasons([("PRODUCT", -3000)], -3000, {}) == [])

    store.close()
    print(f"Document acquisition tests: {'SUCCESS' if not FAILED else 'FAILURE'} ({len(PASSED)} passed, {len(FAILED)} failed)")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
