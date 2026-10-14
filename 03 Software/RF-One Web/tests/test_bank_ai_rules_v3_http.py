"""Bank > AI Rules — structured-v3 engine capabilities (BANK_AI_RULES_008).

On a throwaway database, over HTTP for the preview and through the service
for the application. The AI provider is replaced INSIDE THIS TEST ONLY by a
stand-in that interprets the rules; the application itself never simulates
an answer. The rule used is deliberately NOT the Zelle rule: the
capabilities are general.

* extraction between two texts found ANYWHERE in the description, the end
  text matched in ANY case; the WHO trimmed, spaces collapsed, upper case;
  wrong order or a missing text → the movement is not changed; nothing in
  between → doubtful, never applied;
* the WHY is the DEFAULT WHY registered on the WHO; a WHO with none — or a
  new WHO — empties the WHY ("clear");
* "only if the WHO differs": the same WHO (case and spaces aside) changes
  nothing — WHY and status kept;
* "replace_existing": a different WHO decided by another rule is replaced;
  manual decisions stay PROTECTED, never executed;
* "Da confermare": a changed movement's decision is NEEDS_HUMAN_REVIEW
  (not a resolved decision status);
* an interpretation must account for every instruction (coverage): one with
  an unsupported instruction, one without coverage, or an OTHER answer is
  BLOCKED — no simplified version, and no movement-by-movement AI call
  unless asked explicitly;
* the preview names the provider and model that actually interpreted the
  rule — a saved interpretation from a Claude Code session is reused with no
  AI call and shown as such;
* the preview writes nothing on movements.

BANK_OLD_RULES_REMOVAL_001: Reconciliation Standards were removed from the
product, so the Standard-protected movement ("Pagamento a Mario Rossi REF7")
and its Standard fixture went with them. Checks 9 and 18 keep only their
manual (HUMAN) part - the Standard half of each went with the Standards. No
check number was removed.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rules_v3_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rules-v3-secret"

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
from rfone_data_store.bank_reconciliation import ai_rules  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
RULE = ("Se la descrizione contiene “Pagamento a” seguito da “REF”, senza distinzione tra maiuscole e minuscole, il "
        "WHO è il testo tra “Pagamento a” e “REF”, senza spazi iniziali e finali e in maiuscolo. Se il WHO attuale manca "
        "o è diverso: assegna il WHO, sostituendo quello deciso da altre regole; assegna il WHY di default del WHO, "
        "oppure lascia il WHY vuoto se non ne ha; imposta lo stato “Da confermare”. Se il WHO è già lo stesso, non "
        "modificare nulla.")
COVERAGE = [
    {"instruction": "descrizione contiene “Pagamento a” seguito da “REF”, maiuscole indifferenti",
     "represented_by": "conditions + who.between start_at anywhere, end_case ignore"},
    {"instruction": "WHO = testo tra i delimitatori, ripulito, maiuscolo", "represented_by": "who.between"},
    {"instruction": "se il WHO manca o è diverso, sostituendo quello di altre regole",
     "represented_by": "only_if_who_differs + replace_existing"},
    {"instruction": "WHY di default del WHO, vuoto se manca", "represented_by": "why.who_default if_missing clear"},
    {"instruction": "stato “Da confermare”", "represented_by": "status to_confirm"},
    {"instruction": "WHO già uguale: nessuna modifica", "represented_by": "only_if_who_differs"},
]
FULL = {
    "kind": "STRUCTURED",
    "conditions": [{"field": "description", "op": "contains", "value": "Pagamento a"},
                   {"field": "description", "op": "contains", "value": "REF"}],
    "who": {"mode": "between", "start": "Pagamento a", "end": "REF", "start_at": "anywhere", "end_case": "ignore"},
    "why": {"mode": "who_default", "if_missing": "clear"},
    "status": {"mode": "to_confirm"}, "only_if_who_differs": True, "replace_existing": True,
    "branches": [], "coverage": COVERAGE, "unsupported": [],
}
RULE_UNSUPPORTED = RULE + " Invia anche una email al titolare."
RULE_NO_COVERAGE = RULE + " Sempre."
RULE_OTHER = RULE + " Solo nei giorni festivi."
RULE_SESSION = RULE + " (sessione)"


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_v3", display_name="AI V3", password="AiV3pass123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_v3").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF V3, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        entity = m.ReportingEntity(code="RE_V3", name="RF V3", entity_type="LEGAL", legal_entity_id=llc.id,
                                   status="ACTIVE")
        checking = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT",
                                       display_name="V3 Checking", institution="CHASE", last_four="3001",
                                       currency="USD")
        s.add_all([entity, checking])
        s.flush()
        whys = s.scalars(select(m.BankTransactionReason).where(
            m.BankTransactionReason.status == "ACTIVE",
            m.BankTransactionReason.accounting_classification_id.is_not(None)).order_by(m.BankTransactionReason.id)).all()
        why_default, why_other = whys[0], whys[1]
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        mario = m.BankOccurrence(canonical_name="MARIO ROSSI", occurrence_type_id=counterparty.id, status="ACTIVE",
                                 default_transaction_reason_id=why_default.id)
        luigi = m.BankOccurrence(canonical_name="LUIGI VERDI", occurrence_type_id=counterparty.id, status="ACTIVE")
        publix = m.BankOccurrence(canonical_name="PUBLIX", occurrence_type_id=counterparty.id, status="ACTIVE")
        s.add_all([mario, luigi, publix])
        s.flush()
        seq = [0]

        def tx(day, description):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, day),
                transaction_date=date(2026, 9, day), description_original=description,
                description_normalized=description, amount_minor=-1000 - seq[0], status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"v3-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            return t

        def decide(t, who, why, source="RULE"):
            recognition._create_decision_row(
                s, t, occurrence_id=who.id if who else None, transaction_reason_id=why.id if why else None,
                decision_source=source, decision_status="AUTO_APPLIED",
                confidence=None, explanation_notes="test setup")

        t = {
            "none": tx(2, "Bonifico: PAGAMENTO A  Mario   Rossi ref 001"),
            "new": tx(3, "pagamento a Nuova Ditta REF9"),
            "diff": tx(4, "Pagamento a Mario Rossi REF2"),
            "same": tx(5, "Pagamento a  mario rossi REF3"),
            "human": tx(6, "Pagamento a Mario Rossi REF4"),
            "order": tx(8, "REF5 Pagamento a Mario Rossi"),
            "empty": tx(9, "Pagamento a REF6"),
            "nodefault": tx(10, "Pagamento a Luigi Verdi Ref8"),
            "unrelated": tx(11, "UNRELATED VENDOR"),
        }
        decide(t["diff"], publix, why_other)
        decide(t["same"], mario, why_other)
        decide(t["human"], publix, why_other, source="HUMAN")
        decide(t["nodefault"], None, why_other)
        s.commit()
        ids = {k: v.id for k, v in t.items()}
        why_default_name, why_default_id, why_other_name = why_default.name, why_default.id, why_other.name

    prompts: list[str] = []

    def stand_in(prompt: str) -> dict:
        prompts.append(prompt)
        if "Translate the rule into conditions" not in prompt:
            return {"items": []}
        rule = prompt.split("RULE:\n")[1].split("\n\nEXAMPLE")[0]
        if rule == RULE:
            return json.loads(json.dumps(FULL))
        if rule == RULE_UNSUPPORTED:
            return {**json.loads(json.dumps(FULL)), "unsupported": ["Invia anche una email al titolare"]}
        if rule == RULE_NO_COVERAGE:
            return {k: v for k, v in FULL.items() if k != "coverage"}
        return {"kind": "OTHER", "reason": "“Solo nei giorni festivi” cannot be expressed", "coverage": COVERAGE,
                "unsupported": ["Solo nei giorni festivi"]}

    ai_client.generate_json = stand_in
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_v3", "password": "AiV3pass123!", "csrf_token": csrf})
    csrf = CSRF_RE.search(client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()).group(1)

    def preview(rule, **extra):
        data = {"csrf_token": csrf, "rule_text": rule, "origin_transaction_id": str(ids["none"]),
                "date_from": "2026-09-01", "date_to": "2026-09-30"}
        data.update(extra)
        return client.post("/bank/ai-rules/preview", data=data, headers={"X-Requested-With": "fetch"}).get_json()

    def decisions():
        with SessionFactory() as s:
            return {k: s.get(m.FinancialTransaction, v).explanation_id for k, v in ids.items()}

    # ----------------------------------------------------------- the preview
    before = decisions()
    with SessionFactory() as s:
        explanations_before = s.scalar(select(func.count(m.BankTransactionExplanation.id)))
    p = preview(RULE, create_missing_who="on")
    items = {i["id"]: i for i in p.get("match_items", [])}
    doubts = {i["id"]: i for i in p.get("doubt_items", [])}
    by = {k: items.get(v) for k, v in ids.items()}
    check("1. the rule is interpreted once and executed by code (method CODE, 1 AI call)",
          p.get("ok") and p.get("method") == "CODE" and p.get("ai_calls") == 1, detail=str(p.get("error")))
    check("2. delimiters found anywhere, end text in any case; WHO trimmed, spaces collapsed, upper case",
          by["none"] and by["none"]["proposed_who"] == "MARIO ROSSI" and by["nodefault"]
          and by["nodefault"]["proposed_who"] == "LUIGI VERDI", detail=str(by["none"]))
    check("3. wrong order is not a match; nothing between the texts is a doubt, never applied; unrelated untouched",
          ids["order"] not in items and ids["order"] not in doubts and ids["empty"] in doubts
          and ids["empty"] not in items and ids["unrelated"] not in items)
    check("4. WHO absent → UPDATED: WHO assigned, the WHO's default WHY, status → Da confermare",
          by["none"]["plan"] == "UPDATED" and by["none"]["proposed_why"] == why_default_name
          and "status → Da confermare" in by["none"]["plan_note"], detail=str(by["none"]))
    check("5. a new WHO (no default WHY) → UPDATED with the WHY emptied",
          by["new"]["plan"] == "UPDATED" and by["new"]["proposed_who"] == "NUOVA DITTA" and by["new"]["proposed_who_is_new"]
          and not by["new"]["proposed_why"] and "has no default WHY: WHY empty" in by["new"]["plan_note"],
          detail=str(by["new"]))
    check("6. an existing WHO without default WHY → UPDATED, the previous WHY emptied",
          by["nodefault"]["plan"] == "UPDATED" and "WHO and WHY would change" in by["nodefault"]["plan_note"]
          and "has no default WHY: WHY empty" in by["nodefault"]["plan_note"], detail=str(by["nodefault"]))
    check("7. a different WHO decided by another rule is replaced (WHO and WHY), status → Da confermare",
          by["diff"]["plan"] == "UPDATED" and "WHO and WHY would change" in by["diff"]["plan_note"]
          and by["diff"]["proposed_why"] == why_default_name, detail=str(by["diff"]))
    check("8. the same WHO (case and spaces aside) → UNCHANGED: WHY and status kept",
          by["same"]["plan"] == "UNCHANGED" and "Same WHO" in by["same"]["plan_note"], detail=str(by["same"]))
    check("9. manual decisions are PROTECTED, never executed",
          by["human"]["plan"] == "PROTECTED" and "manually" in by["human"]["plan_note"])
    lines = p.get("interpretation_lines") or []
    check("10. the window lists what is represented: extraction options, default WHY, status, only-if, replace, "
          "protections, every instruction",
          any("anywhere in the description" in x and "any case" in x for x in lines)
          and any(x.startswith("WHY: the default WHY") and "emptied" in x for x in lines)
          and any(x.startswith("STATUS:") and "NEEDS_HUMAN_REVIEW" in x for x in lines)
          and any(x.startswith("ONLY IF") for x in lines) and any(x.startswith("REPLACES") for x in lines)
          and any(x.startswith("PROTECTED by RF-One") for x in lines)
          and sum(1 for x in lines if x.startswith("INSTRUCTION")) == len(COVERAGE), detail=str(lines))
    with SessionFactory() as s:
        explanations_after = s.scalar(select(func.count(m.BankTransactionExplanation.id)))
    check("11. the preview writes nothing on movements", decisions() == before and explanations_after == explanations_before)
    check("12. the preview names the provider and model that interpreted the rule",
          p.get("provider") == p.get("interpretation_provider") and p.get("interpretation_provider"))

    # ------------------------------------------------------------ blocking
    for label, rule, needle in (("an unsupported instruction", RULE_UNSUPPORTED, "not supported: Invia anche una email"),
                                ("no coverage", RULE_NO_COVERAGE, "coverage"),
                                ("an OTHER answer", RULE_OTHER, "giorni festivi")):
        prompts.clear()
        b = preview(rule)
        check(f"13. {label}: BLOCKED with the reason, no simplified version, no movement sent to the AI",
              not b.get("ok") and b.get("status") == "FAILED" and needle in (b.get("error") or "")
              and "Bloccata" in (b.get("error") or "") and not b.get("match_items")
              and not any("MOVEMENTS (" in x for x in prompts), detail=str(b.get("error")))
    check("14. validation: a default WHY with no WHO, and an unknown status, are rejected",
          ai_rules.validate_interpretation({**FULL, "who": None}, RULE)[0] is None
          and ai_rules.validate_interpretation({**FULL, "status": {"mode": "confirmed"}}, RULE)[0] is None)

    # ------------------------------------- a saved Claude Code session interpretation
    with SessionFactory() as s:
        instruction = ai_rules.current_instruction(s)
        key = ai_rules.interpretation_key(RULE_SESSION, instruction.instructions if instruction else None)
        spec, reason = ai_rules.validate_interpretation(json.loads(json.dumps(FULL)), RULE_SESSION)
        s.add(m.BankAiRuleInterpretation(cache_key=key, rule_text=RULE_SESSION, raw_answer=json.dumps(FULL),
                                         spec=json.dumps(spec), rejection_reason=reason,
                                         provider="CLAUDE_CODE_SESSION", model="claude-opus-5-5"))
        s.commit()
    prompts.clear()
    sp = preview(RULE_SESSION)
    check("15. a saved session interpretation is reused with no AI call and shown as its own provider and model",
          sp.get("ok") and sp.get("ai_calls") == 0 and not prompts and sp.get("interpretation_reused")
          and sp.get("provider") == "CLAUDE_CODE_SESSION" and sp.get("model") == "claude-opus-5-5",
          detail=str({k: sp.get(k) for k in ("ok", "ai_calls", "provider", "model", "error")}))

    # --------------------------------- SESSION mode: never a provider call
    os.environ["RFONE_BANK_AI_MODE"] = "SESSION"
    try:
        prompts.clear()
        waiting = preview(RULE + " (in attesa)")
        page = client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()
        check("15b. SESSION mode, no saved interpretation: the preview waits for the session — no AI call, the "
              "instruction to give the session, the provider is the session",
              not waiting.get("ok") and waiting.get("ai_calls") == 0 and not prompts
              and (waiting.get("error") or "").startswith(ai_rules.SESSION_WAIT_MARKER)
              and f"Preview #{waiting.get('preview_id')}" in waiting.get("error")
              and "Interpreta le AI Rules in attesa" in waiting.get("error")
              and waiting.get("provider") == "CLAUDE_CODE_SESSION" and "CLAUDE_CODE_SESSION" in page,
              detail=str({k: waiting.get(k) for k in ("ai_calls", "provider", "error")}))
        prompts.clear()
        again = preview(RULE_SESSION)
        check("15c. SESSION mode, saved interpretation: runs by code, no AI call",
              again.get("ok") and again.get("ai_calls") == 0 and not prompts)
    finally:
        del os.environ["RFONE_BANK_AI_MODE"]

    # ------------------------------- applying writes "Da confermare" (throwaway DB)
    with SessionFactory() as s:
        saved = ai_rule_operations.save_rule(s, rule_id=None, rule_text=RULE, create_missing_who=True,
                                             apply_future=False, origin_transaction_id=ids["none"],
                                             account_id=None, generate=stand_in)
        s.commit()
        rule_id = saved.rule.id
    pa = preview(RULE, create_missing_who="on", scope_all="on", rule_id=str(rule_id))
    with SessionFactory() as s:
        rule = s.get(m.BankAiRule, rule_id)
        application = ai_rule_operations.apply_rule(s, rule=rule, scope="ALL", selected_ids=None,
                                                    preview_id=pa.get("preview_id"), account_id=None)
        s.commit()
        current = {k: recognition.get_current_explanation(s, financial_transaction_id=v) for k, v in ids.items()}
        counts = (application.updated, application.unchanged, application.protected)
    after = decisions()
    check("16. applied: changed movements are NEEDS_HUMAN_REVIEW (Da confermare), not a resolved status",
          current["none"].decision_status == "NEEDS_HUMAN_REVIEW" and current["diff"].decision_status == "NEEDS_HUMAN_REVIEW"
          and "NEEDS_HUMAN_REVIEW" not in recognition.RESOLVED_DECISION_STATUSES, detail=str(counts))
    check("17. applied: default WHY assigned; no default → WHY empty; replaced WHO",
          current["none"].transaction_reason_id == why_default_id and current["nodefault"].transaction_reason_id is None
          and current["new"].transaction_reason_id is None and current["diff"].transaction_reason_id == why_default_id)
    check("18. applied: same WHO and manual movements are untouched (same decision)",
          after["same"] == before["same"] and after["human"] == before["human"]
          and current["same"].decision_status == "AUTO_APPLIED")

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
