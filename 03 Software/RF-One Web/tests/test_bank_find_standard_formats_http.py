#!/usr/bin/env python
"""Rules and profiles: the "Find standard formats" generator is back (Product Owner, 2026-10-25),
Discover WHY Patterns is kept but switched off.

Runs on a COPY of the local Bank database (never the database itself):
1. the page shows "Find standard formats" with its original wording, and neither the WHY patterns
   section nor its script;
2. every Discover WHY Patterns address answers 404 (not operative), its code and data are untouched;
3. the generator scans every transaction, groups the recurring description structures not yet
   read by a WHO rule, asks ChatGPT for WHO extraction formats and shows the proposals, each with
   "Discuss and preview on real transactions";
4. nothing is classified, no rule is created or deleted, no human decision changes.

By default the AI is a deterministic stand-in that proposes one valid WHO extraction rule; with
RFONE_TEST_REAL_AI=1 the real ChatGPT (Codex on this PC) is asked, exactly as the button does.

    python tests/test_bank_find_standard_formats_http.py
"""
from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
REPO_ROOT = Path(APP_DIR).parents[1]
for path in (APP_DIR, os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))):
    if path not in sys.path:
        sys.path.insert(0, path)

_SOURCE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RF-One" / "Bank" / "rfone.db"
if not _SOURCE.exists():
    print("SKIPPED: no local Bank database to copy.")
    sys.exit(0)
_FOLDER = tempfile.mkdtemp(prefix="rfone_standard_formats_")
atexit.register(shutil.rmtree, _FOLDER, ignore_errors=True)
_COPY = Path(_FOLDER) / "rfone.db"
_src = sqlite3.connect(f"file:{_SOURCE.as_posix()}?mode=ro", uri=True)
_dst = sqlite3.connect(_COPY)
_src.backup(_dst)
_dst.close()
_src.close()
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_COPY.as_posix()}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "standard-formats-test-secret"
os.environ["CBANK_BANK_DB"] = str(_COPY)
os.environ["CBANK_BANK_CODE_ROOT"] = str(REPO_ROOT)
os.environ["CBANK_STORE_DIR"] = str(Path(_FOLDER) / "store")
os.environ["RFONE_BANK_SINGLE_ENGINE"] = "1"
os.environ.pop("RFONE_BANK_WHY_PATTERNS", None)  # as the local Bank runs now: switched off

import app as web_app  # noqa: E402
import bank_assistant_preview_routes  # noqa: E402
import bank_chatgpt  # noqa: E402
import bank_flow_routes  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
BANK_CSRF_RE = re.compile(r'<meta name="bank-csrf" content="([^"]+)"')
REAL_AI = os.environ.get("RFONE_TEST_REAL_AI") == "1"


def state(db):
    """What the generator must never change: classifications, decisions, rules."""
    return dict(
        explanations=sorted(tuple(r) for r in db.execute(select(
            m.BankTransactionExplanation.id, m.BankTransactionExplanation.transaction_reason_id,
            m.BankTransactionExplanation.accounting_classification_id,
            m.BankTransactionExplanation.decision_source)).all()),
        linked=sorted(tuple(r) for r in db.execute(select(m.FinancialTransaction.id,
                                                          m.FinancialTransaction.explanation_id)).all()),
        rules=db.scalar(select(func.count()).select_from(m.BankAiRule)),
        live_rules=db.scalar(select(func.count()).select_from(m.BankAiRule).where(m.BankAiRule.deleted_at.is_(None))),
        versions=db.scalar(select(func.count()).select_from(m.BankAiRuleVersion)),
    )


seen_prompts: list[str] = []


def stand_in(prompt, **_):
    """Proposes one literal-delimiter WHO extraction for the first group, as ChatGPT would."""
    seen_prompts.append(prompt)
    groups = re.findall(r'"([A-Z][A-Z0-9 &\'./-]{6,}?) ', prompt)
    start = groups[0].split()[0] + " " if groups else "PAYMENT TO "
    return {"formats": [{"title": "Stand-in format", "reply": "Takes the name after the opening words.",
                         "spec": {"engine": "BANK_FLOW_2", "kind": "EXTRACTOR", "start": start, "end_mode": "end",
                                  "suffix_policy": "dates"}}]}


def main() -> int:
    passed, failed = [], []

    def check(description, condition, detail=""):
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}"
              + ("" if condition or not detail else f"   [{str(detail)[:400]}]"))

    with SessionFactory() as db:
        account_service.create_account(db, username="formats_operator", display_name="formats_operator",
                                       password="OperatorPass123!", status="ACTIVE", is_admin=False)
        db.commit()
        operator = db.query(m.RFOneAccount).filter_by(username="formats_operator").one()
        account_service.set_domain_access(db, account_id=operator.id, domain_code="BANK", enabled=True,
                                          role_code=None, scope=m.DOMAIN_ACCESS_SCOPE_ALL)
        db.commit()
        before = state(db)
        why_artifacts = db.scalar(select(func.count()).select_from(m.BankFlowArtifact)
                                  .where(m.BankFlowArtifact.kind == "WHY_DISCOVERY"))

    client = web_app.app.test_client()
    client.post("/login", data={"username": "formats_operator", "password": "OperatorPass123!",
                                "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})
    page = client.get("/bank/ai-rules").data.decode("utf-8")
    csrf = (BANK_CSRF_RE.search(page) or [None, None])[1]

    # 1. The page
    check("1. Rules and profiles shows the original 'Find standard formats' button and wording",
          '<button id="discover">Find standard formats</button>' in page
          and "Extract WHO only. Review and approve each suggested format." in page
          and 'id="discovery-results"' in page)
    check("1. the Discover WHY Patterns section and its script are not on the page",
          "Discover WHY Patterns" not in page and 'id="why-heading"' not in page and "why_patterns.js" not in page)
    check("1. AI rules, Recognition profiles and the review list are still there",
          'id="new-extractor"' in page and 'id="photos-heading"' in page and 'id="pending-list"' in page)
    data = client.get("/bank/flow/data").get_json() if "/bank/flow/data" in str(web_app.app.url_map) else None
    if data is not None:
        check("1. the rules list still loads, with no WHY pattern rules", data.get("ok") and data.get("why_rules") == [])

    # 2. Discover WHY Patterns: not operative
    codes = [client.post("/bank/flow/why-discover", data={"csrf_token": csrf}).status_code,
             client.get("/bank/flow/why-discover/latest").status_code,
             client.get("/bank/flow/why-rules").status_code]
    check("2. every Discover WHY Patterns address answers 404", codes == [404, 404, 404], codes)

    # 3. The generator, as the button runs it
    real_context = bank_assistant_preview_routes._provider_context_approved
    bank_assistant_preview_routes._provider_context_approved = lambda: True  # the PO's approval, as on the PC
    try:
        response = client.post("/bank/flow/discover", data={"csrf_token": csrf})
    finally:
        bank_assistant_preview_routes._provider_context_approved = real_context
    body = response.get_json() or {}
    check("3. 'Find standard formats' starts a search", response.status_code == 200 and body.get("ok") and body.get("id"),
          response.get_data(as_text=True)[:300])
    scan_id = body.get("id")
    generate = bank_chatgpt.generate_json if REAL_AI else stand_in
    bank_flow_routes.discovery(SessionFactory, scan_id, generate=generate)  # the background thread's work
    result = client.get(f"/bank/flow/discover/{scan_id}").get_json() or {}
    with SessionFactory() as db:
        total = db.scalar(select(func.count()).select_from(m.FinancialTransaction))
    print(f"     search: {result.get('status')}, {result.get('examined')} transactions, "
          f"{result.get('groups')} recurring groups not read by a WHO rule, {len(result.get('formats') or [])} formats"
          + (f", errors: {result.get('errors')}" if result.get("errors") else ""))
    check("3. the search examines every transaction and finds recurring description groups not yet read",
          result.get("examined") == total and (result.get("groups") or 0) > 0, result)
    check("3. the search completes", result.get("status") == "COMPLETE", result.get("errors") or result.get("error"))
    formats = result.get("formats") or []
    check("3. it proposes WHO extraction rules (title, explanation, executable spec), none applied",
          bool(formats) and all(f.get("title") and f.get("spec", {}).get("kind") == "EXTRACTOR" for f in formats),
          formats[:2])
    for f in formats[:15]:
        print(f"       - {f.get('title')}: {f.get('reply', '')[:150]}")
    if not REAL_AI:
        check("3. ChatGPT is asked about the groups (description structures, not merchants)",
              seen_prompts and "Find standard bank description formats: STRUCTURES" in seen_prompts[0])  # PO 2026-10-25: structures with variable parts
    script = client.get("/static/bank-assistant/flow.js").data.decode("utf-8")
    check("3. each proposal opens 'Discuss and preview on real transactions' (unchanged page code)",
          "Discuss and preview on real transactions" in script and "api('/bank/flow/discover'" in script)

    # 4. Nothing else changed
    with SessionFactory() as db:
        after = state(db)
        why_after = db.scalar(select(func.count()).select_from(m.BankFlowArtifact)
                              .where(m.BankFlowArtifact.kind == "WHY_DISCOVERY"))
    check("4. no classification, decision or rule was created, changed or deleted", before == after,
          {k: (before[k], after[k]) for k in before if before[k] != after[k] and not isinstance(before[k], list)})
    check("4. the Discover WHY Patterns data are kept", why_after == why_artifacts, (why_artifacts, why_after))

    print(f"\n{len(passed)} passed, {len(failed)} failed" + (" (real ChatGPT)" if REAL_AI else " (AI stand-in)"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
