"""Bank > AI Rules — the For Whom assignment and For Whom provenance (BANK_AI_RULES_010).

On a throwaway database, over HTTP for the preview and through the service for
the application and the import. The AI provider is replaced INSIDE THIS TEST
ONLY by a stand-in that interprets the rules; the application itself never
simulates an answer. The rule is a general one (invented entities and names),
not the rule of any real Source:

* For Whom is decided on its own, from the text right after a marker
  ("IND NAME:"), never from the WHO: marker in any case, leading spaces
  skipped, the COMPLETE name in any case, followed by the end or by other
  data — never by more letters (a longer name is not that name);
  marker missing or another name → For Whom unchanged;
* the entity must be an existing ACTIVE entity: an unknown or inactive one,
  or one not written in the rule, makes the interpretation invalid; an
  OTHER / unsupported answer stays blocked (no partial interpretation);
* provenance, not mere presence: a For Whom chosen by a person is kept (the
  WHO / WHY still change), alone it is PROTECTED; a For Whom written by
  another rule is replaced when the rule replaces, a CONFLICT otherwise; a
  For Whom of uncertain origin (pending evidence, split) is kept with the
  reason; an accounting-complete For Whom protects the movement; manual
  decisions stay PROTECTED;
* only For Whom changing is enough for "Da confermare"; nothing changing
  keeps the status;
* the preview shows the current and the proposed For Whom and writes
  nothing; applying writes ONE pending RULE allocation naming the AI Rule
  and logs For Whom before / after; the rule's own output is UNCHANGED on
  the next preview; the import applies it to a new movement;
* a BLOCKED interpretation of the previous engine is interpreted again; a
  VALID one is reused (no AI call).

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rules_for_whom_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rules-for-whom-secret"
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
from rfone_data_store.bank_reconciliation import ai_rules  # noqa: E402
from rfone_data_store.bank_reconciliation import economic_allocation  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
RULE = ("Cerca senza distinzione tra maiuscole e minuscole. Se la descrizione contiene “ORIG CO NAME:” seguito da "
        "“ORIG ID:”, il WHO è il testo tra i due, in maiuscolo, sostituendo quello attuale se diverso; assegna il WHY "
        "di default del WHO, vuoto se non ne ha. FOR WHOM: dopo “IND NAME:”, ignorando gli spazi, se il testo inizia "
        "con “ALFA LLC” assegna For Whom = RFA; se inizia con “BETA SRL” assegna For Whom = RFB; il nome può essere "
        "seguito da spazi e altri dati; altrimenti lascia invariato For Whom. Se cambia WHO, WHY o For Whom imposta "
        "“Da confermare”; se nulla cambia non modificare nulla. Mantieni protette le classificazioni manuali e "
        "Standard.")
COVERAGE = [
    {"instruction": "ORIG CO NAME: … ORIG ID: → WHO, sostituendo", "represented_by": "conditions + who.between + "
     "replace_existing"},
    {"instruction": "WHY di default, vuoto se manca", "represented_by": "why.who_default if_missing clear"},
    {"instruction": "IND NAME: ALFA LLC → RFA, BETA SRL → RFB, altrimenti invariato",
     "represented_by": "for_whom.after_text"},
    {"instruction": "Da confermare se cambia WHO, WHY o For Whom", "represented_by": "status to_confirm"},
    {"instruction": "classificazioni manuali e Standard protette", "represented_by": "RF-One protections"},
]
FOR_WHOM = {"mode": "after_text", "marker": "IND NAME:",
            "names": [{"name": "ALFA LLC", "entity": "RFA"}, {"name": "BETA SRL", "entity": "RFB"}]}
FULL = {
    "kind": "STRUCTURED",
    "conditions": [{"field": "description", "op": "contains", "value": "ORIG CO NAME:"},
                   {"field": "description", "op": "contains", "value": "ORIG ID:"}],
    "who": {"mode": "between", "start": "ORIG CO NAME:", "end": "ORIG ID:", "start_at": "anywhere",
            "end_case": "ignore"},
    "why": {"mode": "who_default", "if_missing": "clear"},
    "for_whom": FOR_WHOM,
    "status": {"mode": "to_confirm"}, "only_if_who_differs": False, "replace_existing": True,
    "branches": [], "coverage": COVERAGE, "unsupported": [],
}
RULE_NOREPLACE = RULE + " Non sostituire valori decisi da altre regole."
RULE_OTHER = RULE + " Solo nei giorni festivi."
RULE_OLD_BLOCKED = RULE + " (vecchia interpretazione bloccata)"
RULE_OLD_VALID = RULE + " (vecchia interpretazione valida)"


def copy(value):
    return json.loads(json.dumps(value))


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_fw", display_name="AI FW", password="AiFwPass123!",
                                       status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_fw").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF Test Holding, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        rfa = m.ReportingEntity(code="RE_RFA", name="RFA", entity_type="VIRTUAL", status="ACTIVE")
        rfb = m.ReportingEntity(code="RE_RFB", name="RFB", entity_type="VIRTUAL", status="ACTIVE")
        old = m.ReportingEntity(code="RE_OLDCO", name="OLDCO", entity_type="VIRTUAL", status="INACTIVE")
        checking = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT",
                                       display_name="FW Checking", institution="CHASE", last_four="4001",
                                       currency="USD")
        s.add_all([rfa, rfb, old, checking])
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
        seq = [0]

        def tx(day, ind_name, orig=True):
            seq[0] += 1
            description = ((f"ORIG CO NAME:Mario Rossi    ORIG ID:9{seq[0]:03d} DESC DATE:0901 " if orig else "PAYROLL ")
                           + (f"IND NAME:{ind_name}" if ind_name is not None else "CO ENTRY DESCR:PAYROLL"))
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, day),
                transaction_date=date(2026, 9, day), description_original=description,
                description_normalized=description, amount_minor=-2000 - seq[0], status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"fw-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            return t

        def decide(t, who, why, source="RULE"):
            recognition._create_decision_row(
                s, t, occurrence_id=who.id if who else None, transaction_reason_id=why.id if why else None,
                decision_source=source, decision_status="AUTO_APPLIED",
                confidence=None, explanation_notes="test setup")

        def allocate(t, entity, source="HUMAN", status=m.ALLOCATION_NEEDS_OPERATOR, notes="test setup", why=None):
            economic_allocation.set_allocations(s, financial_transaction_id=t.id, specs=[
                economic_allocation.AllocationSpec(
                    amount_minor=t.amount_minor, reporting_entity_id=entity.id if entity else None,
                    transaction_reason_id=why.id if why else None, status=status, decision_source=source,
                    notes=notes)])

        t = {
            "none": tx(2, "ALFA LLC                 TRN: 1"),
            "lower": tx(3, "   alfa llc AN"),
            "longer": tx(4, "ALFA LLCX"),
            "missing": tx(5, None),
            "other_name": tx(6, "GAMMA SPA"),
            "only_fw": tx(7, "BETA SRL"),
            "same_all": tx(8, "ALFA LLC"),
            "human_diff": tx(9, "ALFA LLC"),
            "human_only": tx(10, "ALFA LLC"),
            "auto_other": tx(11, "ALFA LLC"),
            "uncertain": tx(12, "ALFA LLC"),
            "split": tx(13, "ALFA LLC"),
            "complete": tx(14, "ALFA LLC"),
            "manual": tx(15, "ALFA LLC"),
            "no_orig": tx(16, "ALFA LLC", orig=False),
        }
        decide(t["only_fw"], mario, why_default)
        decide(t["same_all"], mario, why_default)
        allocate(t["same_all"], rfa)
        allocate(t["human_diff"], rfb)
        decide(t["human_only"], mario, why_default)
        allocate(t["human_only"], rfb)
        decide(t["auto_other"], mario, why_default)
        allocate(t["auto_other"], rfb, source="RULE", notes="written by another rule")
        decide(t["uncertain"], mario, why_default)
        allocate(t["uncertain"], None, source=None, status=m.ALLOCATION_PENDING_EVIDENCE)
        decide(t["split"], mario, why_default)
        half = t["split"].amount_minor // 2
        economic_allocation.set_allocations(s, financial_transaction_id=t["split"].id, specs=[
            economic_allocation.AllocationSpec(amount_minor=half, reporting_entity_id=rfa.id,
                                               status=m.ALLOCATION_NEEDS_OPERATOR, decision_source="HUMAN"),
            economic_allocation.AllocationSpec(amount_minor=t["split"].amount_minor - half, reporting_entity_id=rfb.id,
                                               status=m.ALLOCATION_NEEDS_OPERATOR, decision_source="HUMAN")])
        decide(t["complete"], mario, why_default)
        allocate(t["complete"], rfb, status=economic_allocation.COMPLETE, why=why_default)
        decide(t["manual"], publix, why_other, source="HUMAN")
        s.commit()
        ids = {k: v.id for k, v in t.items()}
        rfa_id, rfb_id = rfa.id, rfb.id
        why_default_id = why_default.id

    prompts: list[str] = []

    def stand_in(prompt: str) -> dict:
        prompts.append(prompt)
        if "Translate the rule into conditions" not in prompt:
            return {"items": []}
        rule = prompt.split("RULE:\n")[1].split("\n\nEXAMPLE")[0]
        if rule == RULE_NOREPLACE:
            return {**copy(FULL), "replace_existing": False}
        if rule == RULE_OTHER:
            return {"kind": "OTHER", "reason": "“Solo nei giorni festivi” cannot be expressed", "coverage": COVERAGE,
                    "unsupported": ["Solo nei giorni festivi"]}
        return copy(FULL)

    ai_client.generate_json = stand_in
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_fw", "password": "AiFwPass123!", "csrf_token": csrf})
    csrf = CSRF_RE.search(client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()).group(1)

    def preview(rule, **extra):
        data = {"csrf_token": csrf, "rule_text": rule, "origin_transaction_id": str(ids["none"]),
                "date_from": "2026-09-01", "date_to": "2026-09-30", "create_missing_who": "on"}
        data.update(extra)
        return client.post("/bank/ai-rules/preview", data=data, headers={"X-Requested-With": "fetch"}).get_json()

    def state():
        with SessionFactory() as s:
            out = {}
            for k, v in ids.items():
                allocations = economic_allocation.get_allocations(s, financial_transaction_id=v)
                out[k] = (s.get(m.FinancialTransaction, v).explanation_id,
                          tuple((a.reporting_entity_id, a.decision_source, a.status, a.notes) for a in allocations))
            return out

    # ------------------------------------------------------------ validation
    v = ai_rules.validate_interpretation
    with SessionFactory() as s:
        entities = ai_rules.EntityCatalog(s)
        ok_spec, ok_reason = v(copy(FULL), RULE, entities=entities)
        unknown = v({**copy(FULL), "for_whom": {**FOR_WHOM, "names": [{"name": "ALFA LLC", "entity": "RFZ"}]}},
                    RULE + " RFZ", entities=entities)
        inactive = v({**copy(FULL), "for_whom": {"mode": "fixed", "entity": "OLDCO"}}, RULE + " OLDCO",
                     entities=entities)
        not_written = v({**copy(FULL), "for_whom": {**FOR_WHOM, "marker": "BENEF:"}}, RULE, entities=entities)
        other = v({"kind": "OTHER", "reason": "For Whom cannot be expressed", "coverage": COVERAGE,
                   "unsupported": ["For Whom"]}, RULE, entities=entities)
        partial = v({**copy(FULL), "unsupported": ["Da confermare quando cambia For Whom"]}, RULE, entities=entities)
    check("1. a complete For Whom interpretation is valid (marker, names and entities from the rule, active entities)",
          ok_spec is not None and ok_spec["for_whom"] == FOR_WHOM and ok_spec["version"] == ai_rules.SPEC_VERSION, detail=str(ok_reason))
    check("2. an unknown entity, an inactive entity, a marker not written in the rule: the interpretation is invalid",
          unknown[0] is None and "not an active entity" in unknown[1] and inactive[0] is None
          and "not an active entity" in inactive[1] and not_written[0] is None and "not written" in not_written[1],
          detail=f"{unknown[1]} | {inactive[1]} | {not_written[1]}")
    check("3. an OTHER answer and an answer with an unsupported instruction stay blocked (no partial interpretation)",
          other[0] is None and partial[0] is None and "not supported" in partial[1])
    check("4. the name match: any case, leading spaces skipped, the complete name followed by data; a longer name or "
          "no marker is not a match",
          ai_rules.match_after_text("x ind name:   alfa  llc AN 12", FOR_WHOM)[0] == "RFA"
          and ai_rules.match_after_text("IND NAME:BETA SRL", FOR_WHOM)[0] == "RFB"
          and ai_rules.match_after_text("IND NAME:ALFA LLCX", FOR_WHOM)[0] is None
          and ai_rules.match_after_text("IND NAME:XALFA LLC", FOR_WHOM)[0] is None
          and ai_rules.match_after_text("ALFA LLC", FOR_WHOM)[0] is None)

    # ----------------------------------------------------------- the preview
    before = state()
    p = preview(RULE)
    items = {i["id"]: i for i in p.get("match_items", [])}
    by = {k: items.get(v) for k, v in ids.items()}
    check("5. the rule runs by code with For Whom (method CODE, 1 AI call), and the preview says it assigns For Whom",
          p.get("ok") and p.get("method") == "CODE" and p.get("ai_calls") == 1 and p.get("for_whom_rule"),
          detail=str(p.get("error")))
    check("6. no WHO extracted (no “ORIG CO NAME:”): the rule does not apply at all, For Whom included",
          ids["no_orig"] not in items)
    check("7. no For Whom yet: WHO, WHY and For Whom change, status → Da confermare; current and proposed For Whom shown",
          by["none"]["plan"] == "UPDATED" and by["none"]["proposed_for_whom"] == "RFA" and by["none"]["for_whom"] is None
          and "WHO, WHY and For Whom would change" in by["none"]["plan_note"]
          and "status → Da confermare" in by["none"]["plan_note"], detail=str(by["none"]))
    check("8. any case and leading spaces, name followed by other data → For Whom proposed",
          by["lower"]["proposed_for_whom"] == "RFA" and "For Whom" in by["lower"]["plan_note"], detail=str(by["lower"]))
    check("9. a longer name, no “IND NAME:”, another name: For Whom unchanged (WHO / WHY still change), the reason said",
          all(by[k]["proposed_for_whom"] is None and by[k]["plan"] == "UPDATED" and "For Whom would change" not in
              by[k]["plan_note"] and "For Whom unchanged" in by[k]["reason"] for k in ("longer", "missing", "other_name")),
          detail=str([by[k]["reason"] for k in ("longer", "missing", "other_name")]))
    check("10. only For Whom differs: UPDATED for For Whom alone, status → Da confermare",
          by["only_fw"]["plan"] == "UPDATED" and by["only_fw"]["plan_note"].startswith("For Whom would change")
          and "status → Da confermare" in by["only_fw"]["plan_note"] and by["only_fw"]["proposed_for_whom"] == "RFB",
          detail=str(by["only_fw"]))
    check("11. everything already as the rule says (For Whom chosen by a person, same entity): UNCHANGED",
          by["same_all"]["plan"] == "UNCHANGED" and by["same_all"]["for_whom"] == "RFA", detail=str(by["same_all"]))
    check("12. For Whom chosen by a person, different: WHO / WHY still change, For Whom kept and said so",
          by["human_diff"]["plan"] == "UPDATED" and "WHO and WHY would change" in by["human_diff"]["plan_note"]
          and "For Whom RFB chosen by a person: kept" in by["human_diff"]["plan_note"], detail=str(by["human_diff"]))
    check("13. only a For Whom chosen by a person would change: PROTECTED, reported separately",
          by["human_only"]["plan"] == "PROTECTED" and "chosen by a person" in by["human_only"]["plan_note"],
          detail=str(by["human_only"]))
    check("14. a For Whom written by another rule (automatic) is replaced when the rule replaces",
          by["auto_other"]["plan"] == "UPDATED" and by["auto_other"]["plan_note"].startswith("For Whom would change"),
          detail=str(by["auto_other"]))
    check("15. uncertain origin (pending evidence; a split): kept, PROTECTED with the reason",
          by["uncertain"]["plan"] == "PROTECTED" and "origin is uncertain" in by["uncertain"]["plan_note"]
          and by["split"]["plan"] == "PROTECTED" and "split" in by["split"]["plan_note"],
          detail=f"{by['uncertain']['plan_note']} | {by['split']['plan_note']}")
    check("16. an accounting-complete For Whom and a manual decision: PROTECTED",
          by["complete"]["plan"] == "PROTECTED" and "confirmed by a person" in by["complete"]["plan_note"]
          and by["manual"]["plan"] == "PROTECTED" and "manually" in by["manual"]["plan_note"])
    lines = p.get("interpretation_lines") or []
    check("17. the interpretation shows the For Whom assignment with the entities resolved, and the protections",
          any(x.startswith("FOR WHOM (decided on its own") and "RFA (existing entity, RE_RFA)" in x for x in lines)
          and ai_rules.PROTECTIONS_TEXT in lines, detail=str(lines))
    check("18. the preview writes nothing on movements (decisions and allocations)", state() == before)
    noreplace = {i["id"]: i for i in preview(RULE_NOREPLACE).get("match_items", [])}
    check("19. without “replace”: a For Whom written by another rule is a CONFLICT",
          noreplace[ids["auto_other"]]["plan"] == "CONFLICT"
          and "decided by another rule" in noreplace[ids["auto_other"]]["plan_note"])
    blocked = preview(RULE_OTHER)
    check("20. an OTHER interpretation blocks the preview (no partial execution)",
          not blocked.get("ok") and "Bloccata" in (blocked.get("error") or "") and not blocked.get("match_items"))

    # ------------------------------------------- applying (throwaway database)
    with SessionFactory() as s:
        saved = ai_rule_operations.save_rule(s, rule_id=None, rule_text=RULE, create_missing_who=True,
                                             apply_future=True, origin_transaction_id=ids["none"],
                                             account_id=None, generate=stand_in)
        s.commit()
        rule_id = saved.rule.id
    pa = preview(RULE, scope_all="on", rule_id=str(rule_id))
    with SessionFactory() as s:
        rule = s.get(m.BankAiRule, rule_id)
        application = ai_rule_operations.apply_rule(s, rule=rule, scope="ALL", selected_ids=None,
                                                    preview_id=pa.get("preview_id"), account_id=None)
        s.commit()
        app_items = {i.financial_transaction_id: i for i in application.items}
        current = {k: recognition.get_current_explanation(s, financial_transaction_id=v) for k, v in ids.items()}
        allocations = {k: economic_allocation.get_allocations(s, financial_transaction_id=v) for k, v in ids.items()}
        counts = (application.updated, application.unchanged, application.protected, application.conflicts,
                  application.errors)
    after = state()
    fw = allocations["none"][0] if allocations["none"] else None
    check("21. applied: For Whom written as ONE pending RULE allocation naming the AI Rule; decision Da confermare",
          fw is not None and fw.reporting_entity_id == rfa_id and fw.decision_source == "RULE"
          and fw.status == m.ALLOCATION_NEEDS_OPERATOR and (fw.notes or "").startswith(f"AI Rule #{rule_id} ")
          and current["none"].decision_status == "NEEDS_HUMAN_REVIEW", detail=str(counts))
    check("22. only For Whom changed: a new decision with the SAME WHO and WHY, now Da confermare; For Whom RFB",
          after["only_fw"][0] != before["only_fw"][0] and current["only_fw"].transaction_reason_id == why_default_id
          and current["only_fw"].decision_status == "NEEDS_HUMAN_REVIEW"
          and allocations["only_fw"][0].reporting_entity_id == rfb_id)
    check("23. nothing changed → untouched, status kept; person's For Whom kept; uncertain, split, complete and manual "
          "untouched",
          after["same_all"] == before["same_all"] and current["same_all"].decision_status == "AUTO_APPLIED"
          and after["human_diff"][1] == before["human_diff"][1] and after["human_diff"][0] != before["human_diff"][0]
          and all(after[k] == before[k] for k in ("human_only", "uncertain", "split", "complete", "manual", "no_orig")))
    check("24. the automatic For Whom of another rule is replaced (RFA, written by this AI Rule)",
          allocations["auto_other"][0].reporting_entity_id == rfa_id
          and allocations["auto_other"][0].notes.startswith(f"AI Rule #{rule_id} "))
    check("25. the application log keeps For Whom before / after",
          app_items[ids["only_fw"]].for_whom_before is None and app_items[ids["only_fw"]].for_whom_after == "RFB"
          and app_items[ids["auto_other"]].for_whom_before == "RFB"
          and app_items[ids["auto_other"]].for_whom_after == "RFA" and counts[-1] == 0, detail=str(counts))
    again = {i["id"]: i for i in preview(RULE, scope_all="on", rule_id=str(rule_id)).get("match_items", [])}
    check("26. after applying, the rule's own output is UNCHANGED on the next preview (status kept)",
          all(again[ids[k]]["plan"] == "UNCHANGED" for k in ("none", "only_fw", "auto_other", "lower")),
          detail=str({k: again[ids[k]]["plan_note"] for k in ("none", "only_fw", "auto_other")}))

    # ------------------------------------------------------------- the import
    with SessionFactory() as s:
        checking_id = s.get(m.FinancialTransaction, ids["none"]).payment_instrument_id
        new = m.FinancialTransaction(
            payment_instrument_id=checking_id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 9, 20),
            transaction_date=date(2026, 9, 20), description_original="ORIG CO NAME:Mario Rossi ORIG ID:77 IND NAME:beta srl",
            description_normalized="x", amount_minor=-3000, status="COMPLETED", duplicate_status="NONE",
            review_status="REQUIRES_REVIEW", accounting_status="CANONICAL", fingerprint="fw-new", classification="UNKNOWN")
        s.add(new)
        s.flush()
        context = ai_rule_operations.import_context(s)
        written = ai_rule_operations.apply_to_new_transaction(s, new, context)
        ai_rule_operations.finish_import(context)
        s.commit()
        new_alloc = economic_allocation.get_allocations(s, financial_transaction_id=new.id)
        new_decision = recognition.get_current_explanation(s, financial_transaction_id=new.id)
    check("27. at import, a rule for the future assigns For Whom too (RFB), with WHO, WHY and Da confermare",
          written and new_alloc and new_alloc[0].reporting_entity_id == rfb_id and new_alloc[0].decision_source == "RULE"
          and new_decision.decision_status == "NEEDS_HUMAN_REVIEW" and new_decision.transaction_reason_id == why_default_id)

    # ------------------------------- interpretations of the previous engine version
    with SessionFactory() as s:
        instruction = ai_rules.current_instruction(s)
        text = instruction.instructions if instruction and instruction.instructions else None
        valid_spec, _ = ai_rules.validate_interpretation(copy(FULL), RULE_OLD_VALID)
        for rule_text, spec, reason in ((RULE_OLD_BLOCKED, None, "no For Whom element (old engine)"),
                                        (RULE_OLD_VALID, json.dumps(valid_spec), None)):
            s.add(m.BankAiRuleInterpretation(
                cache_key=ai_rules.interpretation_key(rule_text, text, "structured-v3"), rule_text=rule_text,
                raw_answer="{}", spec=spec, rejection_reason=reason, provider="CLAUDE_CODE_SESSION", model="x"))
        s.commit()
        count_before = s.scalar(select(func.count(m.BankAiRuleInterpretation.id)))
    prompts.clear()
    old_blocked = preview(RULE_OLD_BLOCKED)
    reinterpreted = len(prompts)
    prompts.clear()
    old_valid = preview(RULE_OLD_VALID)
    with SessionFactory() as s:
        count_after = s.scalar(select(func.count(m.BankAiRuleInterpretation.id)))
    check("28. a BLOCKED interpretation of the previous engine is interpreted again (1 AI call) and now runs",
          old_blocked.get("ok") and old_blocked.get("ai_calls") == 1 and reinterpreted == 1
          and not old_blocked.get("interpretation_reused"), detail=str(old_blocked.get("error")))
    check("29. a VALID interpretation of the previous engine is reused — no AI call",
          old_valid.get("ok") and old_valid.get("ai_calls") == 0 and not prompts and old_valid.get("interpretation_reused")
          and count_after == count_before + 1)

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
