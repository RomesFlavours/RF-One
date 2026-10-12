"""Test helper: upload Bank files the way the page now does it.

Since BANK_TWO_PASS_IMPORT_001 `/bank/upload` stages the set and opens its
import session: Pass 1 sets the Sources (Complete Source on each row), Pass
2 reads and checks the rows, and only Confirm imports. Tests that are about what an
import produces (not about the session) use `upload_and_confirm` to take
every step the way a person would, with a default decision for each flagged
row — a possible duplicate is imported as a distinct operation, an
unreadable row is excluded — and get back the Confirm response (or the
response that stopped the flow, e.g. a file whose Source is ambiguous).
"""

from __future__ import annotations

import json
import os
import re

_TOKEN_RE = re.compile(r"(?:staged=|/bank/import/)([0-9a-f]{32})")
_CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def staged_token(response) -> str | None:
    match = _TOKEN_RE.search(response.headers.get("Location", ""))
    return match.group(1) if match else None


def session_state(client, token: str) -> dict:
    """The session state as the page holds it (read from the manifest the
    app wrote, through the staging folder the app is configured with)."""
    import flask  # noqa: F401  (the app is already imported by every caller)
    from app import app
    root = app.config.get("BANK_IMPORT_STAGING_DIR")
    import bank_import_staging
    path = os.path.join(bank_import_staging.staging_root(root), token, "manifest.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle).get("two_pass") or {}


HELPER_OWNER = "Test Import Owner, LLC"


def complete_sources(state: dict) -> None:
    """What a person does with Complete Source before Pass 2
    (BANK_COMPLETE_SOURCE_001): fill ONLY the required data a Source of an
    included file still lacks — an owner (a test LLC) or, for a card, a
    settlement account owned by it. Anything already set is left alone."""
    from datetime import date

    from db import SessionFactory
    from rfone_data_store import models as m
    from rfone_data_store.bank_reconciliation import card_configuration
    from rfone_data_store.bank_reconciliation import configuration as config_service
    from rfone_data_store.bank_reconciliation import import_session
    from rfone_data_store.bank_reconciliation import service as bank_service

    with SessionFactory() as db:
        def owner():
            existing = db.query(m.ReportingEntity).filter_by(name=HELPER_OWNER).one_or_none()
            return existing or config_service.create_entity(db, name=HELPER_OWNER, legal_name=HELPER_OWNER)

        def settlement_account():
            account = db.query(m.PaymentInstrument).filter_by(display_name="Test Import Settlement").one_or_none()
            return account or bank_service.create_payment_instrument(
                db, institution="TEST", display_name="Test Import Settlement", instrument_type="BANK_ACCOUNT",
                last_four="0000", legal_entity_id=owner().legal_entity_id)

        for source_id in {f["source_id"] for f in state.get("files", []) if f["status"] == "READY" and f["source_id"]}:
            source = db.get(m.PaymentInstrument, source_id)
            missing = import_session.source_missing_fields(db, source)
            if "Institution / Provider" in missing:
                source.institution = "TEST"
            if "Last 4 digits or account identifier" in missing:
                source.external_account_identifier = f"TEST-{source.id}"
            if "Owning entity" in missing:
                source.legal_entity_id = owner().legal_entity_id
            if "Settlement / Funding account" in missing:
                card_configuration.assign_settlement_account(
                    db, credit_card_payment_instrument_id=source.id,
                    settlement_bank_account_id=settlement_account().id, valid_from=date(2000, 1, 1))
        db.commit()


def create_missing_sources(client, token: str, csrf: str) -> None:
    """Open the session (a file whose name matches one Source gets it) and,
    for each bank file with no Source and no candidate, do what Complete
    Source does (BANK_COMPLETE_SOURCE_ALL_ROWS_001): save the modal's New
    Source, prefilled with what the file states, for that file."""
    from rfone_data_store.bank_reconciliation import import_session

    client.get(f"/bank/import/{token}")
    for index in range(len(session_state(client, token)["files"])):
        # Re-read after each Save: the page matches the next files (a "(1)"
        # copy) to the Source just created.
        client.get(f"/bank/import/{token}")
        f = session_state(client, token)["files"][index]
        if f["kind"] != "BANK" or f["status"] != "PENDING" or not f["digits"]:
            continue
        data = import_session.source_prefill(f["kind"], f["institution"], f["instrument_type"], f["digits"])
        data.update(csrf_token=csrf, import_token=token, import_file_index=str(f["index"]))
        client.post("/bank/instruments/new", data=data, headers={"X-Requested-With": "fetch"})


def confirm_leave_outs(client, token: str, csrf: str) -> None:
    """What the person confirms in the review log (BANK_FILE_LEAVE_OUT_001):
    every file this import cannot read stays out of this upload."""
    for f in session_state(client, token)["files"]:
        if f["status"] in ("IMPORTER_MISSING", "UNRECOGNIZED"):
            client.post(f"/bank/import/{token}/leave-out",
                        data={"csrf_token": csrf, "file_index": str(f["index"]), "decision": "LEAVE_OUT"})


def upload_and_confirm(client, data: dict, *, duplicates: str = "IMPORT_DISTINCT"):
    """POST the files to `/bank/upload`, take both passes, decide every
    flagged row, then Confirm."""
    response = client.post("/bank/upload", data=data, content_type="multipart/form-data")
    token = staged_token(response)
    if token is None:
        return response
    csrf = data["csrf_token"]
    create_missing_sources(client, token, csrf)
    confirm_leave_outs(client, token, csrf)
    complete_sources(session_state(client, token))
    client.post(f"/bank/import/{token}/check", data={"csrf_token": csrf})
    state = session_state(client, token)
    for issue in (state.get("check") or {}).get("issues", []):
        decision = "EXCLUDE" if issue.get("exclusion_only") else duplicates
        client.post(f"/bank/import/{token}/decide",
                    data={"csrf_token": csrf, "key": issue["key"], "decision": decision})
    return client.post(f"/bank/upload/{token}/confirm", data={"csrf_token": csrf})
