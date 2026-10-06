"""The simple WHO Rule — one sentence, one Apply (BANK_SIMPLE_WHO_RULE_001).

Proves, on a throwaway database:

* the plain-language instruction is read into exactly one deterministic
  DESCRIPTION-CONTAINS pattern, or refused without guessing;
* Classification is a fast paginated, searchable list of WHO occurrences
  with a Rule button and no WHO x WHY rendering, merged fragments hidden;
* Apply — the ONE service, reached from Classification and from Review —
  saves the WHO-only rule and the possible WHY, gives every safe matching
  transaction the canonical WHO, preserves every human decision, merges
  the recognizer fragments safely, and is idempotent;
* the ABC and Top Linen acceptance scenarios, including future imports;
* WHO never determines WHY, and WHAT, For Whom, Standards and
  Configuration are untouched.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import time
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_bank_simple_who_rules_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-simple-who-rules-secret"

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
from rfone_data_store.bank_reconciliation import who_recognition as wr  # noqa: E402
from rfone_data_store.bank_reconciliation import who_rules  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
DAY = date(2026, 8, 3)
RECOGNIZED = "Recognised by who-v1 from the bank's own text (CARD_MERCHANT). Identity only."
ABC_RULE = "Dove nella descrizione trovi ABC il WHO è ABC"
TOP_LINEN_RULE = "Dove nella descrizione trovi Top Linen il WHO è Top Linen"
TOP_LINEN_CSV = (
    "Card,Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
    "1057,08/20/2026,08/21/2026,TOP LINEN ORLANDO 9999,Services,Sale,-88.00,\n"
)


def table_rows(session, model, *columns):
    return sorted(session.execute(select(*[getattr(model, c) for c in columns])).all(), key=repr)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    # ------------------------------------------------------------------
    # RULE PARSING (1-5)
    # ------------------------------------------------------------------
    parsed = who_rules.parse_rule_instruction(ABC_RULE)
    check("1. 'Dove nella descrizione trovi ABC il WHO è ABC' -> contains ABC",
          parsed.normalized_pattern == "ABC" and parsed.stated_who == "ABC")
    upper = who_rules.parse_rule_instruction("DOVE NELLA DESCRIZIONE TROVI abc IL WHO È Abc")
    check("2. the same with different capitalization", upper.normalized_pattern == "ABC")
    quoted = who_rules.parse_rule_instruction('Dove nella descrizione trovi "Top Linen" il WHO è Top Linen')
    check("3. quoted recognition text", quoted.normalized_pattern == "TOP LINEN" and quoted.phrase == "Top Linen")

    def refused(text: str) -> bool:
        try:
            who_rules.parse_rule_instruction(text)
        except who_rules.RuleInstructionError:
            return True
        return False

    check("4. an ambiguous instruction is rejected, never guessed",
          refused("Dove nella descrizione trovi ABC o XYZ il WHO è ABC")
          and refused("Dove nella descrizione trovi ABC e dove trovi XYZ il WHO è ABC")
          and refused('Dove nella descrizione trovi "ABC" o "XYZ" il WHO è ABC')
          and refused("il WHO è ABC") and refused("ABC"))
    check("5. an empty instruction is rejected", refused("") and refused("   ") and refused(None))
    check("5b. a too-short text is rejected", refused("Dove nella descrizione trovi AB il WHO è AB"))

    # ------------------------------------------------------------------
    # Dataset
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        account_service.create_account(s, username="rule_operator", display_name="Rule Operator",
                                       password="RuleOperator123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="rule_operator").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        entity = m.LegalEntity(legal_name="Rule Test LLC", status="ACTIVE")
        s.add(entity)
        s.flush()
        card = m.PaymentInstrument(legal_entity_id=entity.id, instrument_type="CREDIT_CARD",
                                   display_name="Chase Card 1057", institution="CHASE", last_four="1057",
                                   currency="USD")
        s.add(card)
        s.flush()
        batch = m.BankImportBatch(detected_format="CHASE_CREDIT_CARD_WITH_CARD", original_file_name="seed.csv",
                                  raw_file_bytes=b"x", sha256="1" * 64, status="NORMALIZED",
                                  payment_instrument_id=card.id)
        s.add(batch)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(
            m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        beer = s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.code == "BEER_PURCHASES")).one()
        liquor = s.scalars(select(m.BankTransactionReason).where(
            m.BankTransactionReason.code == "LIQUOR_PURCHASES")).one()

        def who(name, *, status="ACTIVE", notes=RECOGNIZED):
            o = m.BankOccurrence(canonical_name=name, occurrence_type_id=counterparty.id, status=status,
                                 optional_notes=notes)
            s.add(o)
            s.flush()
            return o

        abc = who("ABC", notes="Canonical WHO from the WHO/WHY import.")
        fragment_names = ["ABC FINE WINE 71", "ABC FINE WINE S", "ABC FINE WINE SPIRITS",
                          "ABC FINE WINE SPIRITS 014", "ABC FINE WINE SPIRITS 071", "ABC FINE WINE SPIRITS 136"]
        fragments = {name: who(name) for name in fragment_names}
        s.add(m.BankOccurrenceAlias(occurrence_id=fragments["ABC FINE WINE S"].id, alias_text="ABC FINE WINE/S",
                                    alias_key=wr.who_key("ABC FINE WINE/S"), source_family="POS_FIXED_WIDTH",
                                    source="PARSER"))
        human_fragment = who("ABC FINE WINE HUMAN")            # a person chose it once
        configured = who("ABC SUPPLY CO", notes=None)          # created by a person in Configuration
        old_merged = who("ABC OLD MERGED", status="INACTIVE", notes=RECOGNIZED + "\nMerged into 'ABC' (#1).")
        top_linen = who("Top Linen", notes="Canonical WHO from the WHO/WHY import.")
        table_top = who("TABLE TOP LINEN")
        gordon = who("Gordon Food Service", notes="Canonical WHO from the WHO/WHY import.")
        publix = who("PUBLIX SUPER MARKETS")
        for n in range(60):                                    # enough WHO for a second page
            who(f"FILLER VENDOR {n:03d}")
        s.flush()

        seq = [0]

        def tx(description, amount=-1000, *, recognized=None, decision=None, reason=None, status=None):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=card.id, bank_source="CHASE_CREDIT_CARD_WITH_CARD", import_batch_id=batch.id,
                posting_date=DAY, transaction_date=DAY, description_original=description,
                description_normalized=description, amount_minor=amount, status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"seed-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            if recognized is not None:
                s.add(m.BankWhoRecognition(
                    financial_transaction_id=t.id, recognizer_version=wr.RECOGNIZER_VERSION,
                    tier=wr.DETERMINISTIC, family="CARD_MERCHANT", parser_code="CARD_DESCRIPTOR",
                    extracted_name=recognized.canonical_name, occurrence_id=recognized.id,
                    evidence="card statement merchant descriptor"))
            else:
                s.add(m.BankWhoRecognition(
                    financial_transaction_id=t.id, recognizer_version=wr.RECOGNIZER_VERSION,
                    tier=wr.PROPOSED, family="OTHER_DESCRIPTOR", parser_code="UNSTRUCTURED",
                    proposed_name=description, evidence="a name-like descriptor with no recognised structure"))
            if decision is not None:
                source, occurrence = decision
                recognition._create_decision_row(
                    s, t, occurrence_id=occurrence.id if occurrence else None,
                    transaction_reason_id=reason.id if reason else None, recognition_rule_id=None,
                    decision_source=source,
                    decision_status=status or ("HUMAN_CONFIRMED" if source == "HUMAN" else "NEEDS_HUMAN_REVIEW"),
                    confidence="HIGH" if reason else None, explanation_notes="seed",
                    confirmed_by_account_id=operator.id if source == "HUMAN" else None)
            s.flush()
            return t

        abc_tx = {
            "71": tx("ABC FINE WINE 71 ORLANDO FL", recognized=fragments["ABC FINE WINE 71"]),
            "s": tx("ABC FINE WINE/S ABC FINE WINE/SPWINTER PARK FL", recognized=fragments["ABC FINE WINE S"],
                    decision=("RULE", fragments["ABC FINE WINE S"])),
            "spirits": tx("ABC FINE WINE/SPIRITS WINTER PARK FL", recognized=fragments["ABC FINE WINE SPIRITS"],
                          decision=("RULE", fragments["ABC FINE WINE SPIRITS"]), reason=beer, status="AUTO_APPLIED"),
            "014": tx("ABC FINE WINE & SPIRITS 014 ORLANDO", recognized=fragments["ABC FINE WINE SPIRITS 014"]),
            "071": tx("ABC FINE WINE SPIRITS 071 WINTER PARK", recognized=fragments["ABC FINE WINE SPIRITS 071"]),
            "136": tx("ABC FINE WINE SPIRITS 136 KISSIMMEE", recognized=fragments["ABC FINE WINE SPIRITS 136"]),
            "136b": tx("ABC FINE WINE SPIRITS 136 KISSIMMEE", -2200, recognized=fragments["ABC FINE WINE SPIRITS 136"]),
            "unrecognized": tx("IC* ABC FINE VIA INSTA HTTPSWWW.ABCF CA"),
            "supply": tx("ABC SUPPLY CO 55 TAMPA", recognized=configured),
        }
        human_conflict = tx("ABC FINE WINE SPIRITS 071 PAID BY GORDON", recognized=fragments["ABC FINE WINE SPIRITS 071"],
                            decision=("HUMAN", gordon), reason=beer)
        human_same = tx("ABC FINE WINE 71 SAME", recognized=fragments["ABC FINE WINE 71"],
                        decision=("HUMAN", abc), reason=liquor)
        human_on_fragment = tx("ABC FINE WINE HUMAN CHOICE", recognized=human_fragment,
                               decision=("HUMAN", human_fragment))
        top_tx = {
            "orlando": tx("TOP LINEN ORLANDO 1234"),
            "table": tx("ORIG CO NAME:TABLE TOP LINEN        ORIG ID:1900922218 CO ENTRY DESCR:WEDNESDAY",
                        recognized=table_top),
            "other": tx("TOP LINEN ORLANDO 5678", -4400),
        }
        unrelated = tx("PUBLIX SUPER MARKETS 1234", recognized=publix)
        s.commit()

        ids = {
            "abc": abc.id, "top_linen": top_linen.id, "gordon": gordon.id, "configured": configured.id,
            "human_fragment": human_fragment.id, "old_merged": old_merged.id, "table_top": table_top.id,
            "beer": beer.id, "liquor": liquor.id, "card": card.id,
            "fragments": {name: o.id for name, o in fragments.items()},
            "abc_tx": {k: t.id for k, t in abc_tx.items()}, "top_tx": {k: t.id for k, t in top_tx.items()},
            "human_conflict": human_conflict.id, "human_same": human_same.id,
            "human_on_fragment": human_on_fragment.id, "unrelated": unrelated.id,
        }

        def current_decisions():
            return {t.id: (t.explanation_id and s.get(m.BankTransactionExplanation, t.explanation_id))
                    for t in s.scalars(select(m.FinancialTransaction))}

        purpose_before = {tx_id: (e.transaction_reason_id, e.accounting_classification_id,
                                  e.decision_status) if e else None
                          for tx_id, e in current_decisions().items()}
        human_rows_before = table_rows(s, m.BankTransactionExplanation, "id", "financial_transaction_id",
                                       "occurrence_id", "decision_source", "decision_status",
                                       "occurrence_name_snapshot", "transaction_reason_id")
        config_before = {
            "what": table_rows(s, m.BankAccountingClassification, "id", "code", "name", "active", "statement_type"),
            "why": table_rows(s, m.BankTransactionReason, "id", "code", "name", "status", "accounting_classification_id"),
            "instruments": table_rows(s, m.PaymentInstrument, "id", "display_name", "status", "legal_entity_id"),
            "entities": table_rows(s, m.ReportingEntity, "id", "name", "status"),
            "defaults": table_rows(s, m.BankOccurrence, "id", "default_transaction_reason_id"),
        }
        for_whom_before = (table_rows(s, m.BankOccurrenceReportingEntity, "id", "occurrence_id", "reporting_entity_id",
                                      "active"),
                           table_rows(s, m.BankTransactionAllocation, "id"))
        standards_before = table_rows(s, m.BankReconciliationStandard, "id", "occurrence_id", "status")

    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "rule_operator", "password": "RuleOperator123!", "csrf_token": csrf})

    # ------------------------------------------------------------------
    # CLASSIFICATION (6-11)
    # ------------------------------------------------------------------
    start = time.perf_counter()
    resp = client.get("/bank/classification")
    elapsed = time.perf_counter() - start
    page = resp.data.decode()
    rows = page.count('class="who-rule-open"')
    check("6. Classification is paginated (50 rows on the first page, a Next link)",
          resp.status_code == 200 and rows == 50 and "Next &rarr;" in page and "Page 1 of 2" in page,
          detail=f"status={resp.status_code} rows={rows}")
    second = client.get("/bank/classification?page=2").data.decode()
    check("6b. the second page holds the rest", second.count('class="who-rule-open"') > 0 and "Page 2 of 2" in second)
    search = client.get("/bank/classification?q=abc").data.decode()
    check("7. search filters the WHO by name, case-insensitively",
          "ABC FINE WINE SPIRITS 071" in search and "FILLER VENDOR" not in search and "PUBLIX" not in search)
    check("8. the initial GET is fast", elapsed < 2.0, detail=f"{elapsed:.2f}s")
    check("9. no WHO x WHY rendering: no per-row WHY/WHAT dropdown, no receiver candidates",
          'name="default_transaction_reason_id"' not in page and "<select" not in page.split("who-rule-modal")[0]
          and "receiver" not in page.lower())
    check("10. inactive merged fragments are hidden from the normal view",
          "ABC OLD MERGED" not in search and "Show merged WHO" in search)
    merged_view = client.get("/bank/classification?q=abc&show=merged").data.decode()
    check("10b. ... and still visible for audit on request", "ABC OLD MERGED" in merged_view)
    row_button = re.search(r'data-who-id="(\d+)"\s+data-who-name="([^"]*)"\s+data-subject="Occurrence: ABC FINE WINE SPIRITS 071"',
                           search)
    check("11. every occurrence row has a Rule button, preselecting the canonical WHO (ABC)",
          row_button is not None and int(row_button.group(1)) == ids["abc"] and row_button.group(2) == "ABC",
          detail=str(row_button.groups() if row_button else None))
    check("11b. the modal has WHO, one Rule text field, possible WHY and Apply — no match-type control",
          'id="who-rule-instruction"' in page and 'name="transaction_reason_id"' in page
          and ">Apply</button>" in page and "CONTAINS" not in page and "PREFIX" not in page)

    # ------------------------------------------------------------------
    # RULE APPLY (12-21) — through the HTTP route, as the modal does
    # ------------------------------------------------------------------
    calls = []
    original_apply = who_rules.apply_who_rule

    def spy(*args, **kwargs):
        calls.append(kwargs.get("created_from_transaction_id"))
        return original_apply(*args, **kwargs)

    who_rules.apply_who_rule = spy
    csrf = CSRF_RE.search(page).group(1)

    def apply(occurrence_id, instruction, whys=(), transaction_id=None, return_to="/bank/classification?q=ABC"):
        data = {"csrf_token": csrf, "occurrence_id": str(occurrence_id), "instruction": instruction,
                "transaction_reason_id": [str(w) for w in whys], "return_to": return_to}
        if transaction_id:
            data["transaction_id"] = str(transaction_id)
        return client.post("/bank/who-rules/apply", data=data, headers={"X-Requested-With": "fetch"})

    bad = apply(ids["abc"], "Dove nella descrizione trovi ABC o XYZ il WHO è ABC")
    with SessionFactory() as s:
        no_rule = s.scalar(select(func.count(m.BankRecognitionRule.id))) == 0
    check("4b. an ambiguous rule is refused by Apply with a readable error, and nothing is written",
          bad.status_code == 400 and not bad.get_json()["ok"] and "Rewrite" in bad.get_json()["error"] and no_rule)
    mismatch = apply(ids["abc"], "Dove nella descrizione trovi ABC il WHO è Gordon Food Service")
    check("20b. a rule naming another WHO than the selected one is refused",
          mismatch.status_code == 400 and "selected WHO" in mismatch.get_json()["error"])
    inactive = apply(ids["old_merged"], "Dove nella descrizione trovi ABC")
    check("20c. an INACTIVE WHO is refused", inactive.status_code == 400 and "inactive" in inactive.get_json()["error"])

    resp = apply(ids["abc"], ABC_RULE, whys=(ids["beer"], ids["liquor"]))
    body = resp.get_json()
    check("Apply answers ok and returns to the Classification search",
          resp.status_code == 200 and body["ok"] and body["redirect"] == "/bank/classification?q=ABC",
          detail=str(body))
    result_page = client.get(body["redirect"]).data.decode()

    with SessionFactory() as s:
        rules = s.scalars(select(m.BankRecognitionRule)).all()
        rule = rules[0] if rules else None
        check("12. one WHO-only rule is saved: DESCRIPTION contains 'ABC' -> ABC, no WHY, no scope, auto-applied",
              len(rules) == 1 and rule.match_type == recognition.CONTAINS_TEXT and rule.normalized_pattern == "ABC"
              and rule.match_field == recognition.DESCRIPTION and rule.determines_purpose is False
              and rule.transaction_reason_id is None and rule.payment_instrument_id is None
              and rule.direction is None and rule.auto_apply_enabled and rule.status == "ACTIVE"
              and rule.occurrence_id == ids["abc"])
        associations = {a.transaction_reason_id for a in s.scalars(select(m.BankOccurrenceReasonAssociation).where(
            m.BankOccurrenceReasonAssociation.occurrence_id == ids["abc"], m.BankOccurrenceReasonAssociation.active))}
        check("13. the possible WHY associations are saved (ABC: Beer + Liquor)",
              associations == {ids["beer"], ids["liquor"]})
        decisions = current_decisions()
        abc_current = {k: decisions[v] for k, v in ids["abc_tx"].items()}
        check("14. the rule determines no WHY: a transaction with no WHY still has none",
              all(abc_current[k].transaction_reason_id is None for k in ("71", "s", "014", "071", "136", "unrecognized")))
        check("15. matching transactions get the canonical WHO (decision and recognition)",
              all(e.occurrence_id == ids["abc"] for e in abc_current.values())
              and all(s.scalars(select(m.BankWhoRecognition).where(
                  m.BankWhoRecognition.financial_transaction_id == v)).one().occurrence_id == ids["abc"]
                  for v in ids["abc_tx"].values()))
        check("15b. each new decision is a RULE decision naming the rule, still waiting for its WHY",
              all(abc_current[k].decision_source == "RULE" and abc_current[k].recognition_rule_id == rule.id
                  and abc_current[k].decision_status == "NEEDS_HUMAN_REVIEW" for k in ("71", "014", "unrecognized")))
        check("15c. an existing WHY is carried over unchanged (AUTO_APPLIED Beer stays Beer)",
              abc_current["spirits"].transaction_reason_id == ids["beer"]
              and abc_current["spirits"].decision_status == "AUTO_APPLIED"
              and abc_current["spirits"].transaction_reason_name_snapshot == "Beer Purchases")
        conflict = decisions[ids["human_conflict"]]
        check("16. a human decision naming a different WHO is preserved (Gordon stays Gordon, HUMAN)",
              conflict.occurrence_id == ids["gordon"] and conflict.decision_source == "HUMAN")
        same = decisions[ids["human_same"]]
        check("17. a human decision already naming ABC is left unchanged",
              same.decision_source == "HUMAN" and same.occurrence_id == ids["abc"]
              and same.transaction_reason_id == ids["liquor"])
        statuses = {name: s.get(m.BankOccurrence, oid).status for name, oid in ids["fragments"].items()}
        canonical_aliases = {(a.alias_text, a.source_family) for a in s.scalars(select(m.BankOccurrenceAlias).where(
            m.BankOccurrenceAlias.occurrence_id == ids["abc"]))}
        fragment_alias_kept = s.scalars(select(m.BankOccurrenceAlias).where(
            m.BankOccurrenceAlias.occurrence_id == ids["fragments"]["ABC FINE WINE S"])).all()
        check("18. the recognizer fragments are merged: INACTIVE, never deleted, names kept as aliases of ABC",
              all(st == "INACTIVE" for st in statuses.values())
              and all((name, who_rules.MERGED_WHO_NAME) in canonical_aliases for name in fragment_names)
              and ("ABC FINE WINE/S", "POS_FIXED_WIDTH") in canonical_aliases and len(fragment_alias_kept) == 1
              and all("Merged into 'ABC'" in s.get(m.BankOccurrence, oid).optional_notes
                      for oid in ids["fragments"].values()),
              detail=str(statuses))
        check("18b. a WHO a person chose, and a configured WHO, are NOT merged (conflicts, still ACTIVE)",
              s.get(m.BankOccurrence, ids["human_fragment"]).status == "ACTIVE"
              and s.get(m.BankOccurrence, ids["configured"]).status == "ACTIVE")
        old_rows = [r for r in human_rows_before]
        now_rows = table_rows(s, m.BankTransactionExplanation, "id", "financial_transaction_id", "occurrence_id",
                              "decision_source", "decision_status", "occurrence_name_snapshot",
                              "transaction_reason_id")
        check("19. every earlier decision row and its snapshot is preserved (append-only)",
              all(row in now_rows for row in old_rows))
        check("19b. no recognition references a merged fragment",
              not s.scalar(select(func.count(m.BankWhoRecognition.id)).where(
                  m.BankWhoRecognition.occurrence_id.in_(list(ids["fragments"].values())))))
        check("19c. no current decision names a merged fragment",
              not any(e and e.occurrence_id in ids["fragments"].values() for e in decisions.values()))

    collapsed = client.get("/bank/classification?q=ABC").data.decode()
    occurrence_rows = re.findall(r'data-subject="Occurrence: ([^"]+)"', collapsed)
    check("20. inactive fragments are hidden after Apply",
          not any(name in occurrence_rows for name in fragment_names))
    check("21. ABC appears as one canonical row (the WHO a person chose and the configured WHO stay listed)",
          occurrence_rows.count("ABC") == 1 and sorted(occurrence_rows) == ["ABC", "ABC FINE WINE HUMAN", "ABC SUPPLY CO"],
          detail=str(occurrence_rows))
    check("17b. the result is shown: matched / updated / already / human conflicts / merged / possible WHY",
          "Rule saved." in result_page and "Existing transactions matched" in result_page
          and "Human conflicts preserved" in result_page and "Historical WHO fragments merged" in result_page
          and "Beer Purchases" in result_page and "Liquor / Cocktail Product Purchases" in result_page)
    result = re.search(r"<dt>Existing transactions matched</dt><dd>(\d+)</dd>\s*<dt>Transactions updated</dt><dd>(\d+)</dd>"
                       r"\s*<dt>Already assigned</dt><dd>(\d+)</dd>\s*<dt>Human conflicts preserved</dt><dd>(\d+)</dd>",
                       result_page)
    check("17c. the counts add up: 12 matched = 9 updated + 1 already + 2 human conflicts",
          result is not None and result.groups() == ("12", "9", "1", "2"), detail=str(result and result.groups()))
    check("17d. the result shows no database id", "#" + str(ids["abc"]) not in result_page.split("who-rule-result")[1][:3000])

    # ------------------------------------------------------------------
    # IDEMPOTENCY (39)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        counts_before = {model.__name__: s.scalar(select(func.count(model.id))) for model in (
            m.BankRecognitionRule, m.BankOccurrenceReasonAssociation, m.BankOccurrenceAlias,
            m.BankTransactionExplanation, m.BankWhoRecognition, m.BankOccurrence)}
        inactive_before = s.scalar(select(func.count(m.BankOccurrence.id)).where(m.BankOccurrence.status == "INACTIVE"))
    again = apply(ids["abc"], "dove nella descrizione trovi abc il who è abc", whys=(ids["beer"], ids["liquor"]))
    with SessionFactory() as s:
        counts_after = {model.__name__: s.scalar(select(func.count(model.id))) for model in (
            m.BankRecognitionRule, m.BankOccurrenceReasonAssociation, m.BankOccurrenceAlias,
            m.BankTransactionExplanation, m.BankWhoRecognition, m.BankOccurrence)}
        inactive_after = s.scalar(select(func.count(m.BankOccurrence.id)).where(m.BankOccurrence.status == "INACTIVE"))
        confirmations = s.scalars(select(m.BankOccurrenceReasonAssociation.confirmation_count).where(
            m.BankOccurrenceReasonAssociation.occurrence_id == ids["abc"])).all()
    again_page = client.get("/bank/classification?q=ABC").data.decode()
    check("39. a second Apply makes 0 business changes: no duplicate rule, WHY, alias, merge or decision",
          again.status_code == 200 and counts_after == counts_before and inactive_after == inactive_before
          and confirmations == [1, 1] and "Nothing new to change" in again_page and "Rule already in place." in again_page,
          detail=f"{counts_before} -> {counts_after}")

    # ------------------------------------------------------------------
    # REVIEW (22-25) and TOP LINEN (32-33)
    # ------------------------------------------------------------------
    review = client.get("/bank/review").data.decode()
    check("22. Review carries the same Rule modal posting to the same Apply route",
          review.count('id="who-rule-modal"') == 1 and 'action="/bank/who-rules/apply"' in review
          and "bank-who-rule.js" in review
          # BANK_MANUAL_WHO_WHY_001: the Rule is the row's own button; the
          # "Select WHO / WHY" popup no longer carries a Rule shortcut.
          and 'id="who-picker-rule"' not in review)
    orlando_button = re.search(r'data-transaction-id="%d"\s+(?:title="[^"]*"\s+)?data-who-id="([^"]*)"' % ids["top_tx"]["orlando"], review)
    check("22b. a row with no recognised WHO opens the Rule with no WHO preselected",
          orlando_button is not None and orlando_button.group(1) == "")

    # The operator selects WHO = Top Linen for the row (Who only), then Rule.
    with SessionFactory() as s:
        bank_service.record_recognition_decision(
            s, transaction_id=ids["top_tx"]["orlando"], occurrence_id=ids["top_linen"],
            confirmed_by_account_id=None, learn_description=False)
        s.commit()
    # BANK_TWO_STAGE_REVIEW_001 — with its WHO chosen, the row leaves To
    # Reconcile and is listed under Reconciled with that WHO.
    review = client.get("/bank/review").data.decode()
    reconciled = client.get("/bank/review?view=reconciled").data.decode()
    check("23. the manually selected WHO moves the row to Reconciled, with that WHO",
          f'data-transaction-id="{ids["top_tx"]["orlando"]}"' not in review
          and re.search(r'id="t-%d"[^>]*data-who="%d"' % (ids["top_tx"]["orlando"], ids["top_linen"]), reconciled)
          is not None)
    calls_before = len(calls)
    resp = apply(ids["top_linen"], TOP_LINEN_RULE, transaction_id=ids["top_tx"]["orlando"], return_to="/bank/review")
    check("22c. Review's Apply runs through the one shared service (with the transaction it came from)",
          resp.status_code == 200 and len(calls) == calls_before + 1 and calls[-1] == ids["top_tx"]["orlando"])
    with SessionFactory() as s:
        decisions = current_decisions()
        top = {k: decisions[v] for k, v in ids["top_tx"].items()}
        check("24/32. Apply from Review assigns Top Linen to every matching description (incl. TABLE TOP LINEN)",
              top["other"].occurrence_id == ids["top_linen"] and top["table"].occurrence_id == ids["top_linen"]
              and top["orlando"].occurrence_id == ids["top_linen"])
        check("24b. the row the operator decided keeps its own (human) decision",
              top["orlando"].decision_source == "HUMAN")
        check("24c. the TABLE TOP LINEN fragment is merged into Top Linen",
              s.get(m.BankOccurrence, ids["table_top"]).status == "INACTIVE")
        rule = s.scalars(select(m.BankRecognitionRule).where(
            m.BankRecognitionRule.occurrence_id == ids["top_linen"])).one()
        check("24d. the Top Linen rule records the transaction it was taught from",
              rule.created_from_transaction_id == ids["top_tx"]["orlando"] and rule.normalized_pattern == "TOP LINEN")
        check("24e. no possible WHY was invented for Top Linen", not s.scalar(select(func.count(
            m.BankOccurrenceReasonAssociation.id)).where(m.BankOccurrenceReasonAssociation.occurrence_id == ids["top_linen"])))

        # 25 / 33 — future imports resolve directly to the canonical WHO.
        upload = bank_service.import_csv(s, file_bytes=TOP_LINEN_CSV.encode("utf-8"),
                                         original_file_name="chase1057_top_linen.csv", uploaded_by_account_id=None,
                                         payment_instrument_id=ids["card"])
        s.commit()
        imported = s.scalars(select(m.FinancialTransaction).where(
            m.FinancialTransaction.import_batch_id == upload.batch.id)).one()
        imported_decision = recognition.get_current_explanation(s, financial_transaction_id=imported.id)
        check("25/33. a future imported Top Linen transaction resolves to Top Linen on import",
              imported_decision is not None and imported_decision.occurrence_id == ids["top_linen"]
              and imported_decision.transaction_reason_id is None)
        resolution = wr.CanonicalWhoResolver(s).resolve(
            "TOP LINEN ORLANDO", description="TOP LINEN ORLANDO 9999", amount_minor=-8800, instrument_id=ids["card"])
        check("25b. CanonicalWhoResolver names Top Linen through the rule",
              resolution.occurrence is not None and resolution.occurrence.id == ids["top_linen"]
              and resolution.how == wr.RESOLVED_BY_RULE)
        def rule_family_names():
            return sorted(n for n in s.scalars(select(m.BankOccurrence.canonical_name))
                          if "LINEN" in n.upper() or "ABC" in n.upper())

        names_before = rule_family_names()
        wr.recognize_transactions(s, link_suppliers=False)
        s.commit()
        fresh = s.scalars(select(m.BankWhoRecognition).where(
            m.BankWhoRecognition.financial_transaction_id == imported.id)).one()
        check("25c. WHO recognition of the new transaction creates no fragment WHO first",
              fresh.occurrence_id == ids["top_linen"] and rule_family_names() == names_before,
              detail=str(set(rule_family_names()) - set(names_before)))
        abc_future = wr.CanonicalWhoResolver(s).resolve(
            "ABC FINE WINE SPIRITS 999", description="ABC FINE WINE SPIRITS 999 ORLANDO", amount_minor=-100,
            instrument_id=ids["card"])
        check("33b. a future ABC transaction resolves to ABC, not to a fragment",
              abc_future.occurrence is not None and abc_future.occurrence.id == ids["abc"])

    # ------------------------------------------------------------------
    # ABC ACCEPTANCE (26-31)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        decisions = current_decisions()
        abc_ids = list(ids["abc_tx"].values())
        check("26. the disposable scenario holds several ABC FINE WINE ... occurrences", len(fragment_names) >= 6)
        check("27. the rule is 'description contains ABC -> WHO ABC'",
              s.scalars(select(m.BankRecognitionRule).where(m.BankRecognitionRule.occurrence_id == ids["abc"])).one()
              .normalized_pattern == "ABC")
        check("28. all safe ABC transactions are ABC", all(decisions[t].occurrence_id == ids["abc"] for t in abc_ids))
        reasons = {r.name for r in s.scalars(select(m.BankTransactionReason).join(
            m.BankOccurrenceReasonAssociation,
            m.BankOccurrenceReasonAssociation.transaction_reason_id == m.BankTransactionReason.id).where(
            m.BankOccurrenceReasonAssociation.occurrence_id == ids["abc"]))}
        check("29. ABC has Beer + Liquor as possible WHY",
              reasons == {"Beer Purchases", "Liquor / Cocktail Product Purchases"})
        check("30. no WHY was chosen automatically, and ABC's default WHY is not set",
              all(decisions[t].transaction_reason_id is None for t in abc_ids if t != ids["abc_tx"]["spirits"])
              and s.get(m.BankOccurrence, ids["abc"]).default_transaction_reason_id is None)
    final_abc = client.get("/bank/classification?q=ABC").data.decode()
    check("31. the Classification normal view shows one ABC",
          re.findall(r'data-subject="Occurrence: ([^"]+)"', final_abc).count("ABC") == 1
          and "ABC FINE WINE SPIRITS 071" not in final_abc.split("who-rule-modal")[0])

    # ------------------------------------------------------------------
    # INVARIANTS (34-38)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        decisions = current_decisions()
        changed_purpose = [tx_id for tx_id, before in purpose_before.items()
                           if before is not None and decisions[tx_id] is not None
                           and (decisions[tx_id].transaction_reason_id, decisions[tx_id].accounting_classification_id,
                                decisions[tx_id].decision_status) != before]
        check("34. WHO/WHY invariant: no description rule determines purpose, and no transaction's WHY changed",
              not s.scalar(select(func.count(m.BankRecognitionRule.id)).where(
                  m.BankRecognitionRule.match_field == recognition.DESCRIPTION,
                  m.BankRecognitionRule.determines_purpose.is_(True))) and not changed_purpose,
              detail=str(changed_purpose))
        check("35. WHAT unchanged: the accounting catalog and every transaction's WHAT",
              table_rows(s, m.BankAccountingClassification, "id", "code", "name", "active", "statement_type")
              == config_before["what"] and not changed_purpose)
        check("36. For Whom unchanged: WHO -> entities and allocations",
              (table_rows(s, m.BankOccurrenceReportingEntity, "id", "occurrence_id", "reporting_entity_id", "active"),
               table_rows(s, m.BankTransactionAllocation, "id")) == for_whom_before)
        check("37. Standards unchanged",
              table_rows(s, m.BankReconciliationStandard, "id", "occurrence_id", "status") == standards_before)
        check("38. Configuration unchanged: WHY catalog, instruments, entities, WHO default WHY",
              table_rows(s, m.BankTransactionReason, "id", "code", "name", "status", "accounting_classification_id")
              == config_before["why"]
              and table_rows(s, m.PaymentInstrument, "id", "display_name", "status", "legal_entity_id")
              == config_before["instruments"]
              and table_rows(s, m.ReportingEntity, "id", "name", "status") == config_before["entities"]
              and [row for row in table_rows(s, m.BankOccurrence, "id", "default_transaction_reason_id")
                   if row in config_before["defaults"] or row[0] in {r[0] for r in config_before["defaults"]}]
              == config_before["defaults"])

    # ------------------------------------------------------------------
    # SAFETY (20)
    # ------------------------------------------------------------------
    clash = apply(ids["gordon"], "Dove nella descrizione trovi ABC il WHO è Gordon Food Service")
    with SessionFactory() as s:
        gordon_rules = s.scalar(select(func.count(m.BankRecognitionRule.id)).where(
            m.BankRecognitionRule.occurrence_id == ids["gordon"]))
    check("20d. a rule giving the same match to another WHO is refused, nothing partially applied",
          clash.status_code == 400 and "already recognised" in clash.get_json()["error"] and gordon_rules == 0)
    form_post = client.post("/bank/who-rules/apply", data={
        "csrf_token": csrf, "occurrence_id": str(ids["abc"]), "instruction": "", "return_to": "/bank/review"})
    check("20e. a plain form post (no script) redirects back and shows the refusal",
          form_post.status_code == 302 and form_post.headers["Location"].endswith("/bank/review")
          and "The rule is empty." in client.get("/bank/review").data.decode())
    offsite = client.post("/bank/who-rules/apply", data={
        "csrf_token": csrf, "occurrence_id": str(ids["abc"]), "instruction": "", "return_to": "https://example.com/x"})
    check("20f. the return target is always a Bank page", offsite.headers["Location"].endswith("/bank/classification"))
    check("20g. Apply requires the CSRF token",
          client.post("/bank/who-rules/apply", data={"occurrence_id": "1", "instruction": ABC_RULE}).status_code == 400)
    ungated = web_app.app.test_client()
    check("20h. the Rule routes are behind the BANK gate",
          ungated.get("/bank/who-rules/who-options?q=a").status_code in (302, 401, 403)
          and ungated.post("/bank/who-rules/apply").status_code in (302, 400, 401, 403))
    options = client.get("/bank/who-rules/who-options?q=top").get_json()
    summary = client.get(f"/bank/who-rules/who/{ids['abc']}").get_json()
    check("11c. the modal's WHO search lists ACTIVE WHO only; a WHO's summary pre-ticks its possible WHY",
          [o["name"] for o in options["matches"]] == ["Top Linen"]
          and sorted(summary["possible_why_ids"]) == sorted([ids["beer"], ids["liquor"]])
          and summary["rules"] == ["contains “ABC”"])

    who_rules.apply_who_rule = original_apply
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
