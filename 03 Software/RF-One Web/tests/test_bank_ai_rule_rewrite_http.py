"""Bank > AI Rules — Rewrite with AI (BANK_AI_RULES_026).

On a throwaway database, over HTTP. The AI is replaced INSIDE THIS TEST ONLY
by a stand-in that answers the rewrite prompt and the interpretation prompt;
the application itself never simulates an answer.

* the button sits beside the rule's text; the rewrite prompt carries the
  interpreter's OWN description of its elements (no separate list);
* a supported rule is rewritten, verified by Preview's interpreter and
  returned; its WHO and WHY are exactly the original's;
* a Source "equal to" condition the interpreter cannot represent is reported,
  never turned into "contains" — and no rewrite is even asked;
* a rewrite that alters a WHO, adds a condition, is ambiguous, or fails is
  refused: no text is returned (the page keeps the original);
* nothing is saved or applied: no rule, version, draft, preview or decision.

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rule_rewrite_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rule-rewrite-secret"
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
from rfone_data_store.bank_reconciliation import ai_rules  # noqa: E402
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
ORIGINAL = 'Movimenti con PUBLIX nella descrizione: WHO "PUBLIX", WHY "Owner Personal — Food".'
REWRITTEN = 'Se la descrizione contiene “PUBLIX”, assegna WHO "PUBLIX" e WHY "Owner Personal — Food".'
WRONG_CASE = 'Se la descrizione contiene “PUBLIX”, assegna WHO "Publix" e WHY "Owner Personal — Food".'
ADDED = ('Se la descrizione contiene “PUBLIX” e il movimento è in uscita, assegna WHO "PUBLIX" e WHY '
         '"Owner Personal — Food".')
SOURCE_EQ = 'Se la Source è uguale a "Amex Gold", assegna WHO "AMEX".'
VAGUE = "Metti le spese di casa nel WHY giusto."
# BANK_AI_RULES_027 — "o … e" with two readings that execute differently: (PUBLIX) or (COSTCO and FL), or
# (PUBLIX or COSTCO) and FL. The interpreter alone CAN read it (it picks one): the rewrite must not.
AMBIGUOUS_OR = 'Se la descrizione contiene "PUBLIX" o "COSTCO" e "FL", assegna WHO "GROCERY".'
ONE_READING = 'Se la descrizione contiene “PUBLIX”, oppure contiene sia “COSTCO” sia “FL”, assegna WHO "GROCERY".'
INFORMAL = 'publix -> who "PUBLIX"'
INFORMAL_REWRITTEN = 'Se la descrizione contiene “publix”, assegna WHO "PUBLIX".'


def spec_for(text: str, *, direction: bool = False, who: str = "PUBLIX") -> dict:
    conditions = [{"field": "description", "op": "contains", "value": "PUBLIX"}]
    if direction:
        conditions.append({"field": "direction", "op": "is", "value": "money out"})
    return {"kind": "STRUCTURED", "conditions": conditions, "who": {"mode": "fixed", "name": who},
            "why": {"mode": "fixed", "name": "Owner Personal — Food"}, "branches": [], "status": None,
            "only_if_who_differs": False, "replace_existing": False, "unsupported": [],
            "coverage": [{"instruction": "PUBLIX nella descrizione", "represented_by": "conditions"},
                         {"instruction": "WHO e WHY", "represented_by": "who.fixed, why.fixed"}]}


INTERPRET = {ORIGINAL: spec_for(ORIGINAL), REWRITTEN: spec_for(REWRITTEN), WRONG_CASE: spec_for(WRONG_CASE, who="Publix"),
             ADDED: spec_for(ADDED, direction=True),
             SOURCE_EQ: {"kind": "OTHER", "reason": "the Source can only be checked with contains / does not contain",
                         "unsupported": ["la Source è uguale a “Amex Gold” (uguaglianza esatta)"],
                         "coverage": [{"instruction": "Source uguale a Amex Gold", "represented_by": "nothing"}]},
             AMBIGUOUS_OR: {**spec_for(AMBIGUOUS_OR), "who": {"mode": "fixed", "name": "GROCERY"}, "why": None},
             ONE_READING: {**spec_for(ONE_READING), "who": {"mode": "fixed", "name": "GROCERY"}, "why": None},
             INFORMAL: {"kind": "OTHER", "reason": "the arrow does not say what to check", "unsupported": [],
                        "coverage": [{"instruction": "publix ->", "represented_by": "nothing"}]},
             INFORMAL_REWRITTEN: {**spec_for(INFORMAL_REWRITTEN), "conditions": [
                 {"field": "description", "op": "contains", "value": "publix"}], "why": None},
             VAGUE: {"kind": "OTHER", "reason": "no condition and no WHY named", "unsupported": [],
                     "coverage": [{"instruction": "spese di casa", "represented_by": "nothing"}]}}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_rewrite", display_name="AI Rewrite", password="AiRewrite123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_rewrite").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF Rewrite, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        checking = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT",
                                       display_name="Rewrite Checking", institution="CHASE", last_four="3005",
                                       currency="USD")
        s.add(checking)
        s.flush()
        t = m.FinancialTransaction(
            payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, 2),
            transaction_date=date(2026, 9, 2), description_original="PUBLIX SUPER MARKET 1234",
            description_normalized="PUBLIX SUPER MARKET 1234", amount_minor=-1000, status="COMPLETED",
            duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
            fingerprint="rewrite-0", classification="UNKNOWN")
        s.add(t)
        s.commit()
        origin_id = t.id

    plan = {}                       # original text → what the rewrite stand-in answers
    asked = {"rewrite": [], "interpret": []}

    def stand_in(prompt: str) -> dict:
        rule = prompt.split("RULE:\n")[1].split("\n\nEXAMPLE")[0]
        if "Rewrite the rule in clear" in prompt:
            asked["rewrite"].append((rule, prompt))
            answer = plan[rule]
            if isinstance(answer, Exception):
                raise answer
            return answer
        asked["interpret"].append(rule)
        return INTERPRET[rule]

    ai_client.generate_json = stand_in
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_rewrite", "password": "AiRewrite123!", "csrf_token": csrf})
    page = client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()
    csrf = CSRF_RE.search(page).group(1)

    def rewrite(text):
        r = client.post("/bank/ai-rules/rewrite", data={"csrf_token": csrf, "rule_text": text,
                                                        "origin_transaction_id": str(origin_id)},
                        headers={"X-Requested-With": "fetch"})
        return r.status_code, r.get_json()

    def counts():
        with SessionFactory() as s:
            return {name: s.scalar(select(func.count()).select_from(model)) for name, model in (
                ("rules", m.BankAiRule), ("versions", m.BankAiRuleVersion), ("drafts", m.BankAiRuleDraft),
                ("previews", m.BankAiRulePreview), ("applications", m.BankAiRuleApplication),
                ("decisions", m.BankTransactionExplanation))}

    row = page[page.index('class="ai-rule-text-row"'):]
    row = row[:row.index('id="ai-rule-rewrite-status"')]
    check("1. “Rewrite with AI” sits beside the rule's text, with a hidden “Undo rewrite”",
          'id="ai-rule-text"' in row and ">Rewrite with AI</button>" in row and 'id="ai-rule-rewrite-undo" hidden' in row)
    before = counts()

    plan[ORIGINAL] = {"status": "REWRITTEN", "text": REWRITTEN, "who_why_values": ["PUBLIX", "Owner Personal — Food"],
                      "ambiguities": [], "invented": []}
    status, ok = rewrite(ORIGINAL)
    check("2. a supported rule is rewritten, verified by the interpreter and returned as “Rewritten and validated”",
          status == 200 and ok["ok"] and ok["text"] == REWRITTEN and ok["message"] == "Rewritten and validated"
          and REWRITTEN in asked["interpret"], detail=str(ok))
    check("3. its WHO and WHY are exactly the original's",
          '"PUBLIX"' in ok["text"] and '"Owner Personal — Food"' in ok["text"])
    prompt = asked["rewrite"][-1][1]
    check("4. the rewrite prompt carries the interpreter's own description of its elements",
          ai_rules.interpreter_capabilities() in prompt and ai_rules.interpreter_capabilities()
          in ai_rules._interpretation_prompt("x", "y", None))

    rewrites_before = len(asked["rewrite"])
    status, eq = rewrite(SOURCE_EQ)
    check("5. a Source “uguale a” the interpreter cannot represent is reported, no text returned, no rewrite asked",
          status == 200 and not eq["ok"] and eq["status"] == "UNSUPPORTED" and eq["text"] is None
          and any("uguale" in d for d in eq["details"]) and len(asked["rewrite"]) == rewrites_before, detail=str(eq))

    plan[ORIGINAL] = {"status": "REWRITTEN", "text": WRONG_CASE, "who_why_values": ["PUBLIX", "Owner Personal — Food"],
                      "ambiguities": [], "invented": []}
    status, wrong = rewrite(ORIGINAL)
    check("6. a rewrite that alters the WHO (“PUBLIX” → “Publix”) is refused, the original kept",
          not wrong["ok"] and wrong["text"] is None and any("Publix" in d for d in wrong["details"]), detail=str(wrong))

    plan[ORIGINAL] = {"status": "REWRITTEN", "text": ADDED, "who_why_values": ["PUBLIX", "Owner Personal — Food"],
                      "ambiguities": [], "invented": []}
    status, added = rewrite(ORIGINAL)
    check("7. a rewrite that adds a constraint (executed differently from the original) is refused",
          not added["ok"] and added["text"] is None and any("differently" in d for d in added["details"]),
          detail=str(added))

    plan[VAGUE] = {"status": "AMBIGUOUS", "clarify": ["quali movimenti sono “spese di casa”", "quale WHY assegnare"]}
    status, vague = rewrite(VAGUE)
    check("8. an ambiguous rule: not rewritten, says what to clarify",
          not vague["ok"] and vague["status"] == "AMBIGUOUS" and vague["text"] is None and len(vague["details"]) == 2,
          detail=str(vague))

    plan[ORIGINAL] = ai_client.AIProviderUnavailable("the CLI timed out")
    status, error = rewrite(ORIGINAL)
    check("9. an AI error: refused with the reason, no text returned (the original is kept)",
          status == 400 and not error["ok"] and "not changed" in error["message"], detail=str(error))

    # ------------------------------------------- BANK_AI_RULES_027: ambiguity is never resolved by a rewrite
    plan[AMBIGUOUS_OR] = {"status": "REWRITTEN", "text": ONE_READING, "who_why_values": ["GROCERY"],
                          "ambiguities": ["“o … e”: PUBLIX da solo, oppure PUBLIX o COSTCO sempre insieme a FL?"],
                          "invented": []}
    status, amb = rewrite(AMBIGUOUS_OR)
    check("11. an ambiguous rule (two readings, different results) is NOT rewritten even if the AI proposes one "
          "reading and the interpreter could run it: no text, no “Rewritten and validated”, the missing information "
          "is named", status == 200 and not amb["ok"] and amb["status"] == "AMBIGUOUS" and amb["text"] is None
          and amb["message"] != "Rewritten and validated" and "Missing information" in amb["message"]
          and any("FL" in d for d in amb["details"]), detail=str(amb))
    plan[AMBIGUOUS_OR] = {"status": "REWRITTEN", "text": ONE_READING, "who_why_values": ["GROCERY"]}
    status, unchecked = rewrite(AMBIGUOUS_OR)
    check("12. a rewrite without the AI's own check (ambiguities / invented) is refused",
          not unchecked["ok"] and unchecked["text"] is None, detail=str(unchecked))
    plan[AMBIGUOUS_OR] = {"status": "REWRITTEN", "text": ONE_READING, "who_why_values": ["GROCERY"],
                          "ambiguities": [], "invented": ["“oppure contiene sia COSTCO sia FL” — grouping chosen"]}
    status, invented = rewrite(AMBIGUOUS_OR)
    check("13. a rewrite that declares something added is refused",
          not invented["ok"] and invented["text"] is None and any("added" in d for d in invented["details"]),
          detail=str(invented))
    plan[INFORMAL] = {"status": "REWRITTEN", "text": INFORMAL_REWRITTEN, "who_why_values": ["PUBLIX"],
                      "ambiguities": [], "invented": []}
    status, informal = rewrite(INFORMAL)
    check("14. an informal wording with one reading only IS rewritten and validated (nothing invented)",
          informal["ok"] and informal["text"] == INFORMAL_REWRITTEN and informal["message"] == "Rewritten and validated",
          detail=str(informal))
    prompt = asked["rewrite"][-1][1]
    check("15. the rewrite prompt forbids picking a reading and asks for the self-check",
          "do NOT pick one reading" in prompt and '"ambiguities": [], "invented": []' in prompt)

    check("10. Rewrite never saves or applies: no rule, version, draft, preview, application or decision",
          counts() == before, detail=f"{before} {counts()}")

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
