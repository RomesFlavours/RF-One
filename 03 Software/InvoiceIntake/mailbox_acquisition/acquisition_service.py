"""Mailbox → Invoice Intake pipeline orchestration (one poll cycle).

```text
mailbox (ImapClient)
  -> list new/retryable message UIDs
    -> fetch + parse each message (email_parsing.py)
      -> filter attachments to documental file types (attachment_filter.py)
        -> filter out inline email assets (logos/signatures -- attachment_filter.py)
          -> technical dedup (identity + content hash, AcquisitionStore)
            -> save bytes under uploads/ (same folder app.py's manual upload uses)
              -> deliver_to_invoice_intake(): ocr_engine -> parser -> purchased_bridge
                -> Purchased canonical persistence (unchanged pipeline)
```

This module never writes `PurchaseDocument`/`PurchaseLine` directly and
never talks to `rfone_data_store` except through `purchased_bridge.py` —
the exact same pipeline `app.py`'s `/upload` + `/save` routes already use,
so there is exactly one Invoice Intake -> Purchased path, not two.

Functional (cross-channel) duplicate/correction handling — "the same
document received from another channel" vs. "a genuine correction" — is
`purchased_bridge.save_purchase_document`'s own responsibility (Purchased/
README.md, "Duplicate handling" / "Supplier-side corrections"); this module
only ever decides the narrower, purely technical question "have I already
acquired this exact attachment before."
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field

import ocr_engine
import parser as invoice_parser
import purchased_bridge

from .acquisition_store import TERMINAL_SUCCESS_STATUSES, AcquisitionStore
from .attachment_filter import is_documental_attachment, is_email_asset
from .config import MailboxConfig
from .email_parsing import parse_email
from .imap_client import ImapClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INVOICE_INTAKE_DIR = os.path.dirname(BASE_DIR)
UPLOAD_DIR = os.path.join(INVOICE_INTAKE_DIR, "uploads")
DATA_DIR = os.path.join(INVOICE_INTAKE_DIR, "data")
DEFAULT_DB_PATH = os.path.join(DATA_DIR, "mailbox_acquisition.db")


@dataclass
class PollResult:
    delivered: int = 0
    duplicates: int = 0
    skipped_already_processed: int = 0
    ignored_email_assets: int = 0
    attachment_failures: list[tuple[str, str, str]] = field(default_factory=list)  # (uid, filename, reason)
    message_failures: list[tuple[str, str]] = field(default_factory=list)  # (uid, reason)


def redact(text: str, config: MailboxConfig) -> str:
    """Never let the mailbox password leak into a stored failure reason or
    a printed log line (Task requirement 12, "Security")."""

    if config.password and config.password in text:
        return text.replace(config.password, "***")
    return text


def deliver_to_invoice_intake(saved_path: str) -> int:
    """Runs the existing Invoice Intake pipeline against one saved
    attachment — identical to what `app.py`'s `/upload` + `/save` routes do
    for a manually-uploaded file — and returns the resulting
    `PurchaseDocumentId`. No second pipeline: this calls the exact same
    `ocr_engine` / `parser` / `purchased_bridge` modules."""

    ext = os.path.splitext(saved_path)[1].lower()
    if ext == ".pdf":
        text, method = ocr_engine.extract_from_pdf(saved_path)
    else:
        text = ocr_engine.extract_from_image(saved_path)
        method = "OCR"

    header = invoice_parser.parse_header(text)
    header["acquisition_method"] = method
    lines = invoice_parser.parse_lines(text)
    for line in lines:
        line["line_type"] = purchased_bridge.guess_line_type(line.get("description", ""))

    source_file = os.path.basename(saved_path)
    return purchased_bridge.save_purchase_document(header, lines, source_file)


def _save_attachment(content: bytes, original_filename: str) -> str:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex[:8]}_{original_filename}"
    saved_path = os.path.join(UPLOAD_DIR, unique_name)
    with open(saved_path, "wb") as handle:
        handle.write(content)
    return saved_path


def poll_once(
    config: MailboxConfig,
    imap_client: ImapClient,
    store: AcquisitionStore,
    deliver=deliver_to_invoice_intake,
) -> PollResult:
    """Runs exactly one acquisition cycle. Safe to call repeatedly/after a
    restart: every already-resolved attachment (delivered or a recognized
    technical duplicate) is skipped via `AcquisitionStore`'s identity check
    before anything is re-downloaded or re-delivered (Task requirement 4,
    "Idempotency"; requirement 5, "Riavviare il processo NON deve
    duplicare documenti")."""

    result = PollResult()
    mailbox = config.mailbox

    since_uid = store.get_cursor(mailbox)
    try:
        new_uids = imap_client.list_message_uids(mailbox, since_uid=since_uid)
    except Exception as exc:  # noqa: BLE001 — a whole-mailbox listing failure; let the caller's cycle-level retry handle it
        raise RuntimeError(redact(str(exc), config)) from None

    retry_uids = store.get_retry_message_uids(mailbox)
    # Union, oldest first: new messages plus anything still carrying an
    # unresolved FAILED attachment, regardless of the cursor position.
    all_uids = sorted({*new_uids, *retry_uids}, key=int)

    max_uid_seen = since_uid
    for uid in all_uids:
        try:
            raw_message = imap_client.fetch_message(mailbox, uid)
        except Exception as exc:  # noqa: BLE001 — one message's fetch failure must never block the others
            result.message_failures.append((uid, redact(str(exc), config)))
            continue

        parsed = parse_email(raw_message.raw_bytes)
        # Index is assigned over every documental-*type* attachment (PDF/
        # JPG/PNG/...) BEFORE the inline-asset check below, so a real
        # document's (mailbox, uid, index) identity never shifts depending
        # on how many inline logos happen to sit ahead of it in the message
        # -- see attachment_filter.py for the EMAIL_ASSET/DOCUMENT_CANDIDATE
        # evidence-based classification itself.
        documental_attachments = [a for a in parsed.attachments if is_documental_attachment(a.filename)]

        for index, attachment in enumerate(documental_attachments):
            if is_email_asset(attachment):
                # An inline signature/logo/banner, not a supplier document
                # (Task requirement 4/5, "Email attachment noise filter" /
                # "Safe filter principle") -- never becomes an acquisition
                # candidate, never reaches OCR/Purchased. Classification is
                # deterministic MIME evidence, not history, so nothing needs
                # to be persisted to keep re-polls consistent.
                result.ignored_email_assets += 1
                continue

            content_hash = hashlib.sha256(attachment.content).hexdigest()
            existing = store.find_by_identity(mailbox, uid, index)

            if existing is not None and existing.status in TERMINAL_SUCCESS_STATUSES:
                result.skipped_already_processed += 1
                continue

            record_id = existing.id if existing is not None else store.record_pending(
                mailbox=mailbox,
                message_uid=uid,
                attachment_index=index,
                attachment_filename=attachment.filename,
                content_hash=content_hash,
                sender=parsed.sender,
                subject=parsed.subject,
                received_at=parsed.received_at,
            )

            duplicate_source = store.find_delivered_by_content_hash(content_hash)
            if duplicate_source is not None:
                # The exact same bytes were already delivered under a
                # different message/attachment slot (Task requirement 7A,
                # "stesso attachment ricevuto nuovamente") -- a technical
                # duplicate, never re-delivered, never a second Purchase Fact.
                store.mark_duplicate_technical(record_id, purchase_document_id=duplicate_source.purchase_document_id)
                result.duplicates += 1
                continue

            try:
                saved_path = _save_attachment(attachment.content, attachment.filename)
                purchase_document_id = deliver(saved_path)
                functional_status = None
                try:
                    functional_status = purchased_bridge.get_saved_document_functional_status(purchase_document_id)
                except Exception:  # noqa: BLE001 — best-effort cache for the admin view only, never fatal
                    functional_status = None
                store.mark_delivered(
                    record_id,
                    purchase_document_id=purchase_document_id,
                    stored_path=saved_path,
                    functional_status=functional_status,
                )
                result.delivered += 1
            except Exception as exc:  # noqa: BLE001 — one attachment's failure must never block the others
                store.mark_failed(record_id, reason=redact(str(exc), config))
                result.attachment_failures.append((uid, attachment.filename, redact(str(exc), config)))
                continue

        if max_uid_seen is None or int(uid) > max_uid_seen:
            max_uid_seen = int(uid)

    if max_uid_seen is not None:
        # The cursor only accelerates future listing (skip messages already
        # fully scanned); it is never the sole reason a retryable failure
        # gets revisited -- get_retry_message_uids() above is independent of
        # it (Task requirement 9, "non avanzare... se ciò causerebbe perdita").
        store.set_cursor(mailbox, max_uid_seen)

    return result
