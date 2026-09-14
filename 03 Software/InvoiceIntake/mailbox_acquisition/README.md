# Aruba Mailbox Acquisition

Connects `invoices@romesflavours.com` — Rome's Flavours' operational mailbox — as a real source for Purchased / Invoice Intake:

```text
Aruba mailbox (IMAP)
  -> identify new messages (and any previously-failed, retryable ones)
    -> download every documental attachment (PDF, JPG/JPEG, PNG, TIFF, WEBP, BMP)
      -> record source/provenance + technical dedup
        -> deliver to the EXISTING Invoice Intake pipeline
           (ocr_engine.py -> parser.py -> purchased_bridge.py)
             -> Purchased canonical persistence (unchanged)
```

This package owns acquisition only — it never writes `PurchaseDocument`/`PurchaseLine` directly, and it is not a second pipeline: every attachment goes through the exact same `ocr_engine`/`parser`/`purchased_bridge` modules `app.py`'s manual upload already uses.

## Configuration

Set via environment variables or a local `.env` file at the repository root (see `.env.example`; never commit real values):

| Variable | Required | Default | Notes |
|---|---|---|---|
| `ARUBA_IMAP_USERNAME` | yes | — | The mailbox address, e.g. `invoices@romesflavours.com` |
| `ARUBA_IMAP_PASSWORD` | yes | — | Never logged, printed, or stored anywhere |
| `ARUBA_IMAP_HOST` | no | `imaps.aruba.it` | Aruba's standard IMAPS host (public info, not a secret) |
| `ARUBA_IMAP_PORT` | no | `993` | |
| `ARUBA_IMAP_MAILBOX` | no | `INBOX` | IMAP folder to poll |
| `ARUBA_IMAP_POLL_INTERVAL_SECONDS` | no | `45` | Continuous-loop interval (30–60s is the expected range for this mailbox's low volume) |
| `ARUBA_IMAP_USE_SSL` | no | `true` | |

## Running

```
cd "03 Software/InvoiceIntake"
python run_mailbox_acquisition.py          # continuous loop
python run_mailbox_acquisition.py --once   # one poll cycle, then exit (cron/manual)
```

Acquired attachments are saved under the same `uploads/` directory the manual-upload path already uses. Acquisition-layer state (mailbox cursor, provenance, technical dedup/retry) lives in its own local SQLite file, `data/mailbox_acquisition.db` (Git-ignored, never the canonical `rfone_data_store` database) — see `acquisition_store.py`.

A simple admin view is available at `/mailbox` in the InvoiceIntake Flask app (`app.py`), showing what was acquired, its status, recognized Supplier (once delivered), NORMALIZED/HUMAN state, and any failure/retry.

## Behavior

- **Read-only on the mailbox.** Every IMAP `SELECT` is `readonly=True` — this process never marks a message as read, moves it, or deletes it. The mailbox remains normally usable by a human.
- **Idempotent.** A `(mailbox, message UID, attachment index)` identity, plus a SHA-256 content hash, means restarting the process never re-delivers an already-acquired attachment. A technical duplicate (the exact same bytes, arriving via a different message) is recognized and never becomes a second Purchase Fact — it references the original's `PurchaseDocumentId`.
- **One email is never assumed to be one invoice.** Every documental attachment in a message becomes its own acquisition candidate — an invoice, several invoices, or an invoice plus supporting documents are all handled the same way.
- **Failures are isolated and retryable.** One attachment's (or one message's) failure never blocks any other message/attachment in the same or a later poll cycle. A failed attachment is retried on every subsequent poll until it succeeds (or is otherwise resolved) — nothing is silently skipped or lost.
- **Functional deduplication stays Purchased's own.** This package only ever recognizes a *technical* duplicate (identical bytes). "The same document received through another channel, with different bytes" (e.g. re-scanned) is left entirely to `purchased_bridge.save_purchase_document`'s own duplicate/correction handling — this package never decides "corrected invoice vs. duplicate" itself.
- **Provenance, not a Purchased Line.** Source/mailbox metadata (message UID, sender, subject, received timestamp, attachment filename, content hash, ingestion timestamp) is recorded in this package's own local store for traceability — it is never mapped onto a `PurchaseLine`.

## Not in scope for this task

OCR/parser quality is unchanged (`ocr_engine.py`/`parser.py` are untouched) — this package is acquisition only.
