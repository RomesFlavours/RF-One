"""The Rule modal creates its own WHO (BANK_SIMPLE_WHO_RULE_001, WHO creation).

Proves, on a throwaway database, that from the one Rule modal — on Review and
on Classification — the operator can pick an existing WHO or create a new one,
and that Apply then creates the WHO (through the Configuration service, as a
COUNTERPARTY with no default WHY), its possible WHY, its rule and the rule's
application in ONE transaction: any failure leaves no WHO without its rule
and no rule without its WHO. Exact identities are reused, look-alike names
are only offered, human decisions and Standards are preserved.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import time
from datetime import date, datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_rule_modal_who_creation_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-rule-modal-who-creation-secret"

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
from rfone_data_store.bank_reconciliation import configuration  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.bank_reconciliation import service as bank_service  # noqa: E402
from rfone_data_store.bank_reconciliation import who_recognition as wr  # noqa: E402
from rfone_data_store.bank_reconciliation import who_rules  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
DAY = date(2026, 8, 3)
RECOGNIZED = "Recognised by who-v1 from the bank's own text (ACH_ORIGINATOR). Identity only."
CANONICAL = "Canonical WHO from the WHO/WHY import."
NEW_WHO = "Table Top Linen - WP"
TTL_RULE = f'Dove nella descrizione trovi "TABLE TOP LINEN" il WHO è {NEW_WHO}'
FUTURE_CSV = (
    "Card,Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
    "1057,08/20/2026,08/21/2026,TABLE TOP LINEN WEEKLY 7788,Services,Sale,-91.00,\n"
)


def ttl(n: int) -> str:
    return f"ORIG CO NAME:TABLE TOP LINEN        ORIG ID:1900922218 CO ENTRY DESCR:WEEK {n:02d}"


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="who_creator", display_name="Who Creator",
                                       password="WhoCreator123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="who_creator").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        legal = m.LegalEntity(legal_name="Who Creation LLC", status="ACTIVE")
        s.add(legal)
        s.flush()
        reporting = m.ReportingEntity(code="RE_WHO_CREATION", name="Who Creation", entity_type="LEGAL",
                                      legal_entity_id=legal.id, status="ACTIVE")
        card = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="CREDIT_CARD",
                                   display_name="Chase Card 1057", institution="CHASE", last_four="1057",
                                   currency="USD")
        s.add_all([reporting, card])
        s.flush()
        batch = m.BankImportBatch(detected_format="CHASE_CREDIT_CARD_WITH_CARD", original_file_name="seed.csv",
                                  raw_file_bytes=b"x", sha256="3" * 64, status="NORMALIZED",
                                  payment_instrument_id=card.id)
        s.add(batch)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        generic = m.BankOccurrenceType(code="GENERIC_OPERATIONAL", name="Generic Operational")
        s.add(generic)
        s.flush()
        reasons = {code: s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.code == code)).one()
                   for code in ("BEER_PURCHASES", "LIQUOR_PURCHASES")}
        linen_reason = s.scalars(select(m.BankTransactionReason).where(
            m.BankTransactionReason.status == "ACTIVE",
            m.BankTransactionReason.accounting_classification_id.is_not(None),
            m.BankTransactionReason.name.ilike("%clean%") | m.BankTransactionReason.name.ilike("%linen%")
            | m.BankTransactionReason.name.ilike("%laundry%")).order_by(m.BankTransactionReason.name)).first()

        def who(name, *, notes=RECOGNIZED, status="ACTIVE"):
            o = m.BankOccurrence(canonical_name=name, occurrence_type_id=counterparty.id, status=status,
                                 optional_notes=notes)
            s.add(o)
            s.flush()
            return o

        ttl_fragment = who("TABLE TOP LINEN")
        table_top_canonical = who("Table Top Linen", notes=CANONICAL)       # look-alike, curated
        gordon = who("Gordon Food Service", notes=CANONICAL)
        abc = who("ABC", notes=CANONICAL)
        abc_fragments = [who(n) for n in ("ABC FINE WINE S", "ABC FINE WINE SPIRITS 071")]
        publix = who("Publix", notes=CANONICAL)
        s.add(m.BankOccurrenceAlias(occurrence_id=publix.id, alias_text="PUBLIX SUPER MARKETS",
                                    alias_key=wr.who_key("PUBLIX SUPER MARKETS"), source_family="MERGED_WHO_NAME",
                                    source="HUMAN"))
        for n in range(70):
            who(f"FILLER VENDOR {n:03d}")
        s.flush()

        seq = [0]

        def tx(description, recognized, *, decision=None, reason=None, standard=None):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=card.id, bank_source="CHASE_CREDIT_CARD_WITH_CARD", import_batch_id=batch.id,
                posting_date=DAY, transaction_date=DAY, description_original=description,
                description_normalized=description, amount_minor=-1000 - seq[0], status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"who-creation-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            s.add(m.BankWhoRecognition(
                financial_transaction_id=t.id, recognizer_version=wr.RECOGNIZER_VERSION, tier=wr.DETERMINISTIC,
                family="ACH_ORIGINATOR", parser_code="ACH_ORIG_CO_NAME", extracted_name=recognized.canonical_name,
                occurrence_id=recognized.id, evidence="ACH originator field ORIG CO NAME"))
            if decision is not None:
                source, occurrence = decision
                recognition._create_decision_row(
                    s, t, occurrence_id=occurrence.id, transaction_reason_id=reason.id if reason else None,
                    recognition_rule_id=None, decision_source=source,
                    decision_status="HUMAN_CONFIRMED" if source == "HUMAN" else (
                        "AUTO_APPLIED" if standard else "NEEDS_HUMAN_REVIEW"),
                    confidence="HIGH" if reason else None, explanation_notes="seed",
                    confirmed_by_account_id=operator.id if source == "HUMAN" else None,
                    accounting_classification_id=reason.accounting_classification_id if standard else None,
                    accounting_destination_source=m.DESTINATION_SOURCE_STANDARD if standard else m.DESTINATION_SOURCE_WHY,
                    reconciliation_standard_id=standard.id if standard else None)
            s.flush()
            return t

        standard = m.BankReconciliationStandard(
            match_type=recognition.EXACT_NORMALIZED_DESCRIPTION,
            normalized_pattern=recognition.normalize_description_for_recognition(ttl(99)),
            match_field=recognition.DESCRIPTION, occurrence_id=gordon.id,
            transaction_reason_id=reasons["BEER_PURCHASES"].id,
            accounting_classification_id=reasons["BEER_PURCHASES"].accounting_classification_id,
            reporting_entity_id=reporting.id, status="ACTIVE", approved_by_account_id=operator.id,
            approved_at=datetime.now(timezone.utc))
        s.add(standard)
        s.flush()
        ttl_tx = [tx(ttl(1), ttl_fragment), tx(ttl(2), ttl_fragment, decision=("RULE", ttl_fragment)),
                  tx(ttl(3), ttl_fragment)]
        human_tx = tx(ttl(4), ttl_fragment, decision=("HUMAN", gordon), reason=reasons["LIQUOR_PURCHASES"])
        standard_tx = tx(ttl(99), ttl_fragment, decision=("RULE", gordon), reason=reasons["BEER_PURCHASES"],
                         standard=standard)
        abc_tx = [tx("ABC FINE WINE/S WINTER PARK FL", abc_fragments[0]),
                  tx("ABC FINE WINE SPIRITS 071 ORLANDO", abc_fragments[1])]
        s.commit()
        ids = {
            "ttl_fragment": ttl_fragment.id, "table_top_canonical": table_top_canonical.id, "gordon": gordon.id,
            "abc": abc.id, "publix": publix.id, "card": card.id,
            "beer": reasons["BEER_PURCHASES"].id, "liquor": reasons["LIQUOR_PURCHASES"].id,
            "linen_why": linen_reason.id if linen_reason else reasons["BEER_PURCHASES"].id,
            "ttl_tx": [t.id for t in ttl_tx], "human_tx": human_tx.id, "standard_tx": standard_tx.id,
            "abc_tx": [t.id for t in abc_tx], "standard": standard.id,
        }
        standard_rows_before = sorted(s.execute(select(m.BankReconciliationStandard.id,
                                                       m.BankReconciliationStandard.occurrence_id,
                                                       m.BankReconciliationStandard.status)).all())

    def counts():
        with SessionFactory() as s:
            return {
                "who": s.scalar(select(func.count(m.BankOccurrence.id))),
                "rules": s.scalar(select(func.count(m.BankRecognitionRule.id))),
                "assoc": s.scalar(select(func.count(m.BankOccurrenceReasonAssociation.id))),
                "decisions": s.scalar(select(func.count(m.BankTransactionExplanation.id))),
                "inactive": s.scalar(select(func.count(m.BankOccurrence.id)).where(m.BankOccurrence.status == "INACTIVE")),
            }

    def no_orphans() -> bool:
        with SessionFactory() as s:
            rules_ok = all(s.get(m.BankOccurrence, r.occurrence_id) is not None
                           for r in s.scalars(select(m.BankRecognitionRule)))
            created = s.scalars(select(m.BankOccurrence).where(m.BankOccurrence.optional_notes.is_(None))).all()
            whos_ok = all(s.scalar(select(func.count(m.BankRecognitionRule.id)).where(
                m.BankRecognitionRule.occurrence_id == o.id)) for o in created)
            return rules_ok and whos_ok

    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "who_creator", "password": "WhoCreator123!", "csrf_token": csrf})

    def options(text):
        return client.get("/bank/who-rules/who-options", query_string={"q": text}).get_json()

    def apply(*, instruction, occurrence_id=None, new_who=None, whys=(), transaction_id=None,
              return_to="/bank/review"):
        data = {"csrf_token": csrf, "instruction": instruction, "return_to": return_to,
                "transaction_reason_id": [str(w) for w in whys]}
        if occurrence_id:
            data["occurrence_id"] = str(occurrence_id)
        if new_who:
            data["new_who_name"] = new_who
        if transaction_id:
            data["transaction_id"] = str(transaction_id)
        return client.post("/bank/who-rules/apply", data=data, headers={"X-Requested-With": "fetch"})

    # ------------------------------------------------------------------
    # The pages carry the same creatable modal
    # ------------------------------------------------------------------
    start = time.perf_counter()
    classification = client.get("/bank/classification").data.decode()
    classification_time = time.perf_counter() - start
    csrf = CSRF_RE.search(classification).group(1)
    start = time.perf_counter()
    review = client.get("/bank/review").data.decode()
    review_time = time.perf_counter() - start

    def modal_of(html):
        return html[html.index('id="who-rule-modal"'):html.index("bank-who-rule.js")]

    check("5/6. Review and Classification carry the same creatable WHO modal (new-WHO field, same script, same route)",
          all('id="who-rule-new-who-name"' in h and "bank-who-rule.js?v=5" in h and 'action="/bank/who-rules/apply"' in h
              for h in (classification, review))
          and modal_of(classification).split("csrf_token")[0] == modal_of(review).split("csrf_token")[0])
    check("35. no WHO list is rendered into the Rule modal (the combo is fetched lazily)",
          'class="who-option' not in modal_of(classification) and 'class="who-option' not in modal_of(review))

    # ------------------------------------------------------------------
    # EXISTING WHO (1-3)
    # ------------------------------------------------------------------
    found = options("gordon")
    check("1. an existing WHO is searchable", [o["name"] for o in found["matches"]] == ["Gordon Food Service"])
    check("2. an existing WHO is offered as itself (selectable), and no Create for its own name",
          options("Gordon Food Service")["identity"]["id"] == ids["gordon"]
          and options("Gordon Food Service")["create"] is None)
    abc_result = apply(occurrence_id=ids["abc"], instruction="Dove nella descrizione trovi ABC il WHO è ABC",
                       whys=(ids["beer"], ids["liquor"]), return_to="/bank/classification?q=ABC")
    with SessionFactory() as s:
        abc_ok = all(s.get(m.FinancialTransaction, t).explanation_id and s.get(
            m.BankTransactionExplanation, s.get(m.FinancialTransaction, t).explanation_id).occurrence_id == ids["abc"]
            for t in ids["abc_tx"])
        abc_whys = {a.transaction_reason_id for a in s.scalars(select(m.BankOccurrenceReasonAssociation).where(
            m.BankOccurrenceReasonAssociation.occurrence_id == ids["abc"]))}
    check("3/29. Apply with an existing WHO (the ABC rule) still works",
          abc_result.status_code == 200 and abc_ok, detail=str(abc_result.get_json()))
    check("30. ABC's possible WHY are Beer + Liquor", abc_whys == {ids["beer"], ids["liquor"]})
    abc_page = client.get("/bank/classification?q=ABC").data.decode()
    check("29b. ABC collapses to one row and shows 'WHO status: Existing'",
          re.findall(r'data-subject="Occurrence: ([^"]+)"', abc_page) == ["ABC"]
          and "<dt>WHO status</dt><dd>Existing</dd>" in abc_page)

    # ------------------------------------------------------------------
    # NEW WHO offered (4, 18) and duplicate safety (16, 17)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        check("19. no WHO named 'Table Top Linen - WP' exists yet",
              not s.scalar(select(func.count(m.BankOccurrence.id)).where(m.BankOccurrence.canonical_name == NEW_WHO)))
    typed = options(NEW_WHO)
    check("4/20. an unknown WHO text offers Create \"Table Top Linen - WP\"",
          typed["create"] == NEW_WHO and typed["identity"] is None)
    check("18. look-alike WHO are shown as suggestions, never auto-selected",
          {o["name"] for o in typed["similar"]} >= {"Table Top Linen", "TABLE TOP LINEN"} and typed["identity"] is None)
    check("16. an exact existing canonical WHO is offered instead of Create (case/spacing ignored)",
          options("  abc ")["identity"]["id"] == ids["abc"] and options("  abc ")["create"] is None)
    check("17. an alias-equivalent name resolves to its WHO, without Create",
          options("Publix Super Markets")["identity"]["id"] == ids["publix"]
          and options("Publix Super Markets")["create"] is None)
    before = counts()
    reuse = apply(new_who="Publix Super Markets", instruction='Dove nella descrizione trovi "PUBLIX" il WHO è Publix')
    after_reuse = counts()
    check("16b/17b. Apply asked to create an existing identity reuses that WHO — no duplicate",
          reuse.status_code == 200 and after_reuse["who"] == before["who"])

    # ------------------------------------------------------------------
    # ATOMICITY (11-15)
    # ------------------------------------------------------------------
    original_save_rule = who_rules._save_rule
    original_apply_tx = who_rules._apply_to_transaction

    def failing_rule(*_args, **_kwargs):
        raise ValueError("Simulated failure while saving the rule.")

    def failing_tx(*_args, **_kwargs):
        raise ValueError("Simulated failure while applying the rule.")

    snapshot = counts()
    who_rules._save_rule = failing_rule
    failed_rule = apply(new_who="Rollback Linen One", instruction='Dove nella descrizione trovi "TABLE TOP LINEN" il WHO è Rollback Linen One')
    who_rules._save_rule = original_save_rule
    with SessionFactory() as s:
        none_one = not s.scalar(select(func.count(m.BankOccurrence.id)).where(
            m.BankOccurrence.canonical_name == "Rollback Linen One"))
    check("12. a failure while saving the rule rolls back the WHO creation",
          failed_rule.status_code == 400 and none_one and counts() == snapshot)
    who_rules._apply_to_transaction = failing_tx
    failed_tx = apply(new_who="Rollback Linen Two", whys=(ids["linen_why"],),
                      instruction='Dove nella descrizione trovi "TABLE TOP LINEN" il WHO è Rollback Linen Two')
    who_rules._apply_to_transaction = original_apply_tx
    with SessionFactory() as s:
        none_two = not s.scalar(select(func.count(m.BankOccurrence.id)).where(
            m.BankOccurrence.canonical_name == "Rollback Linen Two"))
        fragment_still_active = s.get(m.BankOccurrence, ids["ttl_fragment"]).status == "ACTIVE"
    check("13. a failure while applying to transactions rolls back WHO, WHY, rule and merges",
          failed_tx.status_code == 400 and none_two and counts() == snapshot and fragment_still_active)

    def crashing_tx(*_args, **_kwargs):
        raise RuntimeError("Simulated unexpected crash.")

    who_rules._apply_to_transaction = crashing_tx
    crashed = apply(new_who="Rollback Linen Three",
                    instruction='Dove nella descrizione trovi "TABLE TOP LINEN" il WHO è Rollback Linen Three')
    who_rules._apply_to_transaction = original_apply_tx
    check("13b. an unexpected crash also leaves nothing behind", crashed.status_code == 500 and counts() == snapshot)
    mismatch = apply(new_who=NEW_WHO, instruction='Dove nella descrizione trovi "TABLE TOP LINEN" il WHO è Top Linen Co')
    check("9b. the WHO named in the sentence must be the one being created — else a clear error, nothing created",
          mismatch.status_code == 400 and "new WHO" in mismatch.get_json()["error"] and counts() == snapshot)
    check("14/15. no orphan WHO and no orphan rule after the failures", no_orphans())

    # ------------------------------------------------------------------
    # TABLE TOP LINEN ACCEPTANCE (19-28), from Review
    # ------------------------------------------------------------------
    calls = []
    original_apply = who_rules.apply_who_rule

    def spy(*args, **kwargs):
        calls.append(kwargs.get("new_who_name"))
        return original_apply(*args, **kwargs)

    who_rules.apply_who_rule = spy
    created = apply(new_who=NEW_WHO, instruction=TTL_RULE, whys=(ids["linen_why"],),
                    transaction_id=ids["ttl_tx"][0], return_to="/bank/review")
    who_rules.apply_who_rule = original_apply
    result_page = client.get("/bank/review").data.decode()
    with SessionFactory() as s:
        new = s.scalars(select(m.BankOccurrence).where(m.BankOccurrence.canonical_name == NEW_WHO)).one_or_none()
        check("21/24/25. Create + Apply from Review creates the WHO (one service call, one commit)",
              created.status_code == 200 and new is not None and new.status == "ACTIVE" and calls == [NEW_WHO],
              detail=str(created.get_json()))
        check("7/8. the WHO comes from the Configuration service: COUNTERPARTY, never GENERIC_OPERATIONAL",
              new.occurrence_type_id == s.scalar(select(m.BankOccurrenceType.id).where(
                  m.BankOccurrenceType.code == configuration.COUNTERPARTY_TYPE_CODE))
              and new.optional_notes is None)
        new_whys = {a.transaction_reason_id for a in s.scalars(select(m.BankOccurrenceReasonAssociation).where(
            m.BankOccurrenceReasonAssociation.occurrence_id == new.id, m.BankOccurrenceReasonAssociation.active))}
        check("9/23. the selected possible WHY is associated", new_whys == {ids["linen_why"]})
        check("10. no default WHY is invented", new.default_transaction_reason_id is None)
        rule = s.scalars(select(m.BankRecognitionRule).where(m.BankRecognitionRule.occurrence_id == new.id)).one()
        check("22/11. the rule is 'description contains TABLE TOP LINEN', WHO-only, committed with its WHO",
              rule.normalized_pattern == "TABLE TOP LINEN" and rule.match_type == recognition.CONTAINS_TEXT
              and rule.determines_purpose is False and rule.transaction_reason_id is None
              and rule.created_from_transaction_id == ids["ttl_tx"][0])

        def current(tx_id):
            t = s.get(m.FinancialTransaction, tx_id)
            return s.get(m.BankTransactionExplanation, t.explanation_id) if t.explanation_id else None

        check("26. every safe matching transaction receives the new WHO, with no WHY chosen",
              all(current(t).occurrence_id == new.id and current(t).transaction_reason_id is None
                  for t in ids["ttl_tx"]))
        human = current(ids["human_tx"])
        check("31. a conflicting human decision is preserved",
              human.decision_source == "HUMAN" and human.occurrence_id == ids["gordon"]
              and human.transaction_reason_id == ids["liquor"])
        std = current(ids["standard_tx"])
        check("32. a Standard decision is preserved, and the Standard itself is unchanged",
              std.reconciliation_standard_id == ids["standard"] and std.occurrence_id == ids["gordon"]
              and sorted(s.execute(select(m.BankReconciliationStandard.id, m.BankReconciliationStandard.occurrence_id,
                                          m.BankReconciliationStandard.status)).all()) == standard_rows_before)
        check("26b. the raw TABLE TOP LINEN fragment is merged; the curated look-alike 'Table Top Linen' is not",
              s.get(m.BankOccurrence, ids["ttl_fragment"]).status == "INACTIVE"
              and s.get(m.BankOccurrence, ids["table_top_canonical"]).status == "ACTIVE")
    check("9c. the result says Created, the rule, the counts and the WHY added — no database id",
          "<dt>WHO status</dt><dd>Created</dd>" in result_page and "TABLE TOP LINEN" in result_page
          and "<dt>Human conflicts preserved</dt><dd>2</dd>" in result_page
          and "<dt>Possible WHY added</dt>" in result_page)
    check("14b/15b. still no orphan WHO and no orphan rule", no_orphans())

    before_second = counts()
    again = apply(new_who=NEW_WHO, instruction=TTL_RULE, whys=(ids["linen_why"],))
    again_body = again.get_json()
    check("28. a second Apply (Create again, same name) is idempotent: the WHO is reused, 0 business changes",
          again.status_code == 200 and counts() == before_second
          and "Nothing new to change" in client.get("/bank/review").data.decode(), detail=str(again_body))

    with SessionFactory() as s:
        new_id = s.scalars(select(m.BankOccurrence.id).where(m.BankOccurrence.canonical_name == NEW_WHO)).one()
        upload = bank_service.import_csv(s, file_bytes=FUTURE_CSV.encode("utf-8"),
                                         original_file_name="chase1057_ttl_future.csv", uploaded_by_account_id=None,
                                         payment_instrument_id=ids["card"])
        s.commit()
        imported = s.scalars(select(m.FinancialTransaction).where(
            m.FinancialTransaction.import_batch_id == upload.batch.id)).one()
        decided = recognition.get_current_explanation(s, financial_transaction_id=imported.id)
        resolved = wr.CanonicalWhoResolver(s).resolve(None, description="TABLE TOP LINEN WEEKLY 7788",
                                                      amount_minor=-9100, instrument_id=ids["card"])
    check("27. a future TABLE TOP LINEN transaction receives the new WHO (import and resolver)",
          decided is not None and decided.occurrence_id == new_id
          and resolved.occurrence is not None and resolved.occurrence.id == new_id)

    classification_after = client.get("/bank/classification?q=table top").data.decode()
    rows = re.findall(r'data-subject="Occurrence: ([^"]+)"', classification_after)
    check("Classification shows one 'Table Top Linen - WP' row; the merged fragment is hidden",
          rows.count(NEW_WHO) == 1 and "TABLE TOP LINEN" not in rows, detail=str(rows))

    # ------------------------------------------------------------------
    # PERFORMANCE (33-34)
    # ------------------------------------------------------------------
    check("33. Classification stays fast", classification_time < 2.0, detail=f"{classification_time:.2f}s")
    check("34. Review stays responsive", review_time < 5.0, detail=f"{review_time:.2f}s")
    start = time.perf_counter()
    options("table")
    check("33b. the WHO combo lookup answers quickly", time.perf_counter() - start < 1.0)

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
