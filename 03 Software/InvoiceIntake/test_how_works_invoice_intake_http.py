#!/usr/bin/env python
"""HTTP checks for the contextual "How … works" help of every Invoice Intake
page (UI_HOW_WORKS_001, `03 Software/Shared UI/How Works Standard.md`).

Every page is fetched through Flask's test client and must render its own
help section exactly once, behind the right link label ("How Invoice Intake
works" on the module home, "How this page works" elsewhere), and the parts
of the help describing role-restricted actions must follow the page's own
permission condition.

Isolation (nothing real is touched):
- a disposable RF-One Data Store database (`RFONE_DATABASE_URL`);
- an isolated Supplier Format Training store (`SUPPLIER_FORMAT_TRAINING_DB_PATH`);
- the acquisition store, the uploads folder and the mailbox store are
  redirected to a temporary directory;
- the document reader is replaced by its own digital-text path over fixed
  page text (no PDF, no OCR, no AWS Textract call), or by a reader that
  fails; the mailbox is never contacted (the page only reads its local store).

Usage:
    python test_how_works_invoice_intake_http.py
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_DATA_STORE_DIR = os.path.normpath(os.path.join(HERE, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import (  # noqa: E402
    cleanup_disposable_test_database_url,
    create_disposable_test_database_url,
)

MODULE_LABEL = "How Invoice Intake works"
PAGE_LABEL = "How this page works"

failures: list[str] = []
passes = 0


def check(description: str, condition: bool) -> None:
    global passes
    if condition:
        passes += 1
    else:
        failures.append(description)


def check_help(name: str, response, section: str, label: str) -> str:
    html = response.get_data(as_text=True)
    check(f"{name}: status 200 (got {response.status_code})", response.status_code == 200)
    check(f"{name}: link data-how-works=\"{section}\"", f'data-how-works="{section}"' in html)
    check(f"{name}: section id help-{section}", f'id="help-{section}"' in html)
    check(f"{name}: label '{label}'", label in html)
    if label == PAGE_LABEL:
        check(f"{name}: no module label on a non-home page", MODULE_LABEL not in html)
    check(f"{name}: exactly one help dialog", html.count('id="rf-help-dialog"') == 1)
    return html


def _prime_line_page(number: str, date: str, total: str) -> str:
    return (
        "PRIME LINE DISTRIBUTORS INVOICE\n"
        f"ROME'S FLAVOURS Number: {number}\n"
        f"Date: {date}\n"
        "BM43 8 CASE SAN BENEDETTO NATURAL PET 1.5L 6/50.7 oz 8 7.99 63.92\n"
        f"TOTAL $ {total}\n"
    )


def run(tmp_dir: str) -> None:
    import document_acquisition
    import document_reader
    import human_review
    import app as flask_app

    # -- redirect every local store/folder to the temporary directory --------
    uploads = os.path.join(tmp_dir, "uploads")
    os.makedirs(uploads, exist_ok=True)
    document_acquisition.UPLOAD_DIR = uploads
    document_acquisition.MIRROR_DIR = os.path.join(uploads, "_provider_mirror")
    acquisitions_db = os.path.join(tmp_dir, "document_acquisitions.db")
    original_store = document_acquisition.AcquisitionStore

    class TempAcquisitionStore(original_store):
        def __init__(self, db_path: str = acquisitions_db):
            super().__init__(db_path)

    document_acquisition.AcquisitionStore = TempAcquisitionStore
    mailbox_db = os.path.join(tmp_dir, "mailbox_acquisition.db")
    flask_app.MAILBOX_DB_PATH = mailbox_db
    human_review.MAILBOX_DB_PATH = mailbox_db
    flask_app.UPLOAD_DIR = uploads

    original_reader = document_reader.read_document
    client = flask_app.app.test_client()
    try:
        # -- module home ------------------------------------------------------
        check_help("upload (/)", client.get("/"), "invoice-intake-upload", MODULE_LABEL)

        # -- result page: saved ----------------------------------------------
        pages = [_prime_line_page("7701001", "07/01/26", "63.92")]
        document_reader.read_document = lambda path, **kw: document_reader._read_digital(pages)
        response = client.post(
            "/upload",
            data={"invoice_file": (io.BytesIO(b"%PDF-1.4 how-works test file A"), "how_works_a.pdf")},
            content_type="multipart/form-data",
        )
        html = check_help("result (saved)", response, "invoice-intake-result", PAGE_LABEL)
        check("result (saved): page shows the saved outcome", "Salvato" in html)

        # -- result page: failed reading -------------------------------------
        def failing_reader(path, **kw):
            raise document_reader.DocumentReadError("test: reading service not reachable")

        document_reader.read_document = failing_reader
        response = client.post(
            "/upload",
            data={"invoice_file": (io.BytesIO(b"%PDF-1.4 how-works test file B"), "how_works_b.pdf")},
            content_type="multipart/form-data",
        )
        html = check_help("result (failed)", response, "invoice-intake-result", PAGE_LABEL)
        check("result (failed): page shows the retry button", "Riprova la lettura" in html)
        document_reader.read_document = original_reader

        # -- pages without reviewer identification ---------------------------
        html = check_help("acquisitions", client.get("/acquisitions"), "invoice-intake-acquisitions", PAGE_LABEL)
        check("acquisitions: FAILED row with Riprova is listed", "FAILED" in html and ">Riprova<" in html)
        check_help("mailbox", client.get("/mailbox"), "invoice-intake-mailbox", PAGE_LABEL)

        for path in ("/review", "/documents", "/training"):
            check(f"{path} without reviewer identification is refused (403)", client.get(path).status_code == 403)

        from rfone_data_store import models as m
        from rfone_data_store.database import create_configured_engine, create_session_factory
        from sqlalchemy import select

        session = create_session_factory(create_configured_engine(os.environ["RFONE_DATABASE_URL"]))()
        try:
            doc_ids = [d.id for d in session.scalars(select(m.PurchaseDocument)).all()]
        finally:
            session.close()
        check("one document was saved by the test upload", len(doc_ids) == 1)
        doc_id = doc_ids[0]

        # -- VIEWER -----------------------------------------------------------
        with client.session_transaction() as sess:
            sess["reviewer_name"] = "tester"
            sess["reviewer_role"] = "VIEWER"
        html = check_help("documents (VIEWER)", client.get("/documents"), "invoice-intake-documents", PAGE_LABEL)
        check("documents (VIEWER): no correction wording", "confirm or correct it" not in html)
        check_help("review queue (VIEWER)", client.get("/review"), "invoice-intake-review-queue", PAGE_LABEL)
        html = check_help("review detail (VIEWER)", client.get(f"/review/{doc_id}"), "invoice-intake-review-detail", PAGE_LABEL)
        check("review detail (VIEWER): correction help hidden", "Confirming and correcting a value" not in html)
        check("review detail (VIEWER): explains the role needed", "requires the REVIEWER or VALIDATOR role" in html)

        # -- REVIEWER ---------------------------------------------------------
        with client.session_transaction() as sess:
            sess["reviewer_role"] = "REVIEWER"
        html = check_help("documents (REVIEWER)", client.get("/documents"), "invoice-intake-documents", PAGE_LABEL)
        check("documents (REVIEWER): correction wording shown", "confirm or correct it" in html)
        html = check_help("review detail (REVIEWER)", client.get(f"/review/{doc_id}"), "invoice-intake-review-detail", PAGE_LABEL)
        check("review detail (REVIEWER): correction help shown", "Confirming and correcting a value" in html)
        check("review detail (REVIEWER): page shows Completa review", "Completa review" in html)

        response = client.post(f"/review/{doc_id}/complete")
        html = response.get_data(as_text=True)
        check("review complete: status 200", response.status_code == 200)
        check("review complete (notice, not operational): no help link", "data-how-works" not in html)
        check("review complete: no help dialog", 'id="rf-help-dialog"' not in html)

        html = check_help("training (REVIEWER)", client.get("/training"), "invoice-intake-supplier-training", PAGE_LABEL)
        check("training (REVIEWER): validate help hidden", "<dt>VALIDATE FORMAT</dt>" not in html)
        check("training (REVIEWER): explains the role needed", "requires the VALIDATOR role" in html)

        # -- VALIDATOR --------------------------------------------------------
        with client.session_transaction() as sess:
            sess["reviewer_role"] = "VALIDATOR"
        html = check_help("training (VALIDATOR)", client.get("/training"), "invoice-intake-supplier-training", PAGE_LABEL)
        check("training (VALIDATOR): validate help shown", "<dt>VALIDATE FORMAT</dt>" in html)

        # -- sign-in page carries no help ------------------------------------
        html = client.get("/review/login").get_data(as_text=True)
        check("review login (sign-in): no help link", "data-how-works" not in html)
    finally:
        document_reader.read_document = original_reader
        document_acquisition.AcquisitionStore = original_store


def main() -> int:
    url = create_disposable_test_database_url("how_works_invoice_intake")
    os.environ["RFONE_DATABASE_URL"] = url
    tmp_dir = tempfile.mkdtemp(prefix="how_works_invoice_intake_")
    os.environ["SUPPLIER_FORMAT_TRAINING_DB_PATH"] = os.path.join(tmp_dir, "isolated_training.db")
    try:
        run(tmp_dir)
    finally:
        os.environ.pop("RFONE_DATABASE_URL", None)
        os.environ.pop("SUPPLIER_FORMAT_TRAINING_DB_PATH", None)
        cleanup_disposable_test_database_url(url)
        shutil.rmtree(tmp_dir, ignore_errors=True)

    total = passes + len(failures)
    if failures:
        print(f"Invoice Intake How Works HTTP tests: FAILURE ({passes} passed, {len(failures)} failed)")
        for description in failures:
            print(f"  FAILED: {description}")
        return 1
    print(f"Invoice Intake How Works HTTP tests: ALL CHECKS PASSED ({passes}/{total})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
