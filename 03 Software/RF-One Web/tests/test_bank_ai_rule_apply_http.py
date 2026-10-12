"""Bank > AI Rules — Save Draft, Salva, Salva e Applica, Per il futuro (BANK_AI_RULES_006).

On a throwaway database, over HTTP (and the real import service). The AI
provider is replaced INSIDE THIS TEST ONLY by a stand-in that interprets the
rules; the application itself never simulates an answer.

* Save Draft keeps a draft, never an operative rule, and changes nothing;
* Salva makes the rule operative (a version with its validated
  interpretation) and changes no movement; saving the same text again adds no
  version and needs no AI call;
* Salva e Applica needs a scope, and a completed preview of the same text,
  scope, selection and option — otherwise nothing at all is written;
* applied to the SELECTED movements only those change; applied to ALL, every
  matching movement is planned and logged: updated, unchanged, protected
  (manual, Standard), conflicts (a different value decided elsewhere, another
  AI rule with a different value) — only the fields the rule names change;
* "Crea WHO mancanti" creates the WHO needed, once; a repeated application
  changes nothing and writes no new decision;
* "Per il futuro": the import applies the rule to new movements and logs it;
  two future rules with incompatible values are a conflict, none applied; a
  disabled rule is not applied; a rule the code cannot execute is refused;
* editing an operative rule through Save Draft keeps its current version;
* traditional rules, Standards and unrelated classifications are unchanged.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rule_apply_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rule-apply-secret"

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
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.bank_reconciliation import service as bank_service  # noqa: E402
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
SALON = "Ogni movimento con descrizione che contiene “salon test” è WHO \"SALON TEST\" e WHY \"{why}\"."
SALON_OTHER = "Ogni movimento con descrizione che contiene “salon test” è WHO \"OTHER SALON\"."
ZELLE = ("Se la descrizione comincia con “Zelle payment to” e contiene “JPM”, il WHO è il testo tra “Zelle payment to” "
         "e “JPM”. Non modificare il WHY.")
JUDGED = "Classifica come spesa personale gli acquisti che sembrano personali."


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_apply", display_name="AI Apply",
                                       password="AiApply123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_apply").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF Apply, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        entity = m.ReportingEntity(code="RE_APPLY", name="RF Apply", entity_type="LEGAL", legal_entity_id=llc.id,
                                   status="ACTIVE")
        checking = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT",
                                       display_name="Apply Checking", institution="CHASE", last_four="2001",
                                       currency="USD")
        card = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="CREDIT_CARD", display_name="Chase Card 1057",
                                   institution="CHASE", last_four="1057", currency="USD")
        s.add_all([entity, checking, card])
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        salon_who = m.BankOccurrence(canonical_name="SALON TEST", occurrence_type_id=counterparty.id, status="ACTIVE")
        publix = m.BankOccurrence(canonical_name="PUBLIX", occurrence_type_id=counterparty.id, status="ACTIVE")
        s.add_all([salon_who, publix])
        s.flush()
        whys = s.scalars(select(m.BankTransactionReason).where(
            m.BankTransactionReason.status == "ACTIVE",
            m.BankTransactionReason.accounting_classification_id.is_not(None)).order_by(m.BankTransactionReason.id)).all()
        why_x, why_y = whys[0], whys[1]
        standard = m.BankReconciliationStandard(
            match_type="CONTAINS_TEXT", normalized_pattern="SALON TEST STD", match_field="DESCRIPTION",
            occurrence_id=publix.id, transaction_reason_id=why_x.id,
            accounting_classification_id=why_x.accounting_classification_id, reporting_entity_id=entity.id,
            status="ACTIVE", approved_at=datetime.now(timezone.utc))
        s.add(standard)
        s.flush()
        seq = [0]

        def tx(day, amount, description):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=day,
                transaction_date=day, description_original=description, description_normalized=description,
                amount_minor=amount, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"apply-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            return t

        def decide(t, who, why, source="RULE", standard_id=None):
            extra = (dict(reconciliation_standard_id=standard_id, accounting_destination_source=m.DESTINATION_SOURCE_STANDARD,
                          accounting_classification_id=why.accounting_classification_id) if standard_id else {})
            recognition._create_decision_row(
                s, t, occurrence_id=who.id if who else None, transaction_reason_id=why.id if why else None,
                recognition_rule_id=None, decision_source=source, decision_status="NEEDS_HUMAN_REVIEW",
                confidence=None, explanation_notes="test setup", **extra)

        t = {
            "free": tx(date(2026, 9, 2), -1000, "SALON TEST ORLANDO"),
            "free2": tx(date(2026, 9, 3), -1100, "SALON TEST WINTER PARK"),
            "human": tx(date(2026, 9, 4), -1200, "SALON TEST HUMAN"),
            "standard": tx(date(2026, 9, 5), -1300, "SALON TEST STD"),
            "conflict": tx(date(2026, 9, 6), -1400, "SALON TEST OTHER"),
            "same": tx(date(2026, 9, 7), -1500, "SALON TEST SAME"),
            "why_only": tx(date(2026, 9, 8), -1600, "SALON TEST WHY MISSING"),
            "zelle_1": tx(date(2026, 9, 9), -1700, "Zelle payment to New  Person JPM99abc"),
            "zelle_2": tx(date(2026, 9, 10), -1800, "zelle payment to new person JPM99xyz"),
            "unrelated": tx(date(2026, 9, 11), -1900, "UNRELATED VENDOR"),
        }
        decide(t["human"], publix, why_y, source="HUMAN")
        decide(t["standard"], publix, why_x, standard_id=standard.id)
        decide(t["conflict"], publix, None)
        decide(t["same"], salon_who, why_x)
        decide(t["why_only"], salon_who, None)
        decide(t["zelle_1"], None, why_y)
        decide(t["zelle_2"], None, why_y)
        decide(t["unrelated"], publix, why_y)
        s.commit()
        ids = {k: v.id for k, v in t.items()}
        why_x_name, why_y_name, why_y_id, why_x_id = why_x.name, why_y.name, why_y.id, why_x.id
        salon_id, publix_id = salon_who.id, publix.id
    salon_rule = SALON.format(why=why_x_name)

    def interpretation(prompt: str) -> dict:
        rule = prompt.split("RULE:\n")[1].split("\n\nEXAMPLE")[0]
        if rule.startswith("Ogni movimento con descrizione che contiene “salon test” è WHO \"SALON TEST\""):
            return {"kind": "STRUCTURED", "conditions": [{"field": "description", "op": "contains", "value": "salon test"}],
                    "who": {"mode": "fixed", "name": "SALON TEST"}, "why": {"mode": "fixed", "name": why_x_name}}
        if rule.startswith("Ogni movimento con descrizione che contiene “salon test” è WHO \"OTHER SALON\""):
            return {"kind": "STRUCTURED", "conditions": [{"field": "description", "op": "contains", "value": "salon test"}],
                    "who": {"mode": "fixed", "name": "OTHER SALON"}, "why": None}
        if rule.startswith("Se la descrizione comincia con “Zelle payment to”"):
            return {"kind": "STRUCTURED", "conditions": [{"field": "description", "op": "starts_with",
                                                          "value": "Zelle payment to"}],
                    "who": {"mode": "between", "start": "Zelle payment to", "end": "JPM"}, "why": None}
        return {"kind": "OTHER", "reason": "giudizio sul singolo movimento"}

    calls = {"n": 0}

    def stand_in(prompt: str) -> dict:
        calls["n"] += 1
        if "Translate the rule into conditions" in prompt:
            # structured-v3 (BANK_AI_RULES_008): every interpretation accounts for the rule's instructions.
            return {"coverage": [{"instruction": "the whole rule", "represented_by": "conditions, WHO and WHY"}],
                    **interpretation(prompt)}
        return {"items": []}

    ai_client.generate_json = stand_in

    def state():
        with SessionFactory() as s:
            decisions = {tid: (e.occurrence_id, e.transaction_reason_id, e.decision_source) for tid, e in (
                (tid, recognition.get_current_explanation(s, financial_transaction_id=tid)) for tid in ids.values()) if e}
            return dict(
                decisions=decisions,
                explanations=s.scalar(select(func.count(m.BankTransactionExplanation.id))),
                rules=s.scalar(select(func.count(m.BankRecognitionRule.id))),
                standards=s.scalar(select(func.count(m.BankReconciliationStandard.id))),
                general=s.scalar(select(func.count(m.BankGeneralRule.id))),
                whys=s.scalar(select(func.count(m.BankTransactionReason.id))),
                who_names=sorted(s.scalars(select(m.BankOccurrence.canonical_name))),
                ai_rules=s.scalar(select(func.count(m.BankAiRule.id))))

    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_apply", "password": "AiApply123!", "csrf_token": csrf})
    page = client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()
    csrf = CSRF_RE.search(page).group(1)
    check("1. the window has Save Draft, Salva and Salva e Applica (disabled until a scope is chosen), the three scopes "
          "with none preselected, and row selection",
          "Save Draft" in page and 'id="ai-rule-save"' in page
          and re.search(r'<button type="button" id="ai-rule-save-apply" disabled>Salva e Applica</button>', page)
          and all(f'name="{n}" id' in page for n in ("scope_all", "scope_selected", "scope_future"))
          and not re.search(r'name="scope_(all|selected|future)"[^>]*checked', page)
          and page.count('class="ai-rule-select"') == len(ids) and "Seleziona tutte nel periodo" in page)

    def post(path, **data):
        form = {"csrf_token": csrf, "origin_transaction_id": str(ids["free"]), "date_from": "2026-09-01",
                "date_to": "2026-09-30", "rule_text": salon_rule}
        form.update({k: v for k, v in data.items() if v is not None})
        response = client.post(path, data=form, headers={"X-Requested-With": "fetch"})
        return response.status_code, response.get_json()

    start = state()
    status, draft = post("/bank/ai-rules/drafts")
    check("2. Save Draft keeps a draft only: no operative rule, no movement changed",
          status == 200 and draft["ok"] and state() == start)

    calls["n"] = 0
    status, saved = post("/bank/ai-rules/save")
    after_save = state()
    check("3. Salva makes the rule operative (v1, executed by code) and changes no movement",
          status == 200 and saved["ok"] and saved["version_no"] == 1 and saved["method"] == "CODE"
          and not saved["apply_future"] and after_save["decisions"] == start["decisions"]
          and after_save["ai_rules"] == 1 and calls["n"] == 1, detail=str(saved))
    rule_id = saved["rule_id"]
    calls["n"] = 0
    status, again = post("/bank/ai-rules/save", rule_id=str(rule_id))
    check("3b. Salva again with the same text: same version, no AI call (interpretation saved with the version)",
          again["version_no"] == 1 and not again["new_version"] and calls["n"] == 0)

    status, no_scope = post("/bank/ai-rules/save-apply", rule_id=str(rule_id))
    status2, no_preview = post("/bank/ai-rules/save-apply", rule_id=str(rule_id), scope_all="on")
    check("4. Salva e Applica without a scope is refused; with a scope but no preview it asks for one — nothing written",
          status == 400 and status2 == 409 and no_preview["needs_preview"] and state() == after_save)

    # ---------------------------------------------------------------- SELECTED
    selected = f"{ids['free']},{ids['human']}"
    status, prev_sel = post("/bank/ai-rules/preview", rule_id=str(rule_id), scope_selected="on", selected_ids=selected)
    check("5. the preview of the SELECTED movements plans exactly them: 1 update, 1 protected",
          prev_sel["ok"] and prev_sel["scope"] == "SELECTED" and prev_sel["examined"] == 2
          and prev_sel["planned_updates"] == 1 and prev_sel["protected"] == 1, detail=str(prev_sel))
    status, stale = post("/bank/ai-rules/save-apply", rule_id=str(rule_id), scope_all="on",
                         preview_id=str(prev_sel["preview_id"]))
    check("5b. a preview of another scope cannot be used to apply", status == 409 and state() == after_save)
    status, applied = post("/bank/ai-rules/save-apply", rule_id=str(rule_id), scope_selected="on", selected_ids=selected,
                           preview_id=str(prev_sel["preview_id"]))
    after_sel = state()
    a = applied["application"]
    check("6. applied to the selected movements only: 1 updated, 1 protected, nothing else touched",
          applied["ok"] and a["updated"] == 1 and a["protected"] == 1 and a["examined"] == 2
          and after_sel["decisions"][ids["free"]] == (salon_id, why_x_id, "RULE")
          and after_sel["decisions"][ids["human"]] == start["decisions"][ids["human"]]
          and all(after_sel["decisions"].get(ids[k]) == start["decisions"].get(ids[k])
                  for k in ("free2", "standard", "conflict", "same", "why_only", "unrelated")), detail=str(a))

    # --------------------------------------------------------------------- ALL
    status, prev_all = post("/bank/ai-rules/preview", rule_id=str(rule_id), scope_all="on")
    plans = {i["id"]: i["plan"] for i in prev_all["match_items"]}
    check("7. the preview of ALL plans every match: updated, unchanged, protected (manual, Standard), conflict",
          prev_all["scope"] == "ALL" and plans == {
              ids["free"]: "UNCHANGED", ids["free2"]: "UPDATED", ids["human"]: "PROTECTED",
              ids["standard"]: "PROTECTED", ids["conflict"]: "CONFLICT", ids["same"]: "UNCHANGED",
              ids["why_only"]: "UPDATED"}, detail=str(plans))
    status, applied_all = post("/bank/ai-rules/save-apply", rule_id=str(rule_id), scope_all="on",
                               preview_id=str(prev_all["preview_id"]))
    after_all = state()
    b = applied_all["application"]
    check("8. applied to ALL: 2 updated, 2 unchanged, 2 protected, 1 conflict — logged",
          (b["updated"], b["unchanged"], b["protected"], b["conflicts"], b["errors"]) == (2, 2, 2, 1, 0), detail=str(b))
    check("8b. only the fields the rule names: a WHO already right keeps its WHO and gets the WHY",
          after_all["decisions"][ids["why_only"]][:2] == (salon_id, why_x_id)
          and after_all["decisions"][ids["free2"]][:2] == (salon_id, why_x_id))
    check("8c. manual, Standard and conflicting movements are untouched; unrelated ones too",
          all(after_all["decisions"][ids[k]] == start["decisions"][ids[k]]
              for k in ("human", "standard", "conflict", "unrelated")))
    with SessionFactory() as s:
        items = {i.financial_transaction_id: i for i in s.scalars(select(m.BankAiRuleApplicationItem).where(
            m.BankAiRuleApplicationItem.application_id == b["application_id"]))}
        logged = items[ids["why_only"]]
        log_ok = (logged.outcome == "UPDATED" and logged.who_before == "SALON TEST" and logged.why_before is None
                  and logged.who_after == "SALON TEST" and logged.why_after == why_x_name
                  and items[ids["conflict"]].outcome == "CONFLICT" and "PUBLIX" in items[ids["conflict"]].note)
        app_row = s.get(m.BankAiRuleApplication, b["application_id"])
        app_ok = app_row.rule_id == rule_id and app_row.version_id is not None and app_row.mode == "EXISTING_ALL"
    check("8d. the log keeps rule, version, scope, and WHO/WHY before and after for each movement", log_ok and app_ok)

    explanations_before = state()["explanations"]
    status, prev_again = post("/bank/ai-rules/preview", rule_id=str(rule_id), scope_all="on")
    status, applied_again = post("/bank/ai-rules/save-apply", rule_id=str(rule_id), scope_all="on",
                                 preview_id=str(prev_again["preview_id"]))
    check("9. applying again changes nothing and writes no new decision",
          applied_again["application"]["updated"] == 0 and state()["explanations"] == explanations_before)

    # ------------------------------------------------ another AI rule conflicts
    status, other = post("/bank/ai-rules/save", rule_text=SALON_OTHER)
    status, prev_conflict = post("/bank/ai-rules/preview", rule_id=str(rule_id), scope_all="on")
    notes = [i["plan_note"] for i in prev_conflict["match_items"] if i["id"] == ids["free2"]]
    check("10. another active AI rule assigning a different WHO is a conflict, never settled by order",
          notes and "AI rule #" in notes[0] and "OTHER SALON" in notes[0] and prev_conflict["conflicts"] >= 1, detail=str(notes))
    client.post(f"/bank/ai-rules/rules/{other['rule_id']}/status", data={"csrf_token": csrf, "active": "0"})

    # ---------------------------------------------------- Zelle + missing WHO
    status, prev_z = post("/bank/ai-rules/preview", rule_text=ZELLE, origin_transaction_id=str(ids["zelle_1"]),
                          scope_all="on", create_missing_who="on")
    status, z = post("/bank/ai-rules/save-apply", rule_text=ZELLE, origin_transaction_id=str(ids["zelle_1"]),
                     scope_all="on", create_missing_who="on", preview_id=str(prev_z["preview_id"]))
    after_z = state()
    with SessionFactory() as s:
        new_person = s.scalars(select(m.BankOccurrence).where(m.BankOccurrence.canonical_name == "NEW PERSON")).all()
    check("11. Crea WHO mancanti: the WHO is created once and assigned; the WHY is kept (WHO-only rule)",
          z["ok"] and z["application"]["updated"] == 2 and z["application"]["who_created"] == ["NEW PERSON"]
          and len(new_person) == 1 and after_z["decisions"][ids["zelle_1"]][:2] == (new_person[0].id, why_y_id)
          and after_z["decisions"][ids["zelle_2"]][:2] == (new_person[0].id, why_y_id), detail=str(z.get("application")))
    status, prev_z2 = post("/bank/ai-rules/preview", rule_text=ZELLE, origin_transaction_id=str(ids["zelle_1"]),
                           scope_all="on", create_missing_who="on", rule_id=str(z["rule_id"]))
    status, z2 = post("/bank/ai-rules/save-apply", rule_text=ZELLE, origin_transaction_id=str(ids["zelle_1"]),
                      scope_all="on", create_missing_who="on", rule_id=str(z["rule_id"]),
                      preview_id=str(prev_z2["preview_id"]))
    check("11b. again: no WHO duplicated, nothing updated",
          z2["application"]["updated"] == 0 and state()["who_names"].count("NEW PERSON") == 1)

    # ------------------------------------------------------------- Per il futuro
    status, judged = post("/bank/ai-rules/save", rule_text=JUDGED, scope_future="on")
    # BANK_AI_RULES_009: a rule the code cannot execute is never operative (with or without “Per il futuro”).
    check("12. a rule the code cannot execute is refused (never operative, so never “Per il futuro”)",
          status == 400 and "non è valida" in judged["error"])
    status, future = post("/bank/ai-rules/save-apply", rule_id=str(rule_id), scope_future="on")
    check("12b. Salva e Applica with only “Per il futuro”: saved and enabled, history untouched",
          future["ok"] and future["apply_future"] and not future["applied"] and state()["decisions"] == after_z["decisions"])

    def import_rows(name, rows_csv):
        with SessionFactory() as s:
            result = bank_service.import_csv(
                s, file_bytes=("Card,Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n" + rows_csv)
                .encode("utf-8"), original_file_name=name, uploaded_by_account_id=None)
            s.commit()
            new = s.scalars(select(m.FinancialTransaction).where(
                m.FinancialTransaction.import_batch_id == result.batch.id)).all()
            out = {}
            for txn in new:
                e = recognition.get_current_explanation(s, financial_transaction_id=txn.id)
                out[txn.description_original] = (e.occurrence_id, e.transaction_reason_id) if e else None
            apps = s.scalars(select(m.BankAiRuleApplication).where(
                m.BankAiRuleApplication.import_batch_id == result.batch.id)).all()
            return out, [(a.rule_id, a.mode, a.updated, a.conflicts) for a in apps]

    imported, apps = import_rows("chase1057_future.csv",
                                 "1057,09/20/2026,09/21/2026,SALON TEST NEW ONE,Shopping,Sale,-25.00,\n"
                                 "1057,09/20/2026,09/21/2026,OTHER SHOP,Shopping,Sale,-10.00,\n")
    check("13. a rule “Per il futuro” is applied to new imported movements, and logged as IMPORT",
          imported["SALON TEST NEW ONE"] == (salon_id, why_x_id) and imported["OTHER SHOP"] != (salon_id, why_x_id)
          and apps == [(rule_id, "IMPORT", 1, 0)], detail=f"{imported} {apps}")

    client.post(f"/bank/ai-rules/rules/{other['rule_id']}/status", data={"csrf_token": csrf, "active": "1"})
    post("/bank/ai-rules/save", rule_text=SALON_OTHER, rule_id=str(other["rule_id"]), scope_future="on")
    imported, apps = import_rows("chase1057_conflict.csv",
                                 "1057,09/22/2026,09/23/2026,SALON TEST CONFLICT,Shopping,Sale,-26.00,\n")
    check("14. two future rules with incompatible WHO: a conflict for both, none applied",
          (imported["SALON TEST CONFLICT"] is None or imported["SALON TEST CONFLICT"][0] != salon_id)
          and sorted(apps) == sorted([(rule_id, "IMPORT", 0, 1), (other["rule_id"], "IMPORT", 0, 1)]),
          detail=f"{imported} {apps}")
    client.post(f"/bank/ai-rules/rules/{other['rule_id']}/status", data={"csrf_token": csrf, "active": "0"})
    client.post(f"/bank/ai-rules/rules/{rule_id}/status", data={"csrf_token": csrf, "active": "0"})
    imported, apps = import_rows("chase1057_disabled.csv",
                                 "1057,09/24/2026,09/25/2026,SALON TEST DISABLED,Shopping,Sale,-27.00,\n")
    check("15. a disabled rule is not applied at import", apps == [] and
          (imported["SALON TEST DISABLED"] is None or imported["SALON TEST DISABLED"][0] != salon_id), detail=str(imported))

    # ------------------------------------------------- editing an operative rule
    with SessionFactory() as s:
        versions_before = [(v.version_no, v.rule_text) for v in s.get(m.BankAiRule, rule_id).versions]
    status, edit_draft = post("/bank/ai-rules/drafts", rule_id=str(rule_id), rule_text=salon_rule + " Modificata.")
    with SessionFactory() as s:
        rule = s.get(m.BankAiRule, rule_id)
        versions_after = [(v.version_no, v.rule_text) for v in rule.versions]
        draft_row = s.get(m.BankAiRuleDraft, edit_draft["draft_id"])
        draft_ok = draft_row.ai_rule_id == rule_id
    check("16. Save Draft on an operative rule saves a draft of the change; the current version is unchanged",
          edit_draft["ok"] and draft_ok and versions_after == versions_before)
    page = client.get("/bank/ai-rules").data.decode()
    reopened = client.get(f"/bank/ai-rules/rules/{rule_id}").get_json()
    check("17. the operative rules are listed with status and “Per il futuro”, and reopen with their text",
          f'data-rule-id="{rule_id}"' in page and "Disabled" in page and "ai-rule-operative-open" in page
          and reopened["rule_text"] == salon_rule and reopened["status"] == "INACTIVE" and reopened["apply_future"])

    end = state()
    check("18. traditional rules, Standards, WHY and General Rules are unchanged; only NEW PERSON was added as WHO",
          (end["rules"], end["standards"], end["whys"], end["general"]) ==
          (start["rules"], start["standards"], start["whys"], start["general"])
          and sorted(set(end["who_names"]) - set(start["who_names"])) == ["NEW PERSON"])

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
