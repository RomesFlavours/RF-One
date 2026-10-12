"""Bank > AI Rules — Save Draft / Salva / Salva e Applica (BANK_AI_RULES_009).

On a throwaway database, over HTTP. The AI provider is replaced INSIDE THIS
TEST ONLY by a stand-in that interprets the rules; the application itself
never simulates an answer.

* Save Draft keeps the rule in the drafts;
* Salva makes the current version operative, removes it from the drafts and
  applies nothing; a draft of an operative rule is saved into THAT rule (a new
  version), never a duplicate;
* a rule without a valid interpretation is never operative: refused with what
  is missing (none yet in SESSION mode; not executable), nothing saved, and an
  operative rule keeps its version;
* text, version and interpretation belong together: a new interpretation of
  the same text is a new version; a preview of another text — or of another
  interpretation — cannot authorize the application;
* Salva e Applica applies to the chosen scope and, only after success, removes
  the draft; an application with a movement in error is NOT complete, keeps the
  draft and says so;
* "Per il futuro" is what the import follows.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rule_save_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rule-save-secret"
os.environ.pop("RFONE_BANK_AI_MODE", None)

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from sqlalchemy import func, select  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import ai_rule_operations  # noqa: E402
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
RULE_A = "Se la descrizione contiene “SHOP TEST”, assegna WHO \"SHOP TEST\"."
RULE_B = "Se la descrizione contiene “SHOP TEST”, assegna WHO \"SHOP TEST\". Versione due."
RULE_BLOCKED = "Se la descrizione contiene “SHOP TEST” e il giorno è festivo, assegna WHO \"SHOP TEST\"."


def interpretation(rule: str) -> dict:
    if rule in (RULE_A, RULE_B):
        return {"kind": "STRUCTURED", "conditions": [{"field": "description", "op": "contains", "value": "SHOP TEST"}],
                "who": {"mode": "fixed", "name": "SHOP TEST"}, "why": None, "branches": [], "status": None,
                "only_if_who_differs": False, "replace_existing": False, "unsupported": [],
                "coverage": [{"instruction": "descrizione contiene “SHOP TEST”", "represented_by": "conditions"},
                             {"instruction": "assegna WHO SHOP TEST", "represented_by": "who.fixed"}]}
    return {"kind": "OTHER", "reason": "the holiday condition cannot be expressed",
            "unsupported": ["il giorno è festivo"],
            "coverage": [{"instruction": "il giorno è festivo", "represented_by": "nothing"}]}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_save", display_name="AI Save", password="AiSave123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_save").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF Save, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        checking = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT", display_name="Save Checking",
                                       institution="CHASE", last_four="3001", currency="USD")
        s.add(checking)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        s.add(m.BankOccurrence(canonical_name="SHOP TEST", occurrence_type_id=counterparty.id, status="ACTIVE"))
        ids = []
        for i, text in enumerate(("SHOP TEST ONE", "SHOP TEST TWO", "OTHER STORE")):
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, 2 + i),
                transaction_date=date(2026, 9, 2 + i), description_original=text, description_normalized=text,
                amount_minor=-1000 - i, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"save-{i}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            ids.append(t.id)
        s.commit()

    calls = {"n": 0}

    def stand_in(prompt: str) -> dict:
        calls["n"] += 1
        calls.setdefault("asked", []).append((prompt.split("RULE:\n")[1].split("\n\nEXAMPLE")[0],
                                              "Nuove istruzioni." in prompt))
        return interpretation(prompt.split("RULE:\n")[1].split("\n\nEXAMPLE")[0])

    ai_client.generate_json = stand_in
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_save", "password": "AiSave123!", "csrf_token": csrf})
    csrf = CSRF_RE.search(client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()).group(1)

    def post(path, **data):
        form = {"csrf_token": csrf, "origin_transaction_id": str(ids[0]), "date_from": "2026-09-01",
                "date_to": "2026-09-30", "rule_text": RULE_A}
        form.update({k: str(v) for k, v in data.items() if v is not None})
        response = client.post(path, data=form, headers={"X-Requested-With": "fetch"})
        return response.status_code, response.get_json()

    def counts():
        with SessionFactory() as s:
            return dict(rules=s.scalar(select(func.count(m.BankAiRule.id))),
                        versions=s.scalar(select(func.count(m.BankAiRuleVersion.id))),
                        drafts=s.scalar(select(func.count(m.BankAiRuleDraft.id))),
                        decisions=s.scalar(select(func.count(m.BankTransactionExplanation.id))))

    # ---------------------------------------------------------------- Save Draft
    status, draft = post("/bank/ai-rules/drafts")
    check("1. Save Draft keeps the rule in the drafts", draft["ok"] and counts()["drafts"] == 1 and counts()["rules"] == 0)

    # ---------------------------------------------------------------- Salva
    status, saved = post("/bank/ai-rules/save", draft_id=draft["draft_id"])
    after = counts()
    check("2. Salva: the current version becomes operative, leaves the drafts, applies nothing",
          saved["ok"] and saved["draft_removed"] and saved["version_no"] == 1 and saved["method"] == "CODE"
          and after == {"rules": 1, "versions": 1, "drafts": 0, "decisions": 0}, detail=f"{saved} {after}")
    rule_id = saved["rule_id"]
    page = client.get("/bank/ai-rules").data.decode()
    check("2b. the rule is in the operative list; the draft is gone from the drafts list",
          f'data-rule-id="{rule_id}"' in page and "ai-rule-draft-open" not in page)

    status, edit_draft = post("/bank/ai-rules/drafts", rule_id=rule_id, rule_text=RULE_B)
    status, saved_b = post("/bank/ai-rules/save", rule_text=RULE_B, draft_id=edit_draft["draft_id"])
    after = counts()
    check("3. a draft of an operative rule is saved into THAT rule — a new version, never a duplicate",
          saved_b["ok"] and saved_b["rule_id"] == rule_id and saved_b["version_no"] == 2 and saved_b["draft_removed"]
          and after["rules"] == 1 and after["versions"] == 2 and after["drafts"] == 0, detail=f"{saved_b} {after}")

    # ------------------------------------------------- no valid interpretation
    status, blocked = post("/bank/ai-rules/save", rule_text=RULE_BLOCKED)
    check("4. a rule whose interpretation is not executable is NOT saved as operative, and says what is missing",
          status == 400 and "non è valida" in blocked["error"] and "festivo" in blocked["error"]
          and counts()["rules"] == 1, detail=str(blocked))
    status, blocked_edit = post("/bank/ai-rules/save", rule_id=rule_id, rule_text=RULE_BLOCKED)
    with SessionFactory() as s:
        version_now = ai_rule_operations.current_version(s.get(m.BankAiRule, rule_id))
        kept = (version_now.version_no, version_now.rule_text)
    check("4b. on an operative rule it is refused too, and the current version stays as it is",
          status == 400 and "resta invariata" in blocked_edit["error"] and kept == (2, RULE_B), detail=str(kept))
    os.environ["RFONE_BANK_AI_MODE"] = "SESSION"
    try:
        status, session_missing = post("/bank/ai-rules/save", rule_text=RULE_A + " Nuovo testo.")
    finally:
        os.environ.pop("RFONE_BANK_AI_MODE", None)
    check("4c. SESSION mode, no interpretation yet: refused, asking for Preview and the session",
          status == 400 and "Preview" in session_missing["error"] and counts()["rules"] == 1, detail=str(session_missing))

    # -------------------------------- text / version / interpretation together
    status, preview_b = post("/bank/ai-rules/preview", rule_text=RULE_B, rule_id=rule_id, scope_selected="on",
                             selected_ids=f"{ids[0]},{ids[1]}")
    status, mismatch = post("/bank/ai-rules/save-apply", rule_text=RULE_A, rule_id=rule_id, scope_selected="on",
                            selected_ids=f"{ids[0]},{ids[1]}", preview_id=preview_b["preview_id"])
    after = counts()
    check("5. a preview of another text cannot authorize the application: refused before anything is written",
          status == 409 and mismatch["needs_preview"] and after["versions"] == 2 and after["decisions"] == 0)

    client.post("/bank/ai-rules/instructions", data={"csrf_token": csrf, "instructions": "Nuove istruzioni."})
    status, resaved = post("/bank/ai-rules/save", rule_text=RULE_B, rule_id=rule_id)
    status, stale = post("/bank/ai-rules/save-apply", rule_text=RULE_B, rule_id=rule_id, scope_selected="on",
                         selected_ids=f"{ids[0]},{ids[1]}", preview_id=preview_b["preview_id"])
    after = counts()
    check("5b. a new interpretation of the same text is a new version; the preview of the old one cannot apply it",
          resaved["ok"] and resaved["version_no"] == 3 and resaved["new_version"]
          and status == 409 and "another interpretation" in stale["error"] and after["decisions"] == 0,
          detail=f"{resaved} {stale}")

    # ------------------------------------------------------- Salva e Applica
    status, apply_draft = post("/bank/ai-rules/drafts", rule_id=rule_id, rule_text=RULE_B)
    status, preview_ok = post("/bank/ai-rules/preview", rule_text=RULE_B, rule_id=rule_id, scope_selected="on",
                              selected_ids=f"{ids[0]},{ids[1]}")

    original_write = ai_rule_operations._write
    def failing_write(session, txn, *args, **kwargs):  # noqa: E306 — one movement fails
        if txn.id == ids[1]:
            raise RuntimeError("simulated write failure")
        return original_write(session, txn, *args, **kwargs)
    ai_rule_operations._write = failing_write
    try:
        status, partial = post("/bank/ai-rules/save-apply", rule_text=RULE_B, rule_id=rule_id, scope_selected="on",
                               selected_ids=f"{ids[0]},{ids[1]}", preview_id=preview_ok["preview_id"],
                               draft_id=apply_draft["draft_id"])
    finally:
        ai_rule_operations._write = original_write
    check("6. an application with a movement in error is NOT complete, keeps the draft and says so",
          partial["ok"] and partial["applied"] and partial["complete"] is False and not partial["draft_removed"]
          and partial["application"]["errors"] == 1 and counts()["drafts"] == 1, detail=str(partial))

    status, preview_ok2 = post("/bank/ai-rules/preview", rule_text=RULE_B, rule_id=rule_id, scope_selected="on",
                               selected_ids=f"{ids[0]},{ids[1]}")
    status, done = post("/bank/ai-rules/save-apply", rule_text=RULE_B, rule_id=rule_id, scope_selected="on",
                        selected_ids=f"{ids[0]},{ids[1]}", preview_id=preview_ok2["preview_id"],
                        draft_id=apply_draft["draft_id"])
    after = counts()
    with SessionFactory() as s:
        changed = {t.id for t in s.scalars(select(m.FinancialTransaction).where(
            m.FinancialTransaction.explanation_id.is_not(None)))}
    check("7. Salva e Applica completes on the chosen scope, then removes the draft; same rule, no duplicate",
          done["ok"] and done["complete"] and done["draft_removed"] and done["rule_id"] == rule_id
          and after["rules"] == 1 and after["drafts"] == 0 and changed == {ids[0], ids[1]}, detail=f"{done} {changed}")

    # ---------------------------------------------------------- Per il futuro
    status, off = post("/bank/ai-rules/save", rule_text=RULE_B, rule_id=rule_id)
    with SessionFactory() as s:
        no_future = ai_rule_operations.import_context(s)
    status, on = post("/bank/ai-rules/save", rule_text=RULE_B, rule_id=rule_id, scope_future="on")
    with SessionFactory() as s:
        context = ai_rule_operations.import_context(s)
        future_rules = [r.id for r, _v, _s in context.entries] if context else []
    check("8. “Per il futuro” decides the import: off → not applied to new movements, on → applied",
          not off["apply_future"] and no_future is None and on["apply_future"] and future_rules == [rule_id])
    asked = calls.get("asked", [])
    check("9. the AI is never asked twice for the same text and instructions (interpretation saved and reused)",
          len(asked) == len(set(asked)), detail=str(asked))

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
