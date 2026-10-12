"""Bank > AI Rules — natural-language rules previewed on a whole period
(BANK_AI_RULES_001/002; deterministic rules and "Crea WHO mancanti" of
BANK_AI_RULES_003; WHO/WHY pick lists of 004; general structured rules,
reused interpretations and throttling of 005).

On a throwaway database, over HTTP. The AI provider is replaced INSIDE THIS
TEST ONLY by a stand-in that answers from the prompt it receives; the
application itself never simulates an answer.

* AI Rules sits in the Bank menu next to Rules; the page lists every in-scope
  movement of the period, each with an "AI Rules" button, and the window
  lists every active WHO and every WHY;
* the AI interprets a rule ONCE into a structure (conditions + assignments);
  RF-One validates it (supported elements only, every text copied from the
  rule), resolves WHO/WHY in the catalogs and executes it by code on every
  movement — no movement is sent to the AI; the interpretation is reused while
  the rule text and the general instructions are unchanged;
* a structure that cannot be verified is not executed: the AI then judges
  each movement, in batches, never truncated; throttling is retried with
  progressive waits; batches that succeeded are kept and not asked again; an
  incomplete preview is FAILED, never shown as complete;
* "Crea WHO mancanti" / "Inserisci nuovi WHO in elenco": missing WHO created
  once, existing and merged names reused; drafts keep origin and option;
* nothing is written to movements, decisions, allocations, rules or Standards.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import threading
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ai_rules_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-ai-rules-secret"

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
from rfone_data_store.bank_reconciliation import row_reconciliation  # noqa: E402
from rfone_data_store.bank_reconciliation import who_recognition  # noqa: E402
from rfone_data_store.bank_reconciliation import why_catalog  # noqa: E402
from rfone_data_store.selection.parsing import ai_client  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
MOVE_RE = re.compile(r"^(T\d+) \| .*\| Description: (.*)$", re.M)
INTERPRET = "Translate the rule into conditions"
FILLERS = 90
PUBLIX_RULE = "Ogni acquisto Publix è WHO PUBLIX con il suo WHY abituale."
ZELLE_RULE = ("Se la descrizione comincia con “Zelle payment to” e contiene successivamente “JPM”, estrai come WHO "
              "tutto il testo tra “Zelle payment to” e “JPM”, eliminando gli spazi iniziali e finali e convertendolo "
              "in maiuscolo. Non modificare il WHY.")
SALON_RULE = ("Se la descrizione contiene “bonne vie salon”, senza distinzione tra maiuscole e minuscole, e la carta è "
              "Personal, assegna WHO \"BONNE VIE SALON\" e WHY \"Owner Personal — Other\".")
ZELLE = {
    "giovanna_1": "Zelle payment to Giovanna Wine Rep JPM99cy6r3de",
    "giovanna_2": "Zelle payment to Giovanna Wine Rep JPM99cwmvmfy",
    "foster": "zelle PAYMENT TO   Foster   King JPM99cwlqdgg",
    "bbc": "Zelle payment to BBC Wine JPM99cwepgri",
    "numeric": "Zelle payment to Lonnie Dunston 30817717579",
    "elsewhere": "Online transfer Zelle payment to Someone JPM99aaaa",
    "merged": "Zelle payment to Merged Vendor JPM99mmmmm",
}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="ai_rules", display_name="AI Rules",
                                       password="AiRules123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="ai_rules").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        llc = m.LegalEntity(legal_name="RF Test, LLC", status="ACTIVE")
        s.add(llc)
        s.flush()
        owners = m.ReportingEntity(code="RE_OWNERS", name="Owners - Personal", entity_type="PERSONAL", status="ACTIVE")
        s.add(owners)
        s.flush()
        checking = m.PaymentInstrument(legal_entity_id=llc.id, instrument_type="BANK_ACCOUNT", display_name="Test Checking",
                                       institution="CHASE", last_four="1001", currency="USD")
        personal = m.PaymentInstrument(owner_reporting_entity_id=owners.id, instrument_type="BANK_ACCOUNT",
                                       display_name="Owner Checking", institution="CHASE", last_four="1002", currency="USD")
        s.add_all([checking, personal])
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        publix = m.BankOccurrence(canonical_name="PUBLIX", occurrence_type_id=counterparty.id, status="ACTIVE")
        bbc = m.BankOccurrence(canonical_name="BBC  WINE", occurrence_type_id=counterparty.id, status="ACTIVE")
        giovanna = m.BankOccurrence(canonical_name="GIOVANNA", occurrence_type_id=counterparty.id, status="ACTIVE")
        salon = m.BankOccurrence(canonical_name="BONNE VIE SALON", occurrence_type_id=counterparty.id, status="ACTIVE")
        # A WHO merged into another by a person: its name is an alias of the
        # surviving WHO and must never be created again (GIOVANNA WINE REP case).
        merged_old = m.BankOccurrence(canonical_name="MERGED VENDOR", occurrence_type_id=counterparty.id, status="INACTIVE")
        main_vendor = m.BankOccurrence(canonical_name="MAIN VENDOR", occurrence_type_id=counterparty.id, status="ACTIVE")
        s.add_all([publix, bbc, giovanna, salon, merged_old, main_vendor])
        s.flush()
        s.add(m.BankOccurrenceAlias(occurrence_id=main_vendor.id, alias_text="MERGED VENDOR",
                                    alias_key=who_recognition.who_key("MERGED VENDOR"),
                                    source_family="MERGED_WHO_NAME", source="HUMAN"))
        s.flush()
        why = s.scalars(select(m.BankTransactionReason).where(
            m.BankTransactionReason.status == "ACTIVE",
            m.BankTransactionReason.accounting_classification_id.is_not(None)).order_by(m.BankTransactionReason.id)).first()
        personal_other = s.scalars(select(m.BankTransactionReason).where(
            m.BankTransactionReason.code == "OWNER_PERSONAL_OTHER")).one()
        why_catalog.associate(s, occurrence_id=publix.id, transaction_reason_id=why.id, source="HUMAN")
        seq = [0]

        def tx(day, amount, description, instrument=checking):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=instrument.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=day,
                transaction_date=day, description_original=description, description_normalized=description,
                amount_minor=amount, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"ai-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            return t

        origin = tx(date(2026, 9, 3), -4512, "PUBLIX #1234 ORLANDO")
        classified = tx(date(2026, 9, 9), -2000, "PUBLIX ALREADY DONE")
        late = tx(date(2026, 9, 28), -3100, "PUBLIX CARD 4147202212345678")
        tx(date(2026, 9, 7), -1500, "MYSTERY PAYMENT")
        zelle = {key: tx(date(2026, 9, 10 + i), -5000 - i, text) for i, (key, text) in enumerate(ZELLE.items())}
        salon_personal = tx(date(2026, 9, 4), -6500, "BONNE VIE SALON ORLANDO FL", personal)
        salon_lower = tx(date(2026, 9, 18), -4200, "Square *Bonne Vie Salon", personal)
        salon_company = tx(date(2026, 9, 19), -3900, "BONNE VIE SALON ORLANDO FL", checking)
        for i in range(FILLERS):
            tx(date(2026, 9, 1 + i % 28), -100 - i, f"OTHER VENDOR {i:03d}")
        august = tx(date(2026, 8, 20), -3000, "AUGUST PUBLIX")
        row_reconciliation.record_who(s, transaction_id=classified.id, occurrence_id=publix.id, reason_id=why.id,
                                      account_id=operator.id)
        s.commit()
        ids = dict(origin=origin.id, classified=classified.id, late=late.id, august=august.id,
                   salon_personal=salon_personal.id, salon_lower=salon_lower.id, salon_company=salon_company.id,
                   **{f"z_{k}": t.id for k, t in zelle.items()})
        why_code, why_name = why.code, why.name
        personal_other_name = personal_other.name
    september_count = 4 + len(ZELLE) + 3 + FILLERS

    def facts():
        with SessionFactory() as s:
            return [s.scalar(select(func.count(model.id))) for model in (
                m.FinancialTransaction, m.BankTransactionExplanation, m.BankTransactionAllocation,
                m.BankTransactionReason, m.BankRecognitionRule, m.BankGeneralRule, m.BankReconciliationStandard,
                m.BankWhoRecognition, m.BankOccurrenceReasonAssociation)] + [sorted(s.execute(select(
                    m.FinancialTransaction.id, m.FinancialTransaction.explanation_id)).all())]

    def who_names():
        with SessionFactory() as s:
            return sorted(s.scalars(select(m.BankOccurrence.canonical_name)))

    before, whos_before = facts(), who_names()
    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "ai_rules", "password": "AiRules123!", "csrf_token": csrf})

    # BANK_RULES_RESET_001 — the old Rules page is gone; AI Rules follows Source.
    rules_page = client.get("/bank/sources").data.decode()
    tabs = re.findall(r'class="module-tab[^"]*"\s+href="([^"]+)"', rules_page)
    check("1. AI Rules is in the Bank menu right after Source (no Rules tab)",
          "/bank/ai-rules" in tabs and tabs.index("/bank/ai-rules") == tabs.index("/bank/sources") + 1
          and "/bank/classification" not in tabs,
          detail=str(tabs))
    page = client.get("/bank/ai-rules?date_from=2026-09-01&date_to=2026-09-30").data.decode()
    csrf = CSRF_RE.search(page).group(1)
    check("2. the page lists every movement of the period, classified or not, and nothing outside it",
          f'data-period-count="{september_count}"' in page and "PUBLIX ALREADY DONE" in page
          and "MYSTERY PAYMENT" in page and "AUGUST PUBLIX" not in page)
    check("2b. each movement has an AI Rules button carrying its data and current WHO/WHY",
          page.count('class="btn-secondary ai-rule-open"') == september_count
          and re.search(r'ai-rule-open" data-transaction=\'[^\']*&#34;who&#34;: &#34;PUBLIX&#34;', page) is not None)
    check("2c. the window has Preview, Save Draft, Crea WHO mancanti and Inserisci nuovi WHO in elenco",
          'id="ai-rule-modal"' in page and 'id="ai-rule-preview-button"' in page and "Save Draft" in page
          and "Crea WHO mancanti" in page and "Inserisci nuovi WHO in elenco" in page and 'id="ai-rule-stale"' in page)
    who_picks = re.findall(r'class="ai-rule-pick" role="option" data-kind="WHO" data-name="([^"]+)"', page)
    why_picks = re.findall(r'class="ai-rule-pick" role="option" data-kind="WHY" data-name="([^"]+)"', page)
    with SessionFactory() as s:
        active_whos = sorted(s.scalars(select(m.BankOccurrence.canonical_name)
                                       .where(m.BankOccurrence.status == "ACTIVE")), key=str.casefold)
        active_whys = sorted(s.scalars(select(m.BankTransactionReason.name)
                                       .where(m.BankTransactionReason.status == "ACTIVE")), key=str.casefold)
    check("2d. the window lists every active WHO and every WHY, exact names, alphabetical, each searchable",
          who_picks == active_whos and "MERGED VENDOR" not in who_picks and "MAIN VENDOR" in who_picks
          and [n.replace("&amp;", "&").replace("&#39;", "'") for n in why_picks] == active_whys
          and 'id="ai-rule-who-search"' in page and 'id="ai-rule-why-search"' in page,
          detail=f"{len(who_picks)} WHO / {len(why_picks)} WHY")

    prompts: list[str] = []
    lock = threading.Lock()

    def interpretation_of(prompt: str) -> dict:
        rule = prompt.split("RULE:\n")[1].split("\n\nEXAMPLE")[0]
        if rule.startswith("Se la descrizione comincia con “Zelle payment to”"):
            return {"kind": "STRUCTURED", "conditions": [{"field": "description", "op": "starts_with",
                                                          "value": "Zelle payment to"}],
                    "who": {"mode": "between", "start": "Zelle payment to", "end": "JPM"}, "why": None}
        if rule.startswith("Se la descrizione contiene “bonne vie salon”"):
            return {"kind": "STRUCTURED",
                    "conditions": [{"field": "description", "op": "contains", "value": "bonne vie salon"},
                                   {"field": "source_class", "op": "is", "value": "personal"}],
                    "who": {"mode": "fixed", "name": "BONNE VIE SALON"},
                    "why": {"mode": "fixed", "name": "Owner Personal — Other"}}
        return {"kind": "OTHER", "reason": "la regola dipende dal giudizio sul singolo acquisto"}

    def stand_in(prompt: str) -> dict:
        with lock:
            prompts.append(prompt)
        if INTERPRET in prompt:
            # structured-v3 (BANK_AI_RULES_008): every interpretation accounts for the rule's instructions.
            return {"coverage": [{"instruction": "the whole rule", "represented_by": "conditions, WHO and WHY"}],
                    **interpretation_of(prompt)}
        items = []
        for ref, description in MOVE_RE.findall(prompt.split("MOVEMENTS (")[1]):
            if "PUBLIX" in description:
                items.append({"ref": ref, "verdict": "MATCH", "reason": "Acquisto Publix.", "who": "publix",
                              "why_code": why_code.lower(), "why_name": None})
            elif "MYSTERY" in description:
                items.append({"ref": ref, "verdict": "DOUBT", "reason": "Descrizione insufficiente.", "who": "MYSTERY CO",
                              "why_code": None, "why_name": "Unknown purpose"})
        return {"items": items}

    def run_preview(generate, **extra):
        original = ai_client.generate_json
        ai_client.generate_json = generate
        try:
            # The movement-by-movement AI method is asked explicitly (BANK_AI_RULES_008: never a fallback).
            data = {"csrf_token": csrf, "rule_text": PUBLIX_RULE, "allow_ai_batches": "on",
                    "origin_transaction_id": str(ids["origin"]), "date_from": "2026-09-01", "date_to": "2026-09-30"}
            data.update(extra)
            data = {k: v for k, v in data.items() if v is not None}
            response = client.post("/bank/ai-rules/preview", data=data, headers={"X-Requested-With": "fetch"})
            return response.status_code, response.get_json()
        finally:
            ai_client.generate_json = original

    def batch_prompts():
        return [p for p in prompts if "MOVEMENTS (" in p]

    # ---------------------------------------------------------- AI-judged rule
    status, preview = run_preview(stand_in)
    batch_calls = -(-september_count // ai_rules.BATCH_SIZE)
    sent = "\n".join(batch_prompts())
    check("3. a rule with no executable form is judged by the AI on EVERY movement, in several calls",
          status == 200 and preview["ok"] and preview["method"] == "AI" and preview["examined"] == september_count
          and preview["ai_calls"] == batch_calls + 1 == len(prompts)
          and "giudizio sul singolo acquisto" in preview["interpretation_rejected"]
          and sorted(re.findall(r"^T(\d+) \|", sent, re.M), key=int) == [str(i) for i in range(1, september_count + 1)],
          detail=f"{status} {preview and {k: preview.get(k) for k in ('method', 'examined', 'ai_calls', 'error')}}")
    check("3b. matches across every call are returned — the last movements of the period included",
          preview["matches"] == 3 and {i["description"] for i in preview["match_items"]} ==
          {"PUBLIX #1234 ORLANDO", "PUBLIX ALREADY DONE", "PUBLIX CARD 4147202212345678"})
    check("3c. doubtful cases are separate from matches", preview["doubts"] == 1
          and preview["doubt_items"][0]["description"] == "MYSTERY PAYMENT")
    check("3d. the starting transaction is marked and listed first",
          preview["match_items"][0]["is_origin"] and preview["match_items"][0]["id"] == ids["origin"]
          and preview["origin_verdict"] == "MATCH")
    done = next(i for i in preview["match_items"] if i["description"] == "PUBLIX ALREADY DONE")
    check("3e. each item carries date, amount, current WHO/WHY, reason and the proposed WHO/WHY",
          done["date"] == "2026-09-09" and done["amount"] == "-20.00" and done["who"] == "PUBLIX"
          and done["why"] == why_name and done["reason"] == "Acquisto Publix."
          and done["proposed_who"] == "PUBLIX" and not done["proposed_who_is_new"] and done["proposed_why"] == why_name)
    mystery = preview["doubt_items"][0]
    check("3f. a WHO/WHY outside the catalog is only a suggestion, never created",
          mystery["proposed_who"] == "MYSTERY CO" and mystery["proposed_who_is_new"]
          and mystery["proposed_why_is_new"] and not preview["create_missing_who"])
    check("3g. the AI receives the rule, the example, the catalog — and no full card number",
          "Ogni acquisto Publix" in sent and "EXAMPLE | 2026-09-03" in sent and "WHO CATALOG" in sent
          and why_code in sent and "4147202212345678" not in sent and "****5678" in sent)

    prompts.clear()
    status, again = run_preview(stand_in)
    check("3h. the same rule again: interpretation reused and every completed batch reused — no AI call",
          again["ok"] and again["ai_calls"] == 0 and not prompts and again["batches_reused"] == batch_calls
          and again["matches"] == 3 and again["doubts"] == 1, detail=str({k: again.get(k) for k in ('ai_calls', 'batches_reused')}))

    prompts.clear()
    status, outside = run_preview(stand_in, origin_transaction_id=str(ids["august"]))
    check("4. a starting movement outside the period is still evaluated, and marked",
          outside["ok"] and outside["examined"] == september_count + 1
          and any(i["is_origin"] and i["description"] == "AUGUST PUBLIX" for i in outside["match_items"]))

    def picky(prompt: str) -> dict:
        if "MOVEMENTS (" in prompt and len(MOVE_RE.findall(prompt.split("MOVEMENTS (")[1])) > 20:
            raise ai_client.AIProviderUnavailable("AWS Bedrock returned an unparsable response: Expecting ',' delimiter")
        return stand_in(prompt)

    status, split = run_preview(picky, rule_text=PUBLIX_RULE + " (5)")
    check("5. an unreadable answer is split and asked again: still every movement, same result",
          split["ok"] and split["examined"] == september_count and split["matches"] == 3 and split["doubts"] == 1
          and split["ai_calls"] > batch_calls + 1, detail=str({k: split.get(k) for k in ('ai_calls', 'error')}))

    # ---------------------------------------------- throttling and resumption
    sleeps: list[float] = []
    original_sleep = ai_rules._sleep
    ai_rules._sleep = sleeps.append
    try:
        throttle_left = {"n": 3}

        def throttled_twice(prompt: str) -> dict:
            if "MOVEMENTS (" in prompt:
                with lock:
                    if throttle_left["n"] > 0:
                        throttle_left["n"] -= 1
                        raise ai_client.AIProviderUnavailable(
                            "AWS Bedrock call failed: An error occurred (ThrottlingException) when calling the "
                            "Converse operation (reached max retries: 4): Too many requests, please wait")
            return stand_in(prompt)

        status, recovered = run_preview(throttled_twice, rule_text=PUBLIX_RULE + " (6)")
        check("6. throttling is retried with progressive waits and a reduced concurrency: the preview completes",
              recovered["ok"] and recovered["matches"] == 3 and recovered["throttled"] == 3 and len(sleeps) == 3
              and all(w >= ai_rules.BACKOFF_BASE for w in sleeps), detail=str({k: recovered.get(k) for k in ('ok', 'throttled', 'error')}))

        sleeps.clear()
        prompts.clear()
        stuck = {"prompt": None}

        def one_batch_always_throttled(prompt: str) -> dict:
            if "MOVEMENTS (" in prompt and "OTHER VENDOR 050" in prompt:
                with lock:
                    stuck["prompt"] = prompt
                raise ai_client.AIProviderUnavailable("AWS Bedrock call failed: (ThrottlingException) Too many requests")
            return stand_in(prompt)

        status, stopped = run_preview(one_batch_always_throttled, rule_text=PUBLIX_RULE + " (7)")
        waits = list(sleeps)
        check("6b. persistent throttling stops after limited retries: FAILED, no partial result, completed calls kept",
              stopped["ok"] is False and stopped["status"] == "FAILED" and not stopped["match_items"]
              and "1 of 3 AI calls failed after retries" in stopped["error"]
              and "2 of 3 are completed and kept" in stopped["error"]
              and len(waits) == ai_rules.MAX_RETRIES and waits == sorted(waits), detail=str(stopped.get("error")))
        prompts.clear()
        status, resumed = run_preview(stand_in, rule_text=PUBLIX_RULE + " (7)")
        check("6c. Preview again resumes: only the failed batch is asked, the others are reused, the result is complete",
              resumed["ok"] and resumed["ai_calls"] == 1 and len(batch_prompts()) == 1
              and "OTHER VENDOR 050" in batch_prompts()[0] and resumed["batches_reused"] == 2
              and resumed["matches"] == 3 and resumed["doubts"] == 1,
              detail=str({k: resumed.get(k) for k in ('ok', 'ai_calls', 'batches_reused', 'error')}))
    finally:
        ai_rules._sleep = original_sleep

    def other_failure(prompt: str) -> dict:
        if "MOVEMENTS (" in prompt and "OTHER VENDOR 010" in prompt:
            raise ai_client.AIProviderUnavailable("AWS Bedrock call failed: Your session has expired.")
        return stand_in(prompt)

    status, broken = run_preview(other_failure, rule_text=PUBLIX_RULE + " (8)")
    check("6d. a non-throttling failure is not retried and fails the preview with its reason",
          broken["ok"] is False and "session has expired" in broken["error"] and not broken["match_items"])
    status, empty_rule = run_preview(stand_in, rule_text="  ")
    check("6e. an empty rule is refused with a clear message",
          status == 400 and empty_rule["error"] == "Write the rule before asking for a preview.")

    # ------------------------------- general structured rule (BONNE VIE SALON)
    prompts.clear()
    status, salon = run_preview(stand_in, rule_text=SALON_RULE, origin_transaction_id=str(ids["salon_personal"]))
    salon_matches = {i["id"]: i for i in salon["match_items"]}
    check("7. a 'contains + Source owner + WHO + WHY' rule is interpreted ONCE and executed by code — no movement sent",
          salon["ok"] and salon["method"] == "CODE" and salon["ai_calls"] == 1 and len(prompts) == 1
          and INTERPRET in prompts[0] and not batch_prompts(), detail=str({k: salon.get(k) for k in ('method', 'ai_calls', 'error')}))
    check("7b. description contains the text in any case, and only on a Source classified Personal",
          set(salon_matches) == {ids["salon_personal"], ids["salon_lower"]} and ids["salon_company"] not in salon_matches
          and salon["doubts"] == 0 and salon["not_matching"] == september_count - 2, detail=str(sorted(salon_matches)))
    first_item = salon_matches[ids["salon_personal"]]
    check("7c. WHO and WHY are the catalog's (existing), resolved by RF-One",
          first_item["proposed_who"] == "BONNE VIE SALON" and not first_item["proposed_who_is_new"]
          and first_item["proposed_why"] == personal_other_name and not first_item["proposed_why_is_new"])
    lines = salon["interpretation_lines"]
    check("7d. the window shows the interpretation, line by line, to be checked",
          lines == ['IF the description contains “bonne vie salon” (upper/lower case alike)',
                    "IF the Source is classified Personal",
                    "WHO: BONNE VIE SALON (existing)",
                    f"WHY: {personal_other_name} (existing, OWNER_PERSONAL_OTHER)",
                    ai_rules.PROTECTIONS_TEXT,
                    "Data checked — " + ai_rules.SOURCE_CLASS_BASIS,
                    "INSTRUCTION “the whole rule” → conditions, WHO and WHY"] and not salon["interpretation_reused"],
          detail=str(lines))
    prompts.clear()
    status, salon_again = run_preview(stand_in, rule_text=SALON_RULE, origin_transaction_id=str(ids["salon_personal"]))
    check("7e. the same text and instructions: the saved interpretation is reused — no AI call at all",
          salon_again["ok"] and salon_again["ai_calls"] == 0 and not prompts and salon_again["interpretation_reused"]
          and salon_again["matches"] == 2)
    client.post("/bank/ai-rules/instructions", data={"csrf_token": csrf, "instructions": "Pino è il titolare."})
    prompts.clear()
    status, salon_new = run_preview(stand_in, rule_text=SALON_RULE, origin_transaction_id=str(ids["salon_personal"]))
    check("7f. changed general instructions: interpreted again (1 call), with the instructions sent",
          salon_new["ok"] and salon_new["ai_calls"] == 1 and len(prompts) == 1 and "Pino è il titolare." in prompts[0]
          and not salon_new["interpretation_reused"])

    def invented_text(prompt: str) -> dict:
        if INTERPRET in prompt:
            answer = interpretation_of(prompt)
            if answer["kind"] == "STRUCTURED":
                answer["conditions"][0]["value"] = "salon xyz"
            return answer
        return stand_in(prompt)

    prompts.clear()
    status, unverified = run_preview(invented_text, rule_text=SALON_RULE + " Sempre.",
                                     origin_transaction_id=str(ids["salon_personal"]))
    check("7g. a structure whose text is not in the rule is not executed: rejected with the reason, the AI judges",
          unverified["ok"] and unverified["method"] == "AI"
          and "“salon xyz” of a condition is not written in the rule" in unverified["interpretation_rejected"])
    check("7h. validation: unsupported elements and empty rules are rejected",
          ai_rules.validate_interpretation({"kind": "STRUCTURED", "conditions": [{"field": "amount", "op": "gt",
                                                                                  "value": "10"}],
                                            "who": None, "why": {"mode": "fixed", "name": "x"}}, "x")[0] is None
          and ai_rules.validate_interpretation({"kind": "STRUCTURED", "conditions": [], "who": None, "why": None,
                                                "coverage": [{"instruction": "x", "represented_by": "nothing"}]},
                                               "x")[1] == "the rule states no condition")

    # ------------------------------------------------ deterministic Zelle rule
    client.post("/bank/ai-rules/instructions", data={"csrf_token": csrf, "instructions": ""})
    prompts.clear()
    status, z = run_preview(stand_in, rule_text=ZELLE_RULE, origin_transaction_id=str(ids["z_giovanna_1"]),
                            create_missing_who="on")
    matches = {i["id"]: i for i in z["match_items"]}
    check("8. the Zelle/JPM rule is interpreted once by the AI and applied by CODE — no per-movement AI call",
          z["ok"] and z["method"] == "CODE" and z["ai_calls"] == 1 and len(prompts) == 1
          and any("WHO: the text after" in line for line in z["interpretation_lines"]),
          detail=str({k: z.get(k) for k in ('method', 'ai_calls', 'error')}))
    check("8b. every description starting with the prefix (any case) and containing JPM matches; nothing else",
          set(matches) == {ids["z_giovanna_1"], ids["z_giovanna_2"], ids["z_foster"], ids["z_bbc"], ids["z_merged"]}
          and z["examined"] == september_count, detail=str(sorted(i["description"] for i in z["match_items"])))
    check("8c. a description without JPM (numeric code only) is NOT matching and NOT doubtful",
          z["doubts"] == 0 and ids["z_numeric"] not in matches and z["not_matching_with_prefix"] == 1)
    check("8d. the WHO is the text between, spaces normalized, upper case; the WHY is unchanged",
          matches[ids["z_foster"]]["proposed_who"] == "FOSTER KING"
          and matches[ids["z_giovanna_2"]]["proposed_who"] == "GIOVANNA WINE REP"
          and all(i["proposed_why"] is None for i in z["match_items"]))
    check("8e. an existing WHO is recognised whatever its spacing; an absent one is a new WHO to create, not a doubt",
          not matches[ids["z_bbc"]]["proposed_who_is_new"] and matches[ids["z_giovanna_1"]]["proposed_who_is_new"]
          and z["create_missing_who"] and z["new_who_names"] == ["FOSTER KING", "GIOVANNA WINE REP"]
          and z["origin_verdict"] == "MATCH" and matches[ids["z_giovanna_1"]]["is_origin"], detail=str(z["new_who_names"]))

    def create_who(preview_id):
        return client.post(f"/bank/ai-rules/previews/{preview_id}/create-who", data={"csrf_token": csrf},
                           headers={"X-Requested-With": "fetch"})

    refused = create_who(preview["preview_id"])
    check("9. adding WHO is refused for a preview made without “Crea WHO mancanti”",
          refused.status_code == 400 and "was not active" in refused.get_json()["error"])
    first = create_who(z["preview_id"]).get_json()
    check("9b. Inserisci nuovi WHO in elenco creates the missing WHO once each and reuses the existing one",
          first["ok"] and first["created"] == ["GIOVANNA WINE REP", "FOSTER KING"]
          and first["already_present"] == ["BBC  WINE", "MAIN VENDOR"] and first["error_count"] == 0, detail=str(first))
    second = create_who(z["preview_id"]).get_json()
    check("9c. pressing again creates nothing: every WHO is already in the list",
          second["created_count"] == 0 and second["present_count"] == 4, detail=str(second))
    merged_item = matches[ids["z_merged"]]
    check("9d. a name merged into another WHO is that WHO, never re-created, and the row says so",
          merged_item["proposed_who"] == "MAIN VENDOR" and not merged_item["proposed_who_is_new"]
          and "MERGED VENDOR" in merged_item["reason"] and "MAIN VENDOR" in merged_item["reason"]
          and who_names().count("MERGED VENDOR") == 1, detail=str(merged_item))
    with SessionFactory() as s:
        created = s.scalars(select(m.BankOccurrence).where(m.BankOccurrence.canonical_name == "GIOVANNA WINE REP")).all()
        counterparty_id = s.scalars(select(m.BankOccurrenceType.id).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        shape = [(o.status, o.occurrence_type_id == counterparty_id, o.default_transaction_reason_id) for o in created]
    check("9e. GIOVANNA WINE REP exists exactly once, active Counterparty, no WHY invented",
          shape == [("ACTIVE", True, None)], detail=str(shape))
    check("9f. only the WHO list changed: two WHO added, nothing else",
          sorted(set(who_names()) - set(whos_before)) == ["FOSTER KING", "GIOVANNA WINE REP"]
          and len(who_names()) == len(whos_before) + 2)

    # ---------------------------------------------------------------- drafts
    saved = client.post("/bank/ai-rules/drafts", data={"csrf_token": csrf, "rule_text": ZELLE_RULE,
                                                        "origin_transaction_id": str(ids["z_giovanna_1"]),
                                                        "create_missing_who": "on"},
                        headers={"X-Requested-With": "fetch"}).get_json()
    updated = client.post("/bank/ai-rules/drafts", data={"csrf_token": csrf, "rule_text": ZELLE_RULE + " ",
                                                          "draft_id": str(saved["draft_id"]), "create_missing_who": "on",
                                                          "origin_transaction_id": str(ids["z_giovanna_1"])},
                          headers={"X-Requested-With": "fetch"}).get_json()
    reopened = client.get(f"/bank/ai-rules/drafts/{saved['draft_id']}").get_json()
    with SessionFactory() as s:
        draft_facts = [(d.status, d.origin_transaction_id, d.create_missing_who) for d in s.scalars(select(m.BankAiRuleDraft))]
    check("10. a rule is saved as a draft with its origin and “Crea WHO mancanti”, updated in place",
          saved["ok"] and updated["draft_id"] == saved["draft_id"]
          and draft_facts == [("DRAFT", ids["z_giovanna_1"], True)], detail=str(draft_facts))
    check("10b. a draft reopens with its rule, its origin and its option",
          reopened["rule_text"] == ZELLE_RULE and reopened["origin"]["id"] == ids["z_giovanna_1"]
          and reopened["create_missing_who"] is True)

    check("11. movements, decisions, allocations, WHY, rules and Standards are unchanged", facts() == before,
          detail=f"{before[:9]} -> {facts()[:9]}")
    check("11b. extraction outcomes of a WHO between two texts",
          ai_rules.extract_between("ZELLE PAYMENT TO  a  b JPM1", {"starts_with": "Zelle payment to", "end_marker": "JPM"})
          == ("MATCH", "A B")
          and ai_rules.extract_between("Zelle payment to X jpm1", {"starts_with": "Zelle payment to", "end_marker": "JPM"})
          == ("NO_MARKER", None)
          and ai_rules.extract_between("Zelle payment to JPM1", {"starts_with": "Zelle payment to", "end_marker": "JPM"})
          == ("EMPTY", None))
    check("11c. masking keeps short numbers and the last four of long ones",
          ai_rules.mask_numbers("STORE 1234 REF 1234-5678-9012 ON 09/03") == "STORE 1234 REF ****9012 ON 09/03")

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
