"""Bank > AI Rules — "ends with a final number", the WHO up to it, the explicit override option and overlaps
(BANK_AI_RULES_011).

On a throwaway database, over HTTP for the preview and through the service for the application. The AI provider
is replaced INSIDE THIS TEST ONLY by a stand-in that interprets the rules. Invented names only:

* "ends_with_number": once trimmed, the description ends with a space and a block made ONLY of digits; a final
  code mixing letters and digits ("JPM99cxov680") is not a final number;
* WHO "before_final_number": the text after the start text (any case, leading spaces ignored) and before the
  final number, trimmed, upper case, other numbers kept; no final number / nothing between → not changed;
* "not_contains JPM" excludes those descriptions;
* the option "Sostituisci anche WHO/WHY manuali, Standard o confermati": OFF by default — manual, Standard and
  confirmed movements stay PROTECTED; ON for this rule only — they are replaced, "Da confermare", the override
  is named in the note and in the decision, a confirmation is withdrawn with For Whom kept; another rule
  without the option still sees them protected; the option is part of the preview key (apply needs a preview
  made with the same option) and of the rule's version;
* overlaps: a movement whose current WHO was written by another AI rule, or matched by another active AI rule,
  is shown;
* the preview writes nothing.

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rules_final_number_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rules-final-number-secret"
os.environ.pop("RFONE_BANK_AI_MODE", None)

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from sqlalchemy import select  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import ai_rule_operations  # noqa: E402
from rfone_data_store.bank_reconciliation import ai_rules  # noqa: E402
from rfone_data_store.bank_reconciliation import economic_allocation  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
RULE = ("Se la descrizione, ignorando gli spazi iniziali e finali, comincia con “Pay to” (maiuscole indifferenti), "
        "termina con uno spazio e un blocco di sole cifre e non contiene “XREF”: il WHO è il testo tra “Pay to” e il "
        "numero finale, in maiuscolo; sostituisci il WHO e assegna il suo WHY di default, vuoto se non ne ha; For Whom "
        "invariato; “Da confermare” solo se cambia WHO o WHY. La sostituzione è autorizzata anche per classificazioni "
        "manuali, Standard e confermate.")
COVERAGE = [
    {"instruction": "comincia con “Pay to”", "represented_by": "condition starts_with"},
    {"instruction": "termina con uno spazio e sole cifre", "represented_by": "condition ends_with_number"},
    {"instruction": "non contiene “XREF”", "represented_by": "condition not_contains"},
    {"instruction": "WHO tra “Pay to” e il numero finale", "represented_by": "who.before_final_number"},
    {"instruction": "WHY di default, vuoto se manca", "represented_by": "why.who_default clear + replace_existing"},
    {"instruction": "Da confermare se cambia", "represented_by": "status to_confirm"},
    {"instruction": "anche manuali, Standard e confermate", "represented_by": "rule option + replace_existing"},
]
FULL = {
    "kind": "STRUCTURED",
    "conditions": [{"field": "description", "op": "starts_with", "value": "Pay to"},
                   {"field": "description", "op": "ends_with_number"},
                   {"field": "description", "op": "not_contains", "value": "XREF"}],
    "who": {"mode": "before_final_number", "start": "Pay to", "start_at": "beginning"},
    "why": {"mode": "who_default", "if_missing": "clear"},
    "for_whom": None, "status": {"mode": "to_confirm"}, "only_if_who_differs": False, "replace_existing": True,
    "branches": [], "coverage": COVERAGE, "unsupported": [],
}
OTHER_RULE = "Se la descrizione contiene “Pay to Mario”, il WHO è “MARIO ROSSI”."


def copy(value):
    return json.loads(json.dumps(value))


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_fn", display_name="AI FN", password="AiFnPass123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_fn").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF FN, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        entity = m.ReportingEntity(code="RE_FN", name="RF FN", entity_type="LEGAL", legal_entity_id=llc.id,
                                   status="ACTIVE")
        checking = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT",
                                       display_name="FN Checking", institution="CHASE", last_four="5001",
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
        publix = m.BankOccurrence(canonical_name="PUBLIX", occurrence_type_id=counterparty.id, status="ACTIVE")
        s.add_all([mario, publix])
        s.flush()
        standard = m.BankReconciliationStandard(
            match_type="CONTAINS_TEXT", normalized_pattern="PAY TO MARIO ROSSI 7", match_field="DESCRIPTION",
            occurrence_id=publix.id, transaction_reason_id=why_other.id,
            accounting_classification_id=why_other.accounting_classification_id, reporting_entity_id=entity.id,
            status="ACTIVE", approved_at=datetime.now(timezone.utc))
        s.add(standard)
        s.flush()
        seq = [0]

        def tx(day, description):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, day),
                transaction_date=date(2026, 9, day), description_original=description,
                description_normalized=description, amount_minor=-3000 - seq[0], status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"fn-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            return t

        def decide(t, who, why, source="RULE", standard_id=None, notes="test setup"):
            extra = (dict(reconciliation_standard_id=standard_id, accounting_destination_source=m.DESTINATION_SOURCE_STANDARD,
                          accounting_classification_id=why.accounting_classification_id) if standard_id else {})
            recognition._create_decision_row(
                s, t, occurrence_id=who.id if who else None, transaction_reason_id=why.id if why else None,
                recognition_rule_id=None, decision_source=source,
                decision_status="HUMAN_CONFIRMED" if source == "HUMAN" else "AUTO_APPLIED",
                confidence=None, explanation_notes=notes, **extra)

        t = {
            "plain": tx(1, "  pay to Mario Rossi 30541248046  "),
            "inner_number": tx(2, "Pay to Studio 54 Design 123456"),
            "code": tx(3, "Pay to Mario Rossi XREF99cxov680"),
            "xref_digits": tx(4, "Pay to Mario Rossi XREF 12345"),
            "no_number": tx(5, "Pay to Mario Rossi"),
            "glued": tx(6, "Pay to Mario Rossi12345"),
            "empty": tx(7, "Pay to 12345"),
            "not_start": tx(8, "Bonifico Pay to Mario Rossi 12345"),
            "manual": tx(9, "Pay to Mario Rossi 9001"),
            "standard": tx(10, "Pay to Mario Rossi 7"),
            "confirmed": tx(11, "Pay to Mario Rossi 9002"),
            "confirmed_same": tx(12, "Pay to Mario Rossi 9003"),
            "other_rule": tx(13, "Pay to Mario Rossi 9004"),
        }
        decide(t["manual"], publix, why_other, source="HUMAN")
        decide(t["standard"], publix, why_other, standard_id=standard.id)
        decide(t["confirmed"], publix, why_other, source="HUMAN")
        economic_allocation.set_allocations(s, financial_transaction_id=t["confirmed"].id, specs=[
            economic_allocation.AllocationSpec(amount_minor=t["confirmed"].amount_minor, reporting_entity_id=entity.id,
                                               transaction_reason_id=why_other.id, status=economic_allocation.COMPLETE,
                                               decision_source="HUMAN")])
        decide(t["confirmed_same"], mario, why_default, source="HUMAN")
        economic_allocation.set_allocations(s, financial_transaction_id=t["confirmed_same"].id, specs=[
            economic_allocation.AllocationSpec(amount_minor=t["confirmed_same"].amount_minor,
                                               reporting_entity_id=entity.id, transaction_reason_id=why_default.id,
                                               status=economic_allocation.COMPLETE, decision_source="HUMAN")])
        decide(t["other_rule"], publix, why_other, notes="AI Rule #77 v1 applied to existing movements (all).")
        s.commit()
        ids = {k: v.id for k, v in t.items()}
        entity_id, why_default_id = entity.id, why_default.id

    prompts: list[str] = []

    def stand_in(prompt: str) -> dict:
        prompts.append(prompt)
        rule = prompt.split("RULE:\n")[1].split("\n\nEXAMPLE")[0]
        if rule == OTHER_RULE:
            return {"kind": "STRUCTURED",
                    "conditions": [{"field": "description", "op": "contains", "value": "Pay to Mario"}],
                    "who": {"mode": "fixed", "name": "MARIO ROSSI"}, "why": None, "status": None,
                    "only_if_who_differs": False, "replace_existing": False, "branches": [], "unsupported": [],
                    "coverage": [{"instruction": "Pay to Mario → MARIO ROSSI", "represented_by": "who.fixed"}]}
        return copy(FULL)

    ai_client.generate_json = stand_in
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_fn", "password": "AiFnPass123!", "csrf_token": csrf})
    page = client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()
    csrf = CSRF_RE.search(page).group(1)

    def preview(rule=RULE, **extra):
        data = {"csrf_token": csrf, "rule_text": rule, "origin_transaction_id": str(ids["plain"]),
                "date_from": "2026-09-01", "date_to": "2026-09-30", "create_missing_who": "on", "scope_all": "on"}
        data.update(extra)
        return client.post("/bank/ai-rules/preview", data=data, headers={"X-Requested-With": "fetch"}).get_json()

    def state():
        with SessionFactory() as s:
            return {k: (s.get(m.FinancialTransaction, v).explanation_id,
                        tuple((a.reporting_entity_id, a.status) for a in
                              economic_allocation.get_allocations(s, financial_transaction_id=v)))
                    for k, v in ids.items()}

    # ------------------------------------------------------------- building blocks
    fn = ai_rules.final_number
    ex = ai_rules.extract_before_final_number
    a = {"start": "Pay to", "start_at": "beginning"}
    check("1. final number: a space then only digits at the end (trailing spaces ignored); a mixed code is not one",
          fn("Pay to X 30541248046  ") == "30541248046" and fn("Pay to X JPM99cxov680") is None
          and fn("Pay to X12345") is None and fn("12345") is None)
    check("2. WHO up to the final number: any case and leading spaces at the start, trimmed, upper case, inner numbers "
          "kept; no final number / glued / nothing between / not at the start → not changed",
          ex("  pay to  Leo Windows Cleaning 30541248046 ", a) == ("MATCH", "LEO WINDOWS CLEANING")
          and ex("Pay to Studio 54 Design 123456", a) == ("MATCH", "STUDIO 54 DESIGN")
          and ex("Pay to Leo JPM99cxov680", a)[0] == "NO_MARKER" and ex("Pay to Leo12345", a)[0] == "NO_MARKER"
          and ex("Pay to 12345", a)[0] == "EMPTY" and ex("X Pay to Leo 1", a)[0] == "NO_PREFIX")
    spec, reason = ai_rules.validate_interpretation(copy(FULL), RULE)
    check("3. the interpretation with the new condition and extraction is valid (spec version 5)",
          spec is not None and spec["version"] == ai_rules.SPEC_VERSION and spec["conditions"][1] == {
              "field": "description", "op": "ends_with_number", "value": ""}, detail=str(reason))
    bad = ai_rules.validate_interpretation({**copy(FULL), "who": {"mode": "before_final_number", "start": "Paid"}},
                                           RULE)
    check("4. a start text not written in the rule is refused", bad[0] is None and "not written" in bad[1])
    check("5. the page offers the option, OFF by default", 'id="ai-rule-override-protected"' in page
          and re.search(r'<input type="checkbox" name="override_protected" id="ai-rule-override-protected">', page))

    # ------------------------------------------------------------- option OFF
    before = state()
    p = preview()
    items = {i["id"]: i for i in p.get("match_items", [])}
    by = {k: items.get(v) for k, v in ids.items()}
    doubts = {i["id"] for i in p.get("doubt_items", [])}
    check("6. matches: the final-number format only; mixed code, XREF, no number, glued, not at the start excluded; "
          "nothing between is doubtful",
          p.get("ok") and set(items) == {ids[k] for k in ("plain", "inner_number", "manual", "standard", "confirmed",
                                                         "confirmed_same", "other_rule")}
          and doubts == {ids["empty"]}, detail=str(sorted(k for k, v in ids.items() if v in items)))
    check("7. WHO, WHY: the extracted WHO and its default WHY; inner numbers kept; Da confermare",
          by["plain"]["proposed_who"] == "MARIO ROSSI" and by["plain"]["plan"] == "UPDATED"
          and "status → Da confermare" in by["plain"]["plan_note"]
          and by["inner_number"]["proposed_who"] == "STUDIO 54 DESIGN", detail=str(by["plain"]))
    check("8. option OFF (default): manual, Standard and confirmed are PROTECTED",
          by["manual"]["plan"] == "PROTECTED" and by["standard"]["plan"] == "PROTECTED"
          and by["confirmed"]["plan"] == "PROTECTED" and not p.get("override_protected") and p.get("overridden") == 0)
    check("9. a WHO written by another AI rule is replaced (replace_existing) and shown as an overlap",
          by["other_rule"]["plan"] == "UPDATED" and "written by AI rule #77" in by["other_rule"]["plan_note"]
          and p.get("overlaps") >= 1 and "77" in (p.get("overlap_rules") or {}), detail=str(by["other_rule"]))
    check("10. the preview writes nothing", state() == before)

    # ------------------------------------------------------------- option ON
    p_on = preview(override_protected="on")
    on = {k: {i["id"]: i for i in p_on.get("match_items", [])}.get(v) for k, v in ids.items()}
    check("11. option ON: manual, Standard and confirmed are replaced — the override named, Da confermare",
          all(on[k]["plan"] == "UPDATED" and "OVERRIDES" in on[k]["plan_note"] and "Sostituisci anche" in
              on[k]["plan_note"] and "status → Da confermare" in on[k]["plan_note"]
              for k in ("manual", "standard", "confirmed")) and p_on.get("override_protected")
          and p_on.get("overridden") == 3, detail=str({k: on[k]["plan_note"] for k in ("manual", "standard", "confirmed")}))
    check("12. option ON, a confirmed movement already as the rule says: UNCHANGED, still confirmed",
          on["confirmed_same"]["plan"] == "UNCHANGED", detail=on["confirmed_same"]["plan_note"])
    check("13. option ON: a confirmed movement's note says the confirmation is withdrawn and For Whom kept",
          "confirmation withdrawn, For Whom kept" in on["confirmed"]["plan_note"])
    check("14. the two previews have different keys (the option is part of what a preview authorizes)",
          p_on.get("scope_key") != p.get("scope_key"))

    # ------------------------------------- saving and applying (throwaway database)
    with SessionFactory() as s:
        saved = ai_rule_operations.save_rule(s, rule_id=None, rule_text=RULE, create_missing_who=True,
                                             apply_future=False, origin_transaction_id=ids["plain"], account_id=None,
                                             generate=stand_in, override_protected=True)
        s.commit()
        rule_id, version_option = saved.rule.id, saved.version.override_protected
    check("15. the option is recorded on the rule's version", version_option is True)
    with SessionFactory() as s:
        rule = s.get(m.BankAiRule, rule_id)
        try:
            ai_rule_operations.apply_rule(s, rule=rule, scope="ALL", selected_ids=None,
                                          preview_id=p.get("preview_id"), account_id=None)
            refused = None
        except ai_rule_operations.NeedsPreview as exc:
            refused = str(exc)
        s.rollback()
    check("16. a preview made with the option OFF cannot authorize applying the rule with the option ON",
          refused is not None and "Sostituisci anche" in refused, detail=str(refused))
    p_rule = preview(override_protected="on", rule_id=str(rule_id))
    with SessionFactory() as s:
        rule = s.get(m.BankAiRule, rule_id)
        application = ai_rule_operations.apply_rule(s, rule=rule, scope="ALL", selected_ids=None,
                                                    preview_id=p_rule.get("preview_id"), account_id=None)
        s.commit()
        current = {k: recognition.get_current_explanation(s, financial_transaction_id=v) for k, v in ids.items()}
        allocations = {k: economic_allocation.get_allocations(s, financial_transaction_id=v) for k, v in ids.items()}
        counts = (application.updated, application.unchanged, application.protected, application.errors)
    check("17. applied with the option: manual / Standard / confirmed now MARIO ROSSI + default WHY, Da confermare, "
          "the override written in the decision",
          all(current[k].occurrence_id is not None and current[k].transaction_reason_id == why_default_id
              and current[k].decision_status == "NEEDS_HUMAN_REVIEW" and "OVERRIDES" in current[k].explanation_notes
              and current[k].reconciliation_standard_id is None
              for k in ("manual", "standard", "confirmed")), detail=str(counts))
    check("18. the confirmed movement keeps its For Whom, its confirmation withdrawn (pending again)",
          len(allocations["confirmed"]) == 1 and allocations["confirmed"][0].reporting_entity_id == entity_id
          and allocations["confirmed"][0].status == m.ALLOCATION_NEEDS_OPERATOR)
    check("19. the confirmed movement already as the rule says stays confirmed (decision and For Whom untouched)",
          current["confirmed_same"].decision_status == "HUMAN_CONFIRMED"
          and allocations["confirmed_same"][0].status == economic_allocation.COMPLETE and counts[-1] == 0)

    # ------------------------- another rule WITHOUT the option still sees protections
    with SessionFactory() as s:
        decide_ids = ids["manual"]
        txn = s.get(m.FinancialTransaction, decide_ids)
        publix_id = s.scalar(select(m.BankOccurrence.id).where(m.BankOccurrence.canonical_name == "PUBLIX"))
        recognition._create_decision_row(s, txn, occurrence_id=publix_id, transaction_reason_id=why_default_id,
                                         recognition_rule_id=None, decision_source="HUMAN",
                                         decision_status="HUMAN_CONFIRMED", confidence=None,
                                         explanation_notes="manual again")
        s.commit()
    other = preview(OTHER_RULE)
    other_items = {i["id"]: i for i in other.get("match_items", [])}
    check("20. another rule without the option: the manual movement is PROTECTED (protections unchanged)",
          other_items[ids["manual"]]["plan"] == "PROTECTED" and not other.get("override_protected"))
    check("21. overlaps with the other active AI rule are shown on its movements",
          "also matched by AI rule #" + str(rule_id) in other_items[ids["plain"]]["plan_note"]
          and other.get("overlaps", 0) >= 1, detail=other_items[ids["plain"]]["plan_note"])

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
