#!/usr/bin/env python
"""Tests for the Aruba mailbox acquisition (Purchased / Invoice Intake).

Uses an in-memory fake IMAP client (`FakeImapClient`) — never a real Aruba
connection — so these tests run offline and never touch real credentials.
Most scenarios use a fake `deliver` function to stay fast and isolated from
OCR/the canonical database; one test (`test_attachment_delivered_through_real_pipeline`)
exercises the REAL `ocr_engine -> parser -> purchased_bridge` pipeline
against a disposable RF-One Data Store database, proving delivery actually
reaches Purchased's canonical persistence, not a second pipeline.

Usage:
    python test_mailbox_acquisition.py
"""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_DATA_STORE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from mailbox_acquisition.acquisition_service import poll_once, redact  # noqa: E402
from mailbox_acquisition.acquisition_store import AcquisitionStore, STATUS_DELIVERED, STATUS_DUPLICATE_TECHNICAL, STATUS_FAILED  # noqa: E402
from mailbox_acquisition.config import MailboxConfig  # noqa: E402
from mailbox_acquisition.imap_client import RawEmailMessage  # noqa: E402

UTC = timezone.utc


class Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, description: str, condition: bool) -> None:
        (self.passed if condition else self.failed).append(description)


# ---------------------------------------------------------------------------
# Fixtures: a fake IMAP client + a small RFC822 message builder
# ---------------------------------------------------------------------------


class FakeImapClient:
    """In-memory stand-in for `ArubaImapClient`, implementing the same
    `ImapClient` contract (`imap_client.ImapClient`). Never touches a real
    mailbox."""

    def __init__(self, messages: dict[str, bytes] | None = None):
        self._messages: dict[str, bytes] = dict(messages or {})
        self.closed = False
        self.list_calls: list[str | None] = []

    def add_message(self, uid: str, raw_bytes: bytes) -> None:
        self._messages[uid] = raw_bytes

    def list_message_uids(self, mailbox: str, since_uid: str | None = None) -> list[str]:
        self.list_calls.append(since_uid)
        uids = sorted(self._messages.keys(), key=int)
        if since_uid is not None:
            uids = [uid for uid in uids if int(uid) > int(since_uid)]
        return uids

    def fetch_message(self, mailbox: str, uid: str) -> RawEmailMessage:
        return RawEmailMessage(uid=uid, raw_bytes=self._messages[uid])

    def close(self) -> None:
        self.closed = True


def _build_email(
    *,
    sender: str = "supplier@example.com",
    subject: str = "Invoice",
    date: datetime | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> bytes:
    """`attachments` is a list of (filename, content, content_type)."""

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "invoices@romesflavours.com"
    msg["Subject"] = subject
    msg["Date"] = format_datetime(date or datetime(2026, 1, 15, 9, 30, tzinfo=UTC))
    msg.set_content("See attached document(s).")
    for filename, content, content_type in attachments or []:
        maintype, _, subtype = content_type.partition("/")
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)
    return bytes(msg)


_FAKE_PDF_BYTES = b"%PDF-1.4 fake pdf content for testing purposes only\n"
_FAKE_JPG_BYTES = b"\xff\xd8\xff\xe0 fake jpg bytes for testing"
_FAKE_PNG_BYTES = b"\x89PNG\r\n\x1a\n fake png bytes for testing"

_next_fake_doc_id = 1000


def _make_fake_deliver(calls: list[str] | None = None, fail_on: set[str] | None = None):
    """A stand-in `deliver` callable: never touches OCR/the database. Returns
    a fresh, incrementing fake PurchaseDocumentId per call; raises for any
    saved path whose original filename is in `fail_on`."""

    global _next_fake_doc_id
    fail_on = fail_on or set()

    def _deliver(saved_path: str) -> int:
        global _next_fake_doc_id
        if calls is not None:
            calls.append(saved_path)
        if any(marker in saved_path for marker in fail_on):
            raise RuntimeError(f"Simulated delivery failure for {saved_path}")
        _next_fake_doc_id += 1
        return _next_fake_doc_id

    return _deliver


def _make_store(tmp_dir: str) -> AcquisitionStore:
    import uuid

    db_path = os.path.join(tmp_dir, f"mailbox_test_{uuid.uuid4().hex}.db")
    return AcquisitionStore(db_path)


def _config() -> MailboxConfig:
    return MailboxConfig(host="imaps.aruba.it", port=993, username="invoices@romesflavours.com", password="super-secret-pw")


# ---------------------------------------------------------------------------
# Scenario 1 — new email with 1 PDF
# ---------------------------------------------------------------------------


def test_single_pdf_attachment_delivered(result: Result, tmp_dir: str) -> None:
    store = _make_store(tmp_dir)
    try:
        imap = FakeImapClient()
        imap.add_message("101", _build_email(attachments=[("invoice-1.pdf", _FAKE_PDF_BYTES, "application/pdf")]))
        calls: list[str] = []
        poll_result = poll_once(_config(), imap, store, deliver=_make_fake_deliver(calls))

        result.check("1 PDF attachment is delivered", poll_result.delivered == 1)
        result.check("deliver() was called exactly once", len(calls) == 1)
        records = store.list_recent()
        result.check("exactly one acquisition record exists", len(records) == 1)
        result.check("the record status is DELIVERED", records[0].status == STATUS_DELIVERED)
        result.check("the stored attachment file actually exists on disk", os.path.isfile(records[0].stored_path))
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Scenario 2 — email with multiple attachments
# ---------------------------------------------------------------------------


def test_multiple_attachments_each_become_candidate(result: Result, tmp_dir: str) -> None:
    store = _make_store(tmp_dir)
    try:
        imap = FakeImapClient()
        imap.add_message(
            "102",
            _build_email(
                attachments=[
                    ("invoice-a.pdf", _FAKE_PDF_BYTES, "application/pdf"),
                    ("invoice-b.pdf", _FAKE_PDF_BYTES + b" different", "application/pdf"),
                    ("support-doc.pdf", _FAKE_PDF_BYTES + b" support", "application/pdf"),
                ]
            ),
        )
        calls: list[str] = []
        poll_result = poll_once(_config(), imap, store, deliver=_make_fake_deliver(calls))

        result.check(
            "an email with 3 attachments produces 3 separate delivered candidates (never merged into one)",
            poll_result.delivered == 3 and len(calls) == 3,
        )
        result.check("3 distinct acquisition records were created", len(store.list_recent()) == 3)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Scenario 3 — JPG/PNG attachments
# ---------------------------------------------------------------------------


def test_image_attachments_jpg_png(result: Result, tmp_dir: str) -> None:
    store = _make_store(tmp_dir)
    try:
        imap = FakeImapClient()
        imap.add_message(
            "103",
            _build_email(
                attachments=[
                    ("receipt.jpg", _FAKE_JPG_BYTES, "image/jpeg"),
                    ("receipt2.png", _FAKE_PNG_BYTES, "image/png"),
                ]
            ),
        )
        poll_result = poll_once(_config(), imap, store, deliver=_make_fake_deliver())
        result.check("both JPG and PNG attachments are recognized and delivered", poll_result.delivered == 2)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Scenario 4 — email without attachments
# ---------------------------------------------------------------------------


def test_email_without_attachments_no_error(result: Result, tmp_dir: str) -> None:
    store = _make_store(tmp_dir)
    try:
        imap = FakeImapClient()
        imap.add_message("104", _build_email(attachments=[]))
        poll_result = poll_once(_config(), imap, store, deliver=_make_fake_deliver())

        result.check("an email with no attachments delivers nothing", poll_result.delivered == 0)
        result.check("no failures are raised for an attachment-less email", not poll_result.attachment_failures and not poll_result.message_failures)
        result.check("no acquisition record is created for a message with nothing documental", store.list_recent() == [])
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Scenario 5 — duplicate message retry (already fully delivered)
# ---------------------------------------------------------------------------


def test_rerunning_poll_does_not_reprocess_delivered_message(result: Result, tmp_dir: str) -> None:
    store = _make_store(tmp_dir)
    try:
        imap = FakeImapClient()
        imap.add_message("105", _build_email(attachments=[("invoice.pdf", _FAKE_PDF_BYTES, "application/pdf")]))
        calls: list[str] = []
        deliver = _make_fake_deliver(calls)

        first = poll_once(_config(), imap, store, deliver=deliver)
        second = poll_once(_config(), imap, store, deliver=deliver)  # same message still visible (no new since-filter change here)

        result.check("first poll delivers the message", first.delivered == 1)
        result.check("second poll (same message) delivers nothing new", second.delivered == 0)
        result.check("deliver() was never called a second time for the same attachment", len(calls) == 1)
        result.check("still exactly one acquisition record (not duplicated)", len(store.list_recent()) == 1)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Scenario 6 — duplicate attachment content hash (different message)
# ---------------------------------------------------------------------------


def test_duplicate_content_hash_across_messages_is_technical_duplicate(result: Result, tmp_dir: str) -> None:
    store = _make_store(tmp_dir)
    try:
        imap = FakeImapClient()
        imap.add_message("106", _build_email(attachments=[("invoice.pdf", _FAKE_PDF_BYTES, "application/pdf")]))
        imap.add_message(
            "107",
            _build_email(sender="forwarder@example.com", attachments=[("invoice-forwarded.pdf", _FAKE_PDF_BYTES, "application/pdf")]),
        )
        calls: list[str] = []
        poll_result = poll_once(_config(), imap, store, deliver=_make_fake_deliver(calls))

        result.check("only the first, byte-identical attachment is actually delivered", poll_result.delivered == 1 and len(calls) == 1)
        result.check("the second (same bytes, different message) is recognized as a technical duplicate", poll_result.duplicates == 1)

        records = {r.message_uid: r for r in store.list_recent()}
        result.check("the duplicate record references the same PurchaseDocumentId as the original", records["107"].purchase_document_id == records["106"].purchase_document_id)
        result.check("the duplicate record's own status is DUPLICATE_TECHNICAL", records["107"].status == STATUS_DUPLICATE_TECHNICAL)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Scenario 7 — one attachment failure never blocks the others
# ---------------------------------------------------------------------------


def test_one_attachment_failure_does_not_block_others(result: Result, tmp_dir: str) -> None:
    store = _make_store(tmp_dir)
    try:
        imap = FakeImapClient()
        imap.add_message(
            "108",
            _build_email(
                attachments=[
                    ("good-invoice.pdf", _FAKE_PDF_BYTES, "application/pdf"),
                    ("BAD-invoice.pdf", _FAKE_PDF_BYTES + b"x", "application/pdf"),
                    ("also-good.pdf", _FAKE_PDF_BYTES + b"y", "application/pdf"),
                ]
            ),
        )
        poll_result = poll_once(_config(), imap, store, deliver=_make_fake_deliver(fail_on={"BAD-invoice"}))

        result.check("the two good attachments are delivered despite the third failing", poll_result.delivered == 2)
        result.check("the bad attachment is recorded as exactly one failure", len(poll_result.attachment_failures) == 1)

        records = {r.attachment_filename: r for r in store.list_recent()}
        result.check("good-invoice.pdf is DELIVERED", records["good-invoice.pdf"].status == STATUS_DELIVERED)
        result.check("also-good.pdf is DELIVERED", records["also-good.pdf"].status == STATUS_DELIVERED)
        result.check("BAD-invoice.pdf is FAILED, not silently dropped", records["BAD-invoice.pdf"].status == STATUS_FAILED)
        result.check("the failed record carries a failure reason", bool(records["BAD-invoice.pdf"].failure_reason))
    finally:
        store.close()


def test_failed_attachment_is_retried_and_can_later_succeed(result: Result, tmp_dir: str) -> None:
    store = _make_store(tmp_dir)
    try:
        imap = FakeImapClient()
        imap.add_message("109", _build_email(attachments=[("flaky.pdf", _FAKE_PDF_BYTES, "application/pdf")]))

        first = poll_once(_config(), imap, store, deliver=_make_fake_deliver(fail_on={"flaky"}))
        result.check("first attempt fails and is recorded", first.delivered == 0 and len(first.attachment_failures) == 1)

        record = store.list_recent()[0]
        result.check("retry_count was incremented on failure", record.retry_count == 1)

        # A later poll cycle (e.g. next interval) must retry the same
        # message even though it is not "new" relative to the cursor --
        # get_retry_message_uids() must resurface it.
        second = poll_once(_config(), imap, store, deliver=_make_fake_deliver())
        result.check("a subsequent poll retries the previously-failed attachment and now succeeds", second.delivered == 1)
        result.check("the record is now DELIVERED", store.list_recent()[0].status == STATUS_DELIVERED)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Scenario 8 — restart does not duplicate
# ---------------------------------------------------------------------------


def test_restart_with_fresh_store_instance_does_not_duplicate(result: Result, tmp_dir: str) -> None:
    db_path = os.path.join(tmp_dir, "mailbox_restart_test.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    imap = FakeImapClient()
    imap.add_message("110", _build_email(attachments=[("invoice.pdf", _FAKE_PDF_BYTES, "application/pdf")]))
    calls: list[str] = []
    deliver = _make_fake_deliver(calls)

    store_1 = AcquisitionStore(db_path)
    try:
        poll_once(_config(), imap, store_1, deliver=deliver)
    finally:
        store_1.close()

    # Simulate a process restart: brand-new AcquisitionStore instance over
    # the SAME database file, and re-poll with no "since" advantage (as if
    # the cursor file/connection had to be rebuilt from scratch).
    store_2 = AcquisitionStore(db_path)
    try:
        second_result = poll_once(_config(), imap, store_2, deliver=deliver)
        result.check("restarting the acquisition process does not re-deliver an already-acquired attachment", second_result.delivered == 0)
        result.check("deliver() was called exactly once across both process 'runs'", len(calls) == 1)
        result.check("still exactly one acquisition record after restart", len(store_2.list_recent()) == 1)
    finally:
        store_2.close()
    os.remove(db_path)


# ---------------------------------------------------------------------------
# Scenario 9 — provenance recorded correctly
# ---------------------------------------------------------------------------


def test_provenance_fields_recorded(result: Result, tmp_dir: str) -> None:
    store = _make_store(tmp_dir)
    try:
        imap = FakeImapClient()
        sent_at = datetime(2026, 3, 4, 8, 15, tzinfo=UTC)
        imap.add_message(
            "111",
            _build_email(
                sender="US Foods <billing@usfoods.example>",
                subject="Invoice #INV-9911",
                date=sent_at,
                attachments=[("INV-9911.pdf", _FAKE_PDF_BYTES, "application/pdf")],
            ),
        )
        poll_once(_config(), imap, store, deliver=_make_fake_deliver())

        record = store.list_recent()[0]
        expected_hash = hashlib.sha256(_FAKE_PDF_BYTES).hexdigest()
        result.check("mailbox is recorded", record.mailbox == _config().mailbox)
        result.check("message_uid is recorded", record.message_uid == "111")
        result.check("sender is recorded", record.sender == "US Foods <billing@usfoods.example>")
        result.check("subject is recorded", record.subject == "Invoice #INV-9911")
        result.check("attachment filename is recorded", record.attachment_filename == "INV-9911.pdf")
        result.check("content hash matches the actual attachment bytes", record.content_hash == expected_hash)
        result.check("received_at reflects the email's own Date header (2026-03-04)", record.received_at is not None and "2026-03-04" in record.received_at)
        result.check("ingested_at (our own acquisition timestamp) is recorded", bool(record.ingested_at))
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Scenario 10 — attachment actually delivered through the REAL Invoice Intake pipeline
# ---------------------------------------------------------------------------


def test_attachment_delivered_through_real_pipeline(result: Result, tmp_dir: str) -> None:
    from rfone_data_store.database import (
        cleanup_disposable_test_database_url,
        create_configured_engine,
        create_disposable_test_database_url,
        create_session_factory,
    )
    from rfone_data_store import models as m

    _REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    real_pdf_path = os.path.join(
        _REPO_ROOT, "01 Domains", "Shared Domains", "Administration", "Invoice Intake", "Invoices", "Raw", "Invoice 6855.pdf"
    )
    if not os.path.isfile(real_pdf_path):
        result.check("real PDF sample available for end-to-end delivery test", False)
        return

    with open(real_pdf_path, "rb") as handle:
        real_pdf_bytes = handle.read()

    url = create_disposable_test_database_url("mailbox_acquisition_e2e")
    os.environ["RFONE_DATABASE_URL"] = url
    try:
        from mailbox_acquisition.acquisition_service import deliver_to_invoice_intake  # local import: needs RFONE_DATABASE_URL set first

        store = _make_store(tmp_dir)
        try:
            imap = FakeImapClient()
            imap.add_message("112", _build_email(attachments=[("Invoice 6855.pdf", real_pdf_bytes, "application/pdf")]))
            poll_result = poll_once(_config(), imap, store, deliver=deliver_to_invoice_intake)

            result.check("the real pipeline delivers the email attachment", poll_result.delivered == 1)
            record = store.list_recent()[0]
            result.check("a real PurchaseDocumentId was recorded", record.purchase_document_id is not None)

            engine = create_configured_engine(url)
            session = create_session_factory(engine)()
            try:
                document = session.get(m.PurchaseDocument, record.purchase_document_id)
                result.check(
                    "a real PurchaseDocument exists in Purchased's canonical persistence, sourced from the mailbox attachment",
                    document is not None and len(document.lines) > 0,
                )
            finally:
                session.close()
        finally:
            store.close()
    finally:
        cleanup_disposable_test_database_url(url)
        os.environ.pop("RFONE_DATABASE_URL", None)


# ---------------------------------------------------------------------------
# Scenario 11 — no secret ever appears in a log/failure reason
# ---------------------------------------------------------------------------


def test_no_secret_in_failure_reason_or_output(result: Result, tmp_dir: str) -> None:
    config = _config()
    raw_message = f"IMAP login failed for user with password {config.password} rejected"
    scrubbed = redact(raw_message, config)
    result.check("redact() removes the password from an arbitrary message", config.password not in scrubbed)
    result.check("redact() replaces it with a placeholder, not silently dropping context", "***" in scrubbed)

    store = _make_store(tmp_dir)
    try:
        imap = FakeImapClient()
        imap.add_message("113", _build_email(attachments=[("secret-test.pdf", _FAKE_PDF_BYTES, "application/pdf")]))

        def _deliver_leaking_password(saved_path: str) -> int:
            raise RuntimeError(f"pretend failure exposing password={config.password}")

        poll_once(config, imap, store, deliver=_deliver_leaking_password)
        record = store.list_recent()[0]
        result.check("a failure reason derived from an exception never contains the raw password", config.password not in (record.failure_reason or ""))
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main() -> int:
    import tempfile
    import shutil

    tmp_dir = tempfile.mkdtemp(prefix="mailbox_acquisition_test_")
    result = Result()
    try:
        for test_fn in (
            test_single_pdf_attachment_delivered,
            test_multiple_attachments_each_become_candidate,
            test_image_attachments_jpg_png,
            test_email_without_attachments_no_error,
            test_rerunning_poll_does_not_reprocess_delivered_message,
            test_duplicate_content_hash_across_messages_is_technical_duplicate,
            test_one_attachment_failure_does_not_block_others,
            test_failed_attachment_is_retried_and_can_later_succeed,
            test_restart_with_fresh_store_instance_does_not_duplicate,
            test_provenance_fields_recorded,
            test_attachment_delivered_through_real_pipeline,
            test_no_secret_in_failure_reason_or_output,
        ):
            test_fn(result, tmp_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    total = len(result.passed) + len(result.failed)
    if not result.failed:
        print(f"Mailbox acquisition tests: SUCCESS ({len(result.passed)}/{total} checks passed)")
        return 0
    print(f"Mailbox acquisition tests: FAILURE ({len(result.passed)} passed, {len(result.failed)} failed)")
    for description in result.failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
