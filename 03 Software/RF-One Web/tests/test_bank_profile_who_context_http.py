#!/usr/bin/env python
"""HTTP test for the AI proposal of a Recognition Profile (Bank unification, Phase 2).

The existing profile conversation (`bank_flow_routes.py`) tells the AI, for a
known WHO, its Labels and its WHO -> WHY associations (approved / historical)
as context; the profile page opens that conversation from a link
(`/bank/ai-rules?who_id=…&propose=1`). Nothing is saved or activated here:
activation stays the person's Save after the Preview.

Runs against a DISPOSABLE SQLite database created here and deleted at the end.
The AI provider is replaced by a stub that records the prompt.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from unittest import mock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_profile_who_context_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "profile-who-context-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import bank_assistant_preview_routes  # noqa: E402
import bank_chatgpt  # noqa: E402
import bank_flow_routes  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import manual_reconciliation, who_identification, why_catalog  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
BANK_CSRF_RE = re.compile(r'<meta name="bank-csrf" content="([^"]+)"')


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}"
              + ("" if condition or not detail else f"   [{str(detail)[:300]}]"))

    with SessionFactory() as db:
        account_service.create_account(db, username="profile_operator", display_name="profile_operator",
                                       password="OperatorPass123!", status="ACTIVE", is_admin=False)
        db.commit()
        operator = db.query(m.RFOneAccount).filter_by(username="profile_operator").one()
        account_service.set_domain_access(db, account_id=operator.id, domain_code="BANK", enabled=True,
                                          role_code=None, scope=m.DOMAIN_ACCESS_SCOPE_ALL)
        who_id = manual_reconciliation.create_who(db, name="LINEN TEST CO").occurrence.id
        who_identification.set_labels(db, who_id, labels=[], new_label=("Linen Service", "Rents and launders table linen."))
        whys = [r for r in db.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE"))
                if r.accounting_classification_id][:2]
        why_catalog.associate(db, occurrence_id=who_id, transaction_reason_id=whys[0].id, source="HUMAN")
        why_catalog.associate(db, occurrence_id=who_id, transaction_reason_id=whys[1].id, source="HISTORY", confirm=False)
        db.commit()

        ctx = bank_flow_routes.who_context(db, who_id)
    check("1. the WHO context carries its Labels with their definitions",
          # "Linen Service" is a seed Label: the catalog reuses it (and its definition), never a duplicate.
          [x["name"] for x in ctx["labels"]] == ["Linen Service"] and all(x["definition"] for x in ctx["labels"]), ctx)
    check("2. approved and historical WHYs are kept apart",
          [w["why_id"] for w in ctx["approved_whys"]] == [whys[0].id]
          and [w["why_id"] for w in ctx["historical_whys"]] == [whys[1].id], ctx)

    client = web_app.app.test_client()
    client.post("/login", data={"username": "profile_operator", "password": "OperatorPass123!",
                                "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})
    page = client.get("/bank/ai-rules").data.decode("utf-8")
    csrf = (BANK_CSRF_RE.search(page) or [None, None])[1]
    script = client.get("/static/bank-assistant/flow.js").data.decode("utf-8")
    check("3. the profile page opens the conversation of a WHO from a link (who_id, propose=1)",
          "flow.js?v=whom-resolution2" in page and "params.get('who_id')" in script
          and "params.get('propose')==='1'" in script)

    resp = client.post("/bank/flow/conversation", data={"csrf_token": csrf, "kind": "PHOTO", "who_id": who_id})
    chat = resp.get_json() or {}
    check("4. a profile conversation opens for the WHO", resp.status_code == 200 and chat.get("ok"), resp.data[:300])

    prompts = []

    def stub(prompt, **_):
        prompts.append(prompt)
        return {"reply": "Which branch applies to the RFMD invoices?", "ready": False, "title": "LINEN TEST CO"}

    with mock.patch.object(bank_assistant_preview_routes, "_provider_context_approved", return_value=True), \
            mock.patch.object(bank_chatgpt, "generate_json", side_effect=stub):
        resp = client.post(f"/bank/flow/conversation/{chat.get('id')}",
                           data={"csrf_token": csrf, "message": "Propose the Recognition Profile of this WHO."})
    body = resp.get_json() or {}
    payload = json.loads(prompts[0].split("\n")[-1]) if prompts else {}
    check("5. the AI receives the WHO's Labels and approved/historical WHYs as context",
          resp.status_code == 200 and payload.get("who_context") == ctx, (resp.status_code, list(payload)))
    check("6. the AI is told Labels are context and approved WHYs are respected",
          bool(prompts) and "Labels are context, never a classification" in prompts[0])
    check("7. a proposal is not a profile: nothing is saved or activated (no rule written)",
          body.get("ready") is False and body.get("rule_id") is None)
    with SessionFactory() as db:
        check("8. no Bank rule exists after the AI proposal", db.scalars(select(m.BankAiRule)).first() is None)

    print()
    print(f"{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            from db import _engine
            _engine.dispose()
            os.remove(_TEST_DB_PATH)
        except Exception:  # noqa: BLE001 — best-effort cleanup of the throwaway file
            pass
