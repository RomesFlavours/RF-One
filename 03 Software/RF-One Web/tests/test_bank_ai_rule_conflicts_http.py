"""Bank > AI Rules — conflicts with the other active rules, said before applying.

On a throwaway database, over HTTP. The AI provider is replaced INSIDE THIS
TEST ONLY by a stand-in that interprets and rewrites the rules; the
application itself never simulates an answer.

The case of rules #104 / #92: "WAWA-SHELL" assigns WHO COMPANY CAR when the
description contains WAWA, otherwise when it contains SHELL; "SHELL" assigns
WHO SHELL when the description contains SHELL. Both active, both match the
SHELL movements, different WHO: a conflict between rules.

* Rewrite with AI reports the conflict next to its own outcome — the rule's
  text is clear and is rewritten; the conflict is about the other rule —
  with the other rule's id and title, the overlapping conditions, what each
  rule assigns and an example movement;
* Preview and Save and Apply report it too; Save and Apply changes nothing
  where both rules apply (CONFLICT) and changes or disables no rule;
* a version only saved is said to be not yet applied to the existing
  transactions — in the list, in the window and in the Save answer — until
  Save and Apply applies it.

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rule_conflicts_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rule-conflicts-secret"
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
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
WAWA_SHELL = ("Se la descrizione contiene “WAWA”, il WHO è \"COMPANY CAR\"; altrimenti, se la descrizione contiene "
              "“SHELL”, il WHO è \"COMPANY CAR\".")
SHELL = "Se la descrizione contiene “SHELL”, il WHO è \"SHELL\"."


def interpretation(rule: str) -> dict:
    def contains(text):
        return [{"field": "description", "op": "contains", "value": text}]
    if "WAWA" in rule:
        return {"kind": "STRUCTURED", "conditions": [], "who": None, "why": None, "for_whom": None,
                "branches": [{"conditions": contains("WAWA"), "who": {"mode": "fixed", "name": "COMPANY CAR"},
                              "why": None, "for_whom": None},
                             {"conditions": contains("SHELL"), "who": {"mode": "fixed", "name": "COMPANY CAR"},
                              "why": None, "for_whom": None}],
                "status": None, "only_if_who_differs": False, "replace_existing": False, "unsupported": [],
                "coverage": [{"instruction": "WAWA → COMPANY CAR", "represented_by": "branches[0]"},
                             {"instruction": "altrimenti SHELL → COMPANY CAR", "represented_by": "branches[1]"}]}
    return {"kind": "STRUCTURED", "conditions": contains("SHELL"), "who": {"mode": "fixed", "name": "SHELL"},
            "why": None, "for_whom": None, "branches": [], "status": None, "only_if_who_differs": False,
            "replace_existing": False, "unsupported": [],
            "coverage": [{"instruction": "la descrizione contiene “SHELL”", "represented_by": "conditions"},
                         {"instruction": "il WHO è SHELL", "represented_by": "who.fixed"}]}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_conflicts", display_name="AI Conflicts",
                                       password="AiConflicts123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_conflicts").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF Conflicts, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        checking = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT",
                                       display_name="Conflicts Checking", institution="CHASE", last_four="7470",
                                       currency="USD")
        s.add(checking)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        for name in ("SHELL", "COMPANY CAR"):
            s.add(m.BankOccurrence(canonical_name=name, occurrence_type_id=counterparty.id, status="ACTIVE"))
        ids = {}
        for i, (key, text) in enumerate((("shell", "PURCHASE 04/17 SHELL SERVICE S SHELL SERVICE STORLANDO FL 429396"),
                                         ("wawa", "PURCHASE WAWA 5123 ORLANDO FL"),
                                         ("other", "PURCHASE PUBLIX 1488"))):
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, 2 + i),
                transaction_date=date(2026, 9, 2 + i), description_original=text, description_normalized=text,
                amount_minor=-5396 - i, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"conflicts-{i}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            ids[key] = t.id
        s.commit()

    def stand_in(prompt: str) -> dict:
        found = re.search(r"RULE:\n(.*?)\n\nEXAMPLE", prompt, re.S)
        if "Rewrite the rule in clear" in prompt and found:
            rule = found.group(1).strip()
            return {"status": "REWRITTEN", "text": rule, "ambiguities": [], "invented": [],
                    "who_why_values": ["COMPANY CAR"] if "WAWA" in rule else ["SHELL"]}
        return interpretation(prompt)

    ai_client.generate_json = stand_in
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_conflicts", "password": "AiConflicts123!", "csrf_token": csrf})
    csrf = CSRF_RE.search(client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()).group(1)

    def post(path, **data):
        form = {"csrf_token": csrf, "origin_transaction_id": str(ids["shell"]), "date_from": "2026-09-01",
                "date_to": "2026-09-30"}
        form.update({k: str(v) for k, v in data.items() if v is not None})
        response = client.post(path, data=form, headers={"X-Requested-With": "fetch"})
        return response.status_code, response.get_json()

    def rules_state():
        with SessionFactory() as s:
            return sorted((r.id, r.status, r.deleted_at is None, len(r.versions)) for r in s.scalars(select(m.BankAiRule)))

    def decisions():
        with SessionFactory() as s:
            return s.scalar(select(func.count(m.BankTransactionExplanation.id)))

    # ------------------------------------------------- the other rule, active
    status, wawa = post("/bank/ai-rules/save", rule_text=WAWA_SHELL, user_title="WAWA-SHELL", create_missing_who="on")
    wawa_id = wawa["rule_id"]
    check("1. rule “WAWA-SHELL” saved as operative and active", status == 200 and wawa["ok"], detail=str(wawa))

    # ------------------------------------- Rewrite with AI of a NEW rule
    status, rewritten = post("/bank/ai-rules/rewrite", rule_text=SHELL)
    conflicts = rewritten.get("conflicts") or []
    c = conflicts[0] if conflicts else {}
    check("2. Rewrite with AI: the clear text is rewritten and validated — the conflict is not a text problem",
          status == 200 and rewritten["ok"] and rewritten["status"] == "REWRITTEN", detail=str(rewritten))
    check("2b. … and the conflict is reported separately: the other rule's id and title, what each rule assigns",
          len(conflicts) == 1 and c["rule_id"] == wawa_id and c["rule_title"] == "WAWA-SHELL"
          and c["fields"] == ["WHO"] and c["this"]["who"] == "SHELL" and c["other"]["who"] == "COMPANY CAR",
          detail=str(conflicts))
    check("2c. … the overlapping condition and an example movement",
          c.get("other", {}).get("conditions") == "the description contains “SHELL”"
          and c.get("other", {}).get("branch") == "branch 2" and c.get("count") == 1
          and (c.get("example") or {}).get("id") == ids["shell"], detail=str(c))
    check("2d. … in one sentence: this rule assigns WHO = SHELL, the other WHO = COMPANY CAR to the SHELL movements",
          c.get("message") == f"This rule assigns WHO = SHELL, while rule #{wawa_id} ‘WAWA-SHELL’ assigns WHO = "
                              "COMPANY CAR to the movements where the description contains “SHELL”.",
          detail=c.get("message"))

    # ------------------------------------------------ saved, not applied yet
    status, shell = post("/bank/ai-rules/save", rule_text=SHELL, user_title="SHELL", create_missing_who="on")
    shell_id = shell["rule_id"]
    check("3. Save: the version is said to be saved but not yet applied to the existing transactions, with the "
          "conflict", shell["ok"] and shell["applied_to_existing"] is False
          and [x["rule_id"] for x in shell["rule_conflicts"]] == [wawa_id], detail=str(shell))
    page = client.get("/bank/ai-rules").data.decode()
    row = re.search(rf'<tr data-rule-id="{shell_id}".*?</tr>', page, re.S)
    check("3b. the list says “Saved, not applied to existing transactions” for that rule",
          row is not None and "Saved, not applied to existing transactions" in row.group(0))
    opened = client.get(f"/bank/ai-rules/rules/{shell_id}").get_json()
    check("3c. opening the rule says it too (applied_to_existing false)", opened["applied_to_existing"] is False)

    # ---------------------------------- Rewrite of the saved rule names it
    status, again = post("/bank/ai-rules/rewrite", rule_text=SHELL, rule_id=shell_id, user_title="SHELL")
    check("4. Rewrite of rule #SHELL: “Rule #… ‘SHELL’ assigns WHO = SHELL, while rule #… ‘WAWA-SHELL’ assigns "
          "WHO = COMPANY CAR …” — never compared with itself",
          [x["message"] for x in again["conflicts"]] == [
              f"Rule #{shell_id} ‘SHELL’ assigns WHO = SHELL, while rule #{wawa_id} ‘WAWA-SHELL’ assigns WHO = "
              "COMPANY CAR to the movements where the description contains “SHELL”."], detail=str(again["conflicts"]))

    # ------------------------------------------------------------- Preview
    status, preview = post("/bank/ai-rules/preview", rule_text=SHELL, rule_id=shell_id, user_title="SHELL",
                           create_missing_who="on", scope_all="on")
    check("5. Preview reports the same conflict, and plans the SHELL movement as CONFLICT",
          preview["ok"] and [x["rule_id"] for x in preview["rule_conflicts"]] == [wawa_id]
          and preview["conflicts"] == 1, detail=str({k: preview.get(k) for k in ("conflicts", "rule_conflicts")}))

    # ------------------------------------------------------ Save and Apply
    before_rules, before_decisions = rules_state(), decisions()
    status, applied = post("/bank/ai-rules/save-apply", rule_text=SHELL, rule_id=shell_id, user_title="SHELL",
                           create_missing_who="on", scope_all="on", preview_id=preview["preview_id"])
    check("6. Save and Apply: the conflict is reported, the SHELL movement is not changed",
          applied["ok"] and applied["application"]["conflicts"] == 1 and applied["application"]["updated"] == 0
          and [x["rule_id"] for x in applied["rule_conflicts"]] == [wawa_id], detail=str(applied))
    check("6b. no rule changed or disabled, no movement decided (nothing resolved silently)",
          rules_state() == before_rules and decisions() == before_decisions, detail=str(rules_state()))
    check("6c. the version is now applied to the existing transactions: said so, and the list no longer flags it",
          applied["applied_to_existing"] is True
          and client.get(f"/bank/ai-rules/rules/{shell_id}").get_json()["applied_to_existing"] is True
          and "Saved, not applied to existing transactions" not in (
              re.search(rf'<tr data-rule-id="{shell_id}".*?</tr>', client.get("/bank/ai-rules").data.decode(),
                        re.S).group(0)))

    # ----------------------------------------- no conflict: nothing reported
    status, alone = post("/bank/ai-rules/rewrite", rule_text=SHELL.replace("SHELL", "PUBLIX"))
    check("7. a rule no other active rule overlaps: no conflict reported", alone.get("conflicts") == [],
          detail=str(alone.get("conflicts")))

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
