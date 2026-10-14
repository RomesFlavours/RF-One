"""WHO merge, single default WHY, upper-case names, Rules
(BANK_WHO_MERGE_001, BANK_WHO_SINGLE_DEFAULT_WHY_001, BANK_WHO_UPPERCASE_001).

Proves, on a throwaway database, that:

* a merge preview says what moves and asks about two different default WHY,
  writing nothing; the merge refuses without that choice; with it, EVERY
  reference to the absorbed WHO moves to the kept one (decisions of
  reconciled transactions, aliases, possible WHY, entities) without
  duplicates or loss; the absorbed WHO is inactive, not selectable, and its
  name finds the kept WHO;
* a WHO with one possible WHY (with a WHAT) gets it as default; with two the
  explicit choice stays; no transaction is touched;
* WHO names are stored upper case without outer spaces wherever they are
  created or renamed, and a case / space-only duplicate is refused or
  reused; the data migration normalizes existing names and reports
  collisions without merging them;
* the old Rules page (/bank/classification) is retired (BANK_RULES_RESET_001):
  it answers 404 and the Bank menu has no Rules tab.

BANK_OLD_RULES_REMOVAL_001: a merge no longer moves or counts recognition
rules, WHY rules, Standards, WHO recognitions or learning suggestions (that
rule system was removed from the product). So the fixtures that seeded
BankRecognitionRule / BankPatternSuggestion rows are gone, check 7 no longer
expects an impact "rules" count (it asserts the current impact keys instead),
check 9 covers only the references a merge still moves, check 13 keeps only
"entity not duplicated" (the rule-move part went), and check 14 keeps only
"the chosen default WHY stays" (the suggestion part went). Check numbers are
unchanged.

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_who_merge_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-who-merge-secret"

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
from rfone_data_store.bank_reconciliation import configuration as config_service  # noqa: E402
from rfone_data_store.bank_reconciliation import manual_reconciliation  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.bank_reconciliation import review_queues  # noqa: E402
from rfone_data_store.bank_reconciliation import who_rules  # noqa: E402
from rfone_data_store.bank_reconciliation import why_catalog  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
AUG = date(2026, 8, 12)
# The references a merge moves (BANK_OLD_RULES_REMOVAL_001: rules, WHY rules,
# Standards and WHO recognitions are no longer moved, so not listed).
REFS = (m.BankTransactionExplanation, m.BankOccurrenceAlias, m.BankOccurrenceReasonAssociation,
        m.BankOccurrenceReportingEntity, m.BankOccurrenceSupplier, m.BankEvidenceBypassAuthorization)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    try:
        with SessionFactory() as s:
            account_service.create_account(s, username="merger", display_name="Merger",
                                           password="MergePass123!", status="ACTIVE", is_admin=False)
            s.flush()
            operator = s.query(m.RFOneAccount).filter_by(username="merger").one()
            account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True,
                                              role_code=None)
            legal = m.LegalEntity(legal_name="Merge LLC", status="ACTIVE")
            s.add(legal)
            s.flush()
            entity = m.ReportingEntity(code="RE_M", name="Merge Entity", entity_type="LEGAL",
                                       legal_entity_id=legal.id, status="ACTIVE")
            checking = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                           display_name="Merge Checking", institution="CHASE", last_four="0044", currency="USD")
            s.add_all([entity, checking])
            s.flush()
            batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="seed.csv",
                                      raw_file_bytes=b"x", sha256="1" * 64, status="NORMALIZED",
                                      payment_instrument_id=checking.id)
            s.add(batch)
            s.flush()
            whys = s.scalars(select(m.BankTransactionReason).where(
                m.BankTransactionReason.status == "ACTIVE",
                m.BankTransactionReason.accounting_classification_id.is_not(None)).order_by(m.BankTransactionReason.id)).all()
            why_a, why_b, why_c = whys[0], whys[1], whys[2]
            no_what = config_service.create_why(s, name="No What Yet", description=None, what_id=None, active=True,
                                                reason_group_id=None) if hasattr(config_service, "create_why") else None
            s.commit()
            ids = {"why_a": why_a.id, "why_b": why_b.id, "why_c": why_c.id, "entity": entity.id,
                   "checking": checking.id, "batch": batch.id, "no_what": no_what.id if no_what else None}

        # ------------------------------------------------ upper-case names
        with SessionFactory() as s:
            created = manual_reconciliation.create_who(s, name="  amazon mktp  ")
            s.commit()
            keep_id = created.occurrence.id
            again = manual_reconciliation.create_who(s, name="Amazon Mktp")
            s.commit()
            absorb = config_service.save_who(s, occurrence_id=None, name=" amazon.com ", active=True, reason_ids=[],
                                             default_reason_id=None, reporting_entity_ids=[])
            s.commit()
            absorb_id = absorb.id
            names = {o.id: o.canonical_name for o in s.scalars(select(m.BankOccurrence))}
        check("1. a WHO name is stored upper case without outer spaces, from any creation path",
              names[keep_id] == "AMAZON MKTP" and names[absorb_id] == "AMAZON.COM", str(names))
        check("2. the same name in another case / with spaces is the same WHO (no duplicate)",
              again.reused and again.occurrence.id == keep_id)
        with SessionFactory() as s:
            try:
                config_service.save_who(s, occurrence_id=absorb_id, name="Amazon Mktp", active=True, reason_ids=[],
                                        default_reason_id=None, reporting_entity_ids=[])
                s.commit()
                dup = False
            except ValueError:
                s.rollback()
                dup = True
            renamed = config_service.save_who(s, occurrence_id=absorb_id, name="amazon.com", active=True,
                                              reason_ids=[], default_reason_id=None, reporting_entity_ids=[])
            s.commit()
        check("3. a rename that differs only by case from another WHO is refused; a rename is upper case",
              dup and renamed.canonical_name == "AMAZON.COM")

        # ------------------------------------------------ single default WHY
        with SessionFactory() as s:
            why_catalog.associate(s, occurrence_id=keep_id, transaction_reason_id=ids["why_a"], source="HUMAN")
            s.commit()
            d1 = s.get(m.BankOccurrence, keep_id).default_transaction_reason_id
            why_catalog.associate(s, occurrence_id=keep_id, transaction_reason_id=ids["why_c"], source="HUMAN")
            s.commit()
            d2 = s.get(m.BankOccurrence, keep_id).default_transaction_reason_id
        check("4. one possible WHY becomes the default; a second one keeps the explicit default",
              d1 == ids["why_a"] and d2 == ids["why_a"], str((d1, d2)))
        if ids["no_what"]:
            with SessionFactory() as s:
                lone = manual_reconciliation.create_who(s, name="lone vendor").occurrence
                why_catalog.associate(s, occurrence_id=lone.id, transaction_reason_id=ids["no_what"], source="HUMAN")
                s.commit()
                lone_default = s.get(m.BankOccurrence, lone.id).default_transaction_reason_id
            check("5. a single WHY with no WHAT yet is the default too (BANK_WHO_EDIT_SAVE_001)",
                  lone_default == ids["no_what"])

        # ------------------------------------------------ the absorbed WHO's references
        with SessionFactory() as s:
            absorb = s.get(m.BankOccurrence, absorb_id)
            why_catalog.associate(s, occurrence_id=absorb_id, transaction_reason_id=ids["why_b"], source="HUMAN")
            why_catalog.associate(s, occurrence_id=absorb_id, transaction_reason_id=ids["why_c"], source="HUMAN")
            absorb.default_transaction_reason_id = ids["why_b"]
            for who_id in (keep_id, absorb_id):
                s.add(m.BankOccurrenceAlias(occurrence_id=who_id, alias_text="AMZN MKTP US", alias_key="AMZN MKTP US",
                                            source_family="CARD_MERCHANT", source="HUMAN"))
                s.add(m.BankOccurrenceReportingEntity(occurrence_id=who_id, reporting_entity_id=ids["entity"]))
            s.add(m.BankOccurrenceAlias(occurrence_id=absorb_id, alias_text="AMAZON.COM*AB12", alias_key="AMAZON COM AB12",
                                        source_family="CARD_MERCHANT", source="PARSER"))
            txs = []
            for i in range(3):
                t = m.FinancialTransaction(
                    payment_instrument_id=ids["checking"], bank_source="CHASE_BANK_ACCOUNT", import_batch_id=ids["batch"],
                    posting_date=AUG, transaction_date=AUG, description_original=f"AMAZON.COM ORDER {i}",
                    description_normalized=f"AMAZON.COM ORDER {i}", amount_minor=-1000 - i, status="COMPLETED",
                    duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                    fingerprint=f"merge-{i}", classification="UNKNOWN")
                s.add(t)
                s.flush()
                recognition._create_decision_row(
                    s, t, occurrence_id=absorb_id, transaction_reason_id=None, decision_source="RULE", decision_status="NEEDS_HUMAN_REVIEW", confidence=None,
                    explanation_notes="first", accounting_destination_source=m.DESTINATION_SOURCE_WHY)
                recognition._create_decision_row(
                    s, t, occurrence_id=absorb_id, transaction_reason_id=ids["why_b"], decision_source="HUMAN", decision_status="HUMAN_CONFIRMED", confidence=None,
                    explanation_notes="reconciled", accounting_destination_source=m.DESTINATION_SOURCE_WHY)
                txs.append(t.id)
            s.commit()
            reconciled_before = review_queues.reconciled_ids(s, review_queues.ReviewFilters())
            snapshots = sorted(e.occurrence_name_snapshot or "" for e in s.scalars(select(m.BankTransactionExplanation).where(
                m.BankTransactionExplanation.occurrence_id == absorb_id)))
            assoc_before = {(a.transaction_reason_id): a.confirmation_count for a in s.scalars(
                select(m.BankOccurrenceReasonAssociation).where(m.BankOccurrenceReasonAssociation.occurrence_id.in_([keep_id, absorb_id])))}

        def refs(who_id):
            with SessionFactory() as s:
                return {model.__tablename__: s.scalar(select(func.count()).select_from(model).where(model.occurrence_id == who_id))
                        for model in REFS}

        client = web_app.app.test_client()
        csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
        client.post("/login", data={"username": "merger", "password": "MergePass123!", "csrf_token": csrf})
        page = client.get("/bank/configuration").data.decode()
        csrf = CSRF_RE.search(page).group(1)
        check("6. Configuration offers Merge on the WHO list, with its dialog",
              'id="cp-merge"' in page and "data-merge=" in page and "/who/merge/preview" in page)
        before = refs(absorb_id)
        prev = client.post("/bank/configuration/who/merge/preview", data={
            "csrf_token": csrf, "keep_id": keep_id, "absorb_id": absorb_id}).get_json()
        check("7. the preview names both WHO, the impact, and asks which default WHY stays; nothing written",
              prev["keep"]["name"] == "AMAZON MKTP" and prev["absorb"]["name"] == "AMAZON.COM"
              and prev["impact"]["transactions"] == 3 and prev["impact"]["decisions"] == 6
              and set(prev["impact"]) == {"transactions", "decisions", "aliases", "possible_why", "entities", "suppliers"}
              and [c["key"] for c in prev["conflicts"]] == ["default_why"] and refs(absorb_id) == before, str(prev))
        resp = client.post("/bank/configuration/who/merge", data={"csrf_token": csrf, "keep_id": keep_id, "absorb_id": absorb_id})
        check("8. without the default-WHY choice the merge is refused, nothing written",
              resp.status_code == 302 and refs(absorb_id) == before)
        resp = client.post("/bank/configuration/who/merge", data={
            "csrf_token": csrf, "keep_id": keep_id, "absorb_id": absorb_id, "default_why": ids["why_b"]})
        after = refs(absorb_id)
        check("9. every reference left the absorbed WHO (decisions, aliases, WHY, entities, …)",
              all(v == 0 for v in after.values()), str(after))
        with SessionFactory() as s:
            keep, gone = s.get(m.BankOccurrence, keep_id), s.get(m.BankOccurrence, absorb_id)
            currents = [recognition.get_current_explanation(s, financial_transaction_id=t) for t in txs]
            history = s.scalar(select(func.count(m.BankTransactionExplanation.id)).where(
                m.BankTransactionExplanation.financial_transaction_id.in_(txs)))
            snapshots_after = sorted(e.occurrence_name_snapshot or "" for e in s.scalars(select(m.BankTransactionExplanation).where(
                m.BankTransactionExplanation.financial_transaction_id.in_(txs))))
            aliases = sorted((a.alias_text, a.source_family) for a in s.scalars(select(m.BankOccurrenceAlias).where(
                m.BankOccurrenceAlias.occurrence_id == keep_id)))
            assoc = {a.transaction_reason_id: a.confirmation_count for a in s.scalars(select(m.BankOccurrenceReasonAssociation).where(
                m.BankOccurrenceReasonAssociation.occurrence_id == keep_id))}
            entities = s.scalar(select(func.count()).select_from(m.BankOccurrenceReportingEntity).where(
                m.BankOccurrenceReportingEntity.occurrence_id == keep_id))
            reconciled_after = review_queues.reconciled_ids(s, review_queues.ReviewFilters())
            resolved, _name = who_rules.check_new_who(s, "amazon.com")
        check("10. reconciled transactions now name the kept WHO, keep their WHY, stay reconciled; history and snapshots intact",
              all(c.occurrence_id == keep_id and c.transaction_reason_id == ids["why_b"] and c.decision_source == "HUMAN" for c in currents)
              and history == 6 and snapshots_after == snapshots and reconciled_after == reconciled_before)
        check("11. aliases merged without duplicate; the absorbed name is an alias of the kept WHO",
              aliases == sorted([("AMZN MKTP US", "CARD_MERCHANT"), ("AMAZON.COM*AB12", "CARD_MERCHANT"),
                                 ("AMAZON.COM", "MERGED_WHO_NAME")]), str(aliases))
        check("12. possible WHY merged, one row per WHY, confirmations added",
              set(assoc) == {ids["why_a"], ids["why_b"], ids["why_c"]} and assoc[ids["why_c"]] == 2, str((assoc, assoc_before)))
        check("13. entity not duplicated",
              entities == 1, str(entities))
        check("14. the chosen default WHY stays",
              keep.default_transaction_reason_id == ids["why_b"])
        check("15. the absorbed WHO is inactive (not selectable) and its name finds the kept WHO",
              gone.status == "INACTIVE" and "Merged into 'AMAZON MKTP'" in (gone.optional_notes or "")
              and resolved is not None and resolved.id == keep_id
              and all(w["id"] != absorb_id for w in client.get("/bank/manual-reconciliation/whos").get_json()))
        resp = client.post("/bank/configuration/who/merge/preview", data={"csrf_token": csrf, "keep_id": keep_id, "absorb_id": absorb_id})
        check("16. merging it again is refused (already merged)", resp.status_code == 400)

        # ------------------------------------------------ Rules (retired)
        # BANK_RULES_RESET_001 — the old Rules page is gone, and so is its tab.
        retired = client.get("/bank/classification")
        menu = client.get("/bank/review").data.decode()
        check("17. the retired Rules page answers 404 and is not in the Bank menu",
              retired.status_code == 404 and ">Rules</a>" not in menu and ">Classification</a>" not in menu
              and ">AI Rules</a>" in menu, str(retired.status_code))

        # ------------------------------------------------ the data migration
        from alembic import command
        from alembic.config import Config
        cfg = Config(os.path.join(_DATA_STORE_DIR, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(_DATA_STORE_DIR, "migrations"))
        os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = os.environ["RFONE_DATABASE_URL"]
        cfg.set_main_option("sqlalchemy.url", os.environ["RFONE_DATABASE_URL"])
        command.downgrade(cfg, "f3b7d9a1c5e8")
        with SessionFactory() as s:
            counterparty = s.scalars(select(m.BankOccurrence.occurrence_type_id)).first()
            for name in ("  mixed Case Vendor ", "Twin Name", "TWIN NAME "):
                s.add(m.BankOccurrence(canonical_name=name, occurrence_type_id=counterparty, status="ACTIVE"))
            single = m.BankOccurrence(canonical_name="Single Why", occurrence_type_id=counterparty, status="ACTIVE")
            s.add(single)
            s.flush()
            s.add(m.BankOccurrenceReasonAssociation(occurrence_id=single.id, transaction_reason_id=ids["why_a"], active=True,
                                                    confirmation_count=1, source="HUMAN"))
            s.commit()
        command.upgrade(cfg, "head")
        os.environ.pop("ALEMBIC_DATABASE_URL_OVERRIDE", None)
        with SessionFactory() as s:
            stored = sorted(o.canonical_name for o in s.scalars(select(m.BankOccurrence)))
            single_default = s.scalars(select(m.BankOccurrence).where(
                m.BankOccurrence.canonical_name == "SINGLE WHY")).one().default_transaction_reason_id
        check("18. the migration upper-cases existing names, keeps ids, leaves a would-be duplicate pair for a person",
              "MIXED CASE VENDOR" in stored and "Twin Name" in stored and "TWIN NAME " in stored
              and "SINGLE WHY" in stored, str(stored))
        check("19. the migration sets the default of a WHO with one possible WHY", single_default == ids["why_a"])
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    if failed:
        print("FAILED CHECKS:")
        for description in failed:
            print(f"  - {description}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
