"""Aruba mailbox acquisition for Purchased / Invoice Intake.

Feeds `invoices@romesflavours.com` (Rome's Flavours' operational mailbox)
into the existing Invoice Intake pipeline (`ocr_engine.py` / `parser.py` /
`purchased_bridge.py`) as a real acquisition source, alongside the existing
manual upload path (`app.py`'s `/upload`). This package owns acquisition
only — identifying new messages, downloading documental attachments,
recording source/provenance, and technical deduplication/retry. It never
writes `PurchaseDocument`/`PurchaseLine` directly and never duplicates the
OCR/parser/`purchased_bridge` pipeline; see `acquisition_service.py`.
"""
