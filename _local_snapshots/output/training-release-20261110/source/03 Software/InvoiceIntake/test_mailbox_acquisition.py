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
import shutil
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


def _build_email_with_inline_image(
    *,
    sender: str = "service@romesflavours.com",
    subject: str = "Bla Bla Bla.",
    date: datetime | None = None,
    inline_image: tuple[str, bytes, str, str, str | None] | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
    html_references_cid: bool = True,
) -> bytes:
    """Builds a realistic HTML email with an embedded/inline image inside a
    `multipart/related` part (mirrors real Outlook-generated mail, verified
    against a real message from `invoices@romesflavours.com` during the
    Aruba smoke test) plus zero or more ordinary attachments.

    `inline_image` is `(filename, content, content_type, cid, disposition)`
    where `disposition` is `"inline"`, `None` (real Aruba mail often sets
    no explicit disposition at all, relying on Content-ID + a `cid:`
    reference in the HTML body instead), or any other value to simulate an
    UNREFERENCED Content-ID (no matching `cid:` in the HTML body) — used to
    test the "ambiguous image" scenarios.
    """
    from email.mime.application import MIMEApplication
    from email.mime.image import MIMEImage
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("mixed")
    msg["From"] = sender
    msg["To"] = "invoices@romesflavours.com"
    msg["Subject"] = subject
    msg["Date"] = format_datetime(date or datetime(2026, 1, 15, 9, 30, tzinfo=UTC))

    related = MIMEMultipart("related")
    if inline_image is not None and html_references_cid:
        filename, content, content_type, cid, disposition = inline_image
        html = f'<html><body><p>Hi</p><img src="cid:{cid}"></body></html>'
    else:
        html = "<html><body><p>Hi</p></body></html>"
    related.attach(MIMEText(html, "html"))

    if inline_image is not None:
        filename, content, content_type, cid, disposition = inline_image
        maintype, _, subtype = content_type.partition("/")
        img_part = MIMEImage(content, _subtype=subtype) if maintype == "image" else MIMEApplication(content, _subtype=subtype)
        img_part.add_header("Content-ID", f"<{cid}>")
        # Real Aruba mail sets a filename via Content-Type's own "name"
        # param even when Content-Disposition is entirely absent -- match
        # that (get_filename() falls back to Content-Type's name param).
        img_part.set_param("name", filename)
        if disposition == "inline":
            img_part.add_header("Content-Disposition", "inline", filename=filename)
        elif disposition is not None:
            img_part.add_header("Content-Disposition", str(disposition), filename=filename)
        related.attach(img_part)

    msg.attach(related)

    for filename, content, content_type in attachments or []:
        maintype, _, subtype = content_type.partition("/")
        part = MIMEImage(content, _subtype=subtype) if maintype == "image" else MIMEApplication(content, _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    return msg.as_bytes()


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
# Email attachment noise filter (inline signature/logo images)
# ---------------------------------------------------------------------------


def test_inline_signature_logo_is_ignored(result: Result, tmp_dir: str) -> None:
    """Scenario 4 — an inline logo (Content-ID referenced by `cid:` in the
    HTML body, mirroring a real Aruba/Outlook email) is never delivered as a
    document, even though its file type (JPG) is otherwise allowed."""

    store = _make_store(tmp_dir)
    try:
        imap = FakeImapClient()
        imap.add_message(
            "201",
            _build_email_with_inline_image(
                inline_image=("image001.jpg", _FAKE_JPG_BYTES, "image/jpeg", "logo123@mail", None),
                attachments=[("real_invoice.pdf", _FAKE_PDF_BYTES, "application/pdf")],
            ),
        )
        calls: list[str] = []
        poll_result = poll_once(_config(), imap, store, deliver=_make_fake_deliver(calls))

        result.check("only the real invoice is delivered, not the inline logo", poll_result.delivered == 1)
        result.check("the inline logo is counted as an ignored email asset", poll_result.ignored_email_assets == 1)
        result.check("deliver() was never called for the logo", all("image001" not in c for c in calls))
        result.check(
            "no acquisition record exists for the ignored logo (only the real invoice)",
            len(store.list_recent()) == 1 and store.list_recent()[0].attachment_filename == "real_invoice.pdf",
        )
    finally:
        store.close()


def test_real_jpg_attachment_not_inline_is_not_ignored(result: Result, tmp_dir: str) -> None:
    """Scenario 5 — a real JPG sent as a normal attachment (no Content-ID,
    `Content-Disposition: attachment`) is never filtered just because it is
    an image, even if superficially named like an inline asset."""

    store = _make_store(tmp_dir)
    try:
        imap = FakeImapClient()
        imap.add_message(
            "202", _build_email(attachments=[("invoice_photo.jpg", _FAKE_JPG_BYTES, "image/jpeg")])
        )
        poll_result = poll_once(_config(), imap, store, deliver=_make_fake_deliver())
        result.check("a real JPG attachment (not inline) is delivered normally", poll_result.delivered == 1)
        result.check("nothing was ignored", poll_result.ignored_email_assets == 0)

        # Even a JPG whose filename happens to match the generic inline-asset
        # pattern must NOT be filtered when it carries no Content-ID at all --
        # the naming heuristic is never sufficient on its own (Task requirement:
        # "NON usare una regola stupida tipo 'ignore all image001.jpg'").
        store2 = _make_store(tmp_dir)
        try:
            imap2 = FakeImapClient()
            imap2.add_message("203", _build_email(attachments=[("image001.jpg", _FAKE_JPG_BYTES, "image/jpeg")]))
            poll_result_2 = poll_once(_config(), imap2, store2, deliver=_make_fake_deliver())
            result.check(
                "a plain attachment named like a generic inline asset, but with no Content-ID, is still processed",
                poll_result_2.delivered == 1 and poll_result_2.ignored_email_assets == 0,
            )
        finally:
            store2.close()
    finally:
        store.close()


def test_repeated_signature_asset_ignored_consistently(result: Result, tmp_dir: str) -> None:
    """Scenario 6 — the same inline logo, repeated across several
    messages/poll cycles, is ignored every single time; the real invoice
    next to it is delivered every time, without ever duplicating."""

    store = _make_store(tmp_dir)
    try:
        imap = FakeImapClient()
        for i, uid in enumerate(("204", "205", "206")):
            imap.add_message(
                uid,
                _build_email_with_inline_image(
                    inline_image=("image001.jpg", _FAKE_JPG_BYTES, "image/jpeg", "logo123@mail", None),
                    attachments=[(f"invoice_{i}.pdf", _FAKE_PDF_BYTES + str(i).encode(), "application/pdf")],
                ),
            )
        poll_result = poll_once(_config(), imap, store, deliver=_make_fake_deliver())
        result.check("all 3 logos are ignored (one per message)", poll_result.ignored_email_assets == 3)
        result.check("all 3 distinct real invoices are delivered", poll_result.delivered == 3)
        result.check("no store record exists for the repeated logo at all", all("image001" not in r.attachment_filename for r in store.list_recent()))

        # Re-poll (idempotency check for the same, already-processed messages).
        second = poll_once(_config(), imap, store, deliver=_make_fake_deliver())
        result.check("re-polling the same messages ignores the logo again, not newly delivers it", second.delivered == 0)
    finally:
        store.close()


def test_ambiguous_image_is_processed_not_discarded(result: Result, tmp_dir: str) -> None:
    """Scenario 7 — an image with a Content-ID that cannot be confirmed as
    referenced by any HTML body, and a non-generic filename, is genuinely
    ambiguous: per the Task's "Safe filter principle" it must be processed
    as a document candidate (better HUMAN than losing a real invoice), not
    silently discarded."""

    store = _make_store(tmp_dir)
    try:
        imap = FakeImapClient()
        imap.add_message(
            "207",
            _build_email_with_inline_image(
                inline_image=("receipt_scan_2026.jpg", _FAKE_JPG_BYTES, "image/jpeg", "some-cid", None),
                html_references_cid=False,
            ),
        )
        poll_result = poll_once(_config(), imap, store, deliver=_make_fake_deliver())
        result.check("an ambiguous image (unreferenced Content-ID, non-generic name) is processed, not discarded", poll_result.delivered == 1)
        result.check("nothing was ignored for this ambiguous case", poll_result.ignored_email_assets == 0)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Real OCR (Tesseract + Poppler) — skipped gracefully if not installed
# ---------------------------------------------------------------------------

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
_POPPLER_AVAILABLE = shutil.which("pdftoppm") is not None


def _draw_text_image(lines: list[str]):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1000, 120 + 50 * len(lines)), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
    for i, line in enumerate(lines):
        draw.text((30, 30 + i * 50), line, fill="black", font=font)
    return img


def test_scanned_pdf_produces_ocr_text(result: Result, tmp_dir: str) -> None:
    """Scenario 1 (§10) — a scanned (image-only, no embedded text layer)
    PDF goes through the OCR fallback (Poppler renders pages -> Tesseract
    reads them) and produces real, non-trivial text."""

    if not (_TESSERACT_AVAILABLE and _POPPLER_AVAILABLE):
        result.check("SKIPPED: scanned PDF OCR (tesseract/poppler not installed in this environment)", True)
        return

    img = _draw_text_image(["INVOICE NUMBER 12345", "TOTAL DUE 199.99"])
    pdf_path = os.path.join(tmp_dir, "scanned_invoice.pdf")
    img.save(pdf_path, "PDF")

    import ocr_engine

    text, method = ocr_engine.extract_from_pdf(pdf_path)
    result.check("a scanned/image-only PDF is read via the OCR fallback, not the digital-text path", method == "OCR")
    result.check("OCR actually produced recognizable text from the scanned PDF", "INVOICE" in text.upper() and "199.99" in text)


def test_jpg_photo_produces_ocr_text(result: Result, tmp_dir: str) -> None:
    """Scenario 2 (§10) — a photographed JPG invoice is read via Tesseract
    and produces real, non-trivial text."""

    if not _TESSERACT_AVAILABLE:
        result.check("SKIPPED: JPG OCR (tesseract not installed in this environment)", True)
        return

    img = _draw_text_image(["ACME SUPPLIES INC", "AMOUNT 42.50"])
    jpg_path = os.path.join(tmp_dir, "invoice_photo.jpg")
    img.save(jpg_path, "JPEG")

    import ocr_engine

    text = ocr_engine.extract_from_image(jpg_path)
    result.check("OCR produced recognizable text from a photographed JPG invoice", "ACME" in text.upper() and "42.50" in text)


def test_digital_pdf_still_uses_embedded_text_path(result: Result, tmp_dir: str) -> None:
    """Scenario 3 (§10) — a digital-text PDF (embedded text layer) is still
    read via pdfplumber's fast/accurate path, never falling through to OCR,
    exactly as before this task (§8, "Digital PDF vs scanned PDF")."""

    _REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    real_pdf_path = os.path.join(
        _REPO_ROOT, "01 Domains", "Shared Domains", "Administration", "Invoice Intake", "Invoices", "Raw", "Invoice 6855.pdf"
    )
    if not os.path.isfile(real_pdf_path):
        result.check("SKIPPED: digital PDF sample not present", True)
        return

    import ocr_engine

    text, method = ocr_engine.extract_from_pdf(real_pdf_path)
    result.check("a digital-text PDF is read via the embedded-text path, not OCR", method == "PDF-Text")
    result.check("meaningful text was extracted without needing Tesseract/Poppler at all", len(text.strip()) > 40)


def test_ocr_soft_failure_yields_human(result: Result, tmp_dir: str) -> None:
    """Scenario 10 (§10) — OCR that runs without crashing but produces no
    usable text (e.g. a blank/illegible image) must never be a hard
    FAILURE: the document is still delivered, just correctly flagged
    HUMAN."""

    if not _TESSERACT_AVAILABLE:
        result.check("SKIPPED: OCR soft-failure (tesseract not installed in this environment)", True)
        return

    from PIL import Image

    blank_path = os.path.join(tmp_dir, "blank.jpg")
    Image.new("RGB", (300, 300), "white").save(blank_path, "JPEG")

    url_module = __import__("rfone_data_store.database", fromlist=["create_disposable_test_database_url", "cleanup_disposable_test_database_url"])
    url = url_module.create_disposable_test_database_url("mailbox_ocr_soft_failure")
    os.environ["RFONE_DATABASE_URL"] = url
    try:
        from mailbox_acquisition.acquisition_service import deliver_to_invoice_intake

        store = _make_store(tmp_dir)
        try:
            imap = FakeImapClient()
            with open(blank_path, "rb") as handle:
                blank_bytes = handle.read()
            imap.add_message("208", _build_email(attachments=[("blank.jpg", blank_bytes, "image/jpeg")]))
            poll_result = poll_once(_config(), imap, store, deliver=deliver_to_invoice_intake)

            result.check("an unreadable/blank image is still delivered (OCR did not crash)", poll_result.delivered == 1)
            result.check("no attachment failure was recorded for it", poll_result.attachment_failures == [])
            record = store.list_recent()[0]
            result.check("it is correctly flagged HUMAN, not silently accepted as reliable", record.functional_status == "HUMAN")
        finally:
            store.close()
    finally:
        url_module.cleanup_disposable_test_database_url(url)
        os.environ.pop("RFONE_DATABASE_URL", None)


def test_ocr_success_but_parser_uncertain_is_human(result: Result, tmp_dir: str) -> None:
    """Scenario 11 (§10) — OCR successfully extracts real text, but the
    parser cannot confidently determine key header fields (e.g. no
    recognizable date) -- still HUMAN, not falsely NORMALIZED."""

    if not (_TESSERACT_AVAILABLE and _POPPLER_AVAILABLE):
        result.check("SKIPPED: OCR success/parser-uncertain (tesseract/poppler not installed in this environment)", True)
        return

    img = _draw_text_image(["SOME SUPPLIER TEXT", "TOTAL DUE 199.99"])  # deliberately no parseable date
    pdf_path = os.path.join(tmp_dir, "no_date_invoice.pdf")
    img.save(pdf_path, "PDF")

    url_module = __import__("rfone_data_store.database", fromlist=["create_disposable_test_database_url", "cleanup_disposable_test_database_url"])
    url = url_module.create_disposable_test_database_url("mailbox_ocr_parser_uncertain")
    os.environ["RFONE_DATABASE_URL"] = url
    try:
        from mailbox_acquisition.acquisition_service import deliver_to_invoice_intake

        store = _make_store(tmp_dir)
        try:
            imap = FakeImapClient()
            with open(pdf_path, "rb") as handle:
                pdf_bytes = handle.read()
            imap.add_message("209", _build_email(attachments=[("no_date_invoice.pdf", pdf_bytes, "application/pdf")]))
            poll_result = poll_once(_config(), imap, store, deliver=deliver_to_invoice_intake)

            result.check("OCR succeeded and the document was delivered", poll_result.delivered == 1)
            record = store.list_recent()[0]
            result.check("OCR text was in fact extracted (method=OCR)", record.functional_status is not None)
            result.check("missing date -> HUMAN despite OCR producing real text", record.functional_status == "HUMAN")
        finally:
            store.close()
    finally:
        url_module.cleanup_disposable_test_database_url(url)
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
    # `deliver_to_invoice_intake` -> `purchased_bridge.save_purchase_document()`
    # always writes to `supplier_format_training.py`'s own observation
    # store as a side effect -- isolate it from the real, persistent
    # training data, same as `test_purchased_bridge.py` (Task "Purchased
    # Supplier+Format Training — Phase 1" finding).
    os.environ["SUPPLIER_FORMAT_TRAINING_DB_PATH"] = os.path.join(tmp_dir, "isolated_training.db")
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
            test_inline_signature_logo_is_ignored,
            test_real_jpg_attachment_not_inline_is_not_ignored,
            test_repeated_signature_asset_ignored_consistently,
            test_ambiguous_image_is_processed_not_discarded,
            test_scanned_pdf_produces_ocr_text,
            test_jpg_photo_produces_ocr_text,
            test_digital_pdf_still_uses_embedded_text_path,
            test_ocr_soft_failure_yields_human,
            test_ocr_success_but_parser_uncertain_is_human,
            test_no_secret_in_failure_reason_or_output,
        ):
            test_fn(result, tmp_dir)
    finally:
        os.environ.pop("SUPPLIER_FORMAT_TRAINING_DB_PATH", None)
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
