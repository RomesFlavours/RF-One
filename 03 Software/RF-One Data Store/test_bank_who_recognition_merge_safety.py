#!/usr/bin/env python
"""WHO recognition is merge-safe (BANK_WHO_WHY_CANONICAL_CATALOG_001).

The canonical WHO/WHY import renames WHO to their clean names, moves every
fragment's aliases onto the canonical WHO, records each fragment's old name
as an alias, and marks the fragments INACTIVE. This suite proves, on a
throwaway database shaped exactly that way, that re-running WHO recognition
afterwards:

* reuses the active canonical WHO by name or by alias;
* never recreates a merged fragment and never reactivates an INACTIVE WHO;
* holds for a person anything it cannot resolve safely;
* still creates a genuinely new COUNTERPARTY, and never a GENERIC_OPERATIONAL;
* keeps alias history and moves no reference back onto a fragment;
* applies an approved description rule within its own direction — the Wix
  Payment Online CREDIT goes to Giftedd, a Wix DEBIT stays Wix;
* never determines a WHY (BANK_WHO_WHY_INVARIANT_001);
* is idempotent.

Never touches AWS, RDS, the operational database, or a real bank file.
"""

from __future__ import annotations

import sys
from datetime import date

from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import who_recognition as wr
from rfone_data_store.database import (
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)

DAY = date(2026, 9, 15)


def ach(name: str) -> str:
    return (f"ORIG CO NAME:{name:<22}ORIG ID:1234567890 DESC DATE:       "
            "CO ENTRY DESCR:PAYMENT   SEC:CCD    TRACE#:111000015742249")


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
            print(f"  PASS  {description}")
        else:
            failed.append(description)
            print(f"  FAIL  {description}" + (f" ({detail})" if detail else ""))

    url = resolve_test_database_url("who_recognition_merge_safety")
    print(f"Database: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as s:
            counterparty = s.scalars(select(m.BankOccurrenceType).where(
                m.BankOccurrenceType.code == "COUNTERPARTY")).one()
            generic = m.BankOccurrenceType(code="GENERIC_OPERATIONAL", name="Generic Operational")
            s.add(generic)
            own = m.LegalEntity(legal_name="Angeli E Demoni, LLC", status="ACTIVE")
            s.add(own)
            s.flush()
            checking = m.PaymentInstrument(instrument_type="BANK_ACCOUNT", display_name="Checking",
                                           institution="Chase", last_four="3376", legal_entity_id=own.id)
            s.add(checking)
            s.flush()
            batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="t.csv",
                                      raw_file_bytes=b"x", sha256="0" * 64, payment_instrument_id=checking.id)
            s.add(batch)
            s.flush()

            def who(name, status="ACTIVE", type_=counterparty, notes=None):
                o = m.BankOccurrence(canonical_name=name, occurrence_type_id=type_.id, status=status,
                                     optional_notes=notes)
                s.add(o)
                s.flush()
                return o

            def alias(o, text, family="ACH_ORIGINATOR"):
                s.add(m.BankOccurrenceAlias(occurrence_id=o.id, alias_text=text, alias_key=wr.who_key(text),
                                            source_family=family, source="HUMAN"))

            def merged(canonical, fragment_name):
                """The state the canonical import leaves: fragment INACTIVE, its spelling an alias of the canonical."""
                fragment = who(fragment_name, status="INACTIVE",
                               notes=f"Merged into '{canonical.canonical_name}' (#{canonical.id}).")
                alias(canonical, fragment_name)
                alias(canonical, fragment_name, family="MERGED_WHO_NAME")
                return fragment

            # Canonical WHO, as the approved import leaves them.
            gordon = who("Gordon Food Service")
            gfs_fragment = merged(gordon, "GORDON FOOD SERV")
            publix = who("Publix")                                  # renamed from "PUBLIX"
            alias(publix, "PUBLIX", family="MERGED_WHO_NAME")
            publix_fragment = merged(publix, "PUBLIX SUPER MA")
            costco = who("Costco")
            costco_fragment = merged(costco, "COSTCO WHSE 0183")
            fcb = who("First Citizens Bank")                        # renamed from "FIRST CITIZENS BANK"
            fcb_fragment = merged(fcb, "FRST BK MRCH SVC")
            abc = who("ABC")
            abc_fragment = merged(abc, "ABC FINE WINE S")
            cheney = who("CHENEY BROTHERS")                         # an untouched exact canonical name
            wix = who("Wix")
            wix_fragment = merged(wix, "WIX.COM, INC. 415-6399034")
            giftedd = who("Giftedd")
            car_gas = who("Car-Gas", type_=generic)                 # configured GENERIC_OPERATIONAL knowledge
            orphan = who("OLD MERGED VENDOR", status="INACTIVE", notes="merged earlier; target not recorded")
            twin_a, twin_b = who("Twin Vendor A"), who("Twin Vendor B")
            alias(twin_a, "SHARED VENDOR")
            alias(twin_b, "SHARED VENDOR")
            s.add(m.BankRecognitionRule(
                match_type="PREFIX", normalized_pattern="WIXCOM WIX PAYMEN", match_field="DESCRIPTION",
                determines_purpose=False, direction="CREDIT", occurrence_id=giftedd.id,
                transaction_reason_id=None, priority=0, status="ACTIVE", auto_apply_enabled=True,
                human_confirmations=1, human_contradictions=0,
            ))
            s.flush()

            rows = {
                "gordon": (ach("GORDON FOOD SERV"), -90000),
                "publix_name": (ach("PUBLIX"), -2000),
                "publix_alias": (ach("PUBLIX SUPER MA"), -3000),
                "costco": (ach("COSTCO WHSE 0183"), -4000),
                "fcb": (ach("FRST BK MRCH SVC"), 50000),
                "abc": (ach("ABC FINE WINE S"), -6000),
                "cheney": (ach("CHENEY BROTHERS"), -7000),
                "orphan": (ach("OLD MERGED VENDOR"), -8000),
                "shared": (ach("SHARED VENDOR"), -9000),
                "new": ("Zelle payment to Charlize Irizarry JPM99b5p8jv0", -5000),
                "wix_credit": ("Wixcom Wix Paymen ST-F*W*T1A0L0F6", 17624),
                "wix_debit": ("POS SIG 07/01 VISA #5363 Wix.Com, Inc. 415-6399034 CA", -4500),
                "wix_pattern_debit": ("Wixcom Wix Paymen ST-Q*Q*Q1Q1Q1Q1", -1500),
                "car_gas_unknown": ("Some Unknown Car Gas Line 4411", -3300),
            }
            tx = {}
            for index, (key, (description, amount)) in enumerate(rows.items()):
                t = m.FinancialTransaction(
                    payment_instrument_id=checking.id, posting_date=DAY, transaction_date=DAY,
                    description_original=description, amount_minor=amount, status="COMPLETED",
                    classification="UNKNOWN", import_batch_id=batch.id, fingerprint=f"fp{index}:0")
                s.add(t)
                s.flush()
                tx[key] = t.id
            # A stale recognition still pointing at a merged fragment, as if made before the merge.
            s.add(m.BankWhoRecognition(
                financial_transaction_id=tx["gordon"], recognizer_version=wr.RECOGNIZER_VERSION,
                tier=wr.DETERMINISTIC, family="ACH_ORIGINATOR", parser_code="ACH_ORIG_CO_NAME",
                extracted_name="GORDON FOOD SERV", occurrence_id=gfs_fragment.id, evidence="before the merge"))
            s.commit()

            fragments = {gfs_fragment.id, publix_fragment.id, costco_fragment.id, fcb_fragment.id,
                         abc_fragment.id, wix_fragment.id, orphan.id}
            occurrences_before = s.scalar(select(func.count(m.BankOccurrence.id)))
            alias_rows_before = set(s.execute(select(
                m.BankOccurrenceAlias.id, m.BankOccurrenceAlias.occurrence_id, m.BankOccurrenceAlias.alias_text,
                m.BankOccurrenceAlias.alias_key, m.BankOccurrenceAlias.source_family)).all())
            rules_before = s.execute(select(m.BankRecognitionRule.id, m.BankRecognitionRule.occurrence_id,
                                            m.BankRecognitionRule.direction)).all()

            summary, _results = wr.recognize_transactions(s)
            s.commit()
            rec = {r.financial_transaction_id: r for r in s.scalars(select(m.BankWhoRecognition))}
            on = lambda key: rec[tx[key]].occurrence_id

            check("12. an active canonical WHO with the exact name is reused", on("cheney") == cheney.id)
            check("12b. a renamed canonical WHO is reused by its identity key (PUBLIX -> Publix)",
                  on("publix_name") == publix.id)
            check("13. an alias resolves to its active canonical WHO "
                  "(Publix / Costco / First Citizens / Gordon / ABC fragments)",
                  [on(k) for k in ("publix_alias", "costco", "fcb", "gordon", "abc")]
                  == [publix.id, costco.id, fcb.id, gordon.id, abc.id],
                  detail=str([on(k) for k in ("publix_alias", "costco", "fcb", "gordon", "abc")]))
            names = [n for (n,) in s.execute(select(m.BankOccurrence.canonical_name))]
            check("14. no merged fragment is recreated",
                  all(names.count(n) == 1 for n in ("GORDON FOOD SERV", "PUBLIX SUPER MA", "COSTCO WHSE 0183",
                                                    "FRST BK MRCH SVC", "ABC FINE WINE S", "Publix"))
                  and "PUBLIX" not in names)
            check("14b. every fragment is still INACTIVE",
                  all(s.get(m.BankOccurrence, i).status == "INACTIVE" for i in fragments))
            check("15. an inactive fragment with a known canonical target resolves to the canonical WHO",
                  on("gordon") == gordon.id and rec[tx["gordon"]].tier == wr.DETERMINISTIC)
            orphan_rec = rec[tx["orphan"]]
            check("16. an inactive WHO with no safe target is neither recreated nor reactivated — held for review",
                  orphan_rec.tier == wr.PROPOSED and orphan_rec.occurrence_id is None
                  and s.get(m.BankOccurrence, orphan.id).status == "INACTIVE"
                  and names.count("OLD MERGED VENDOR") == 1 and "INACTIVE" in orphan_rec.evidence,
                  detail=f"{orphan_rec.tier} {orphan_rec.evidence[-120:]}")
            shared = rec[tx["shared"]]
            check("16b. an alias held by two active WHO is ambiguous — held, never guessed",
                  shared.tier == wr.PROPOSED and shared.occurrence_id is None)
            check("18. the stale recognition now references the canonical WHO, not the fragment",
                  on("gordon") == gordon.id)
            alias_rows_after = set(s.execute(select(
                m.BankOccurrenceAlias.id, m.BankOccurrenceAlias.occurrence_id, m.BankOccurrenceAlias.alias_text,
                m.BankOccurrenceAlias.alias_key, m.BankOccurrenceAlias.source_family)).all())
            new_aliases = alias_rows_after - alias_rows_before
            check("19. alias history is intact (every earlier alias unchanged, none moved or removed)",
                  alias_rows_before <= alias_rows_after)
            check("19b. no new alias is attached to an INACTIVE WHO",
                  not any(row[1] in fragments for row in new_aliases))
            check("20. no recognition references a merged INACTIVE WHO",
                  not any(r.occurrence_id in fragments for r in rec.values()))
            created = s.scalars(select(m.BankOccurrence).where(m.BankOccurrence.id.not_in(
                [o.id for o in (gordon, publix, costco, fcb, abc, cheney, wix, giftedd, car_gas, orphan,
                                twin_a, twin_b)] + list(fragments)))).all()
            # BANK_FINAL_CLEANUP_001: structural extraction never creates a raw
            # WHO. A genuinely new name is held PROPOSED for a person to create.
            check("21. a genuinely new identity creates NO WHO: it is held PROPOSED with its name",
                  created == [] and on("new") is None and rec[tx["new"]].tier == wr.PROPOSED
                  and summary.occurrences_created == 0,
                  detail=str([o.canonical_name for o in created]))
            check("21b. recognition never creates a GENERIC_OPERATIONAL WHO",
                  s.scalar(select(func.count(m.BankOccurrence.id)).where(
                      m.BankOccurrence.occurrence_type_id == generic.id)) == 1
                  and rec[tx["car_gas_unknown"]].occurrence_id != car_gas.id)
            check("22. BANK_WHO_WHY invariant intact: rules unchanged, none determines purpose from a description",
                  s.execute(select(m.BankRecognitionRule.id, m.BankRecognitionRule.occurrence_id,
                                   m.BankRecognitionRule.direction)).all() == rules_before
                  and not s.scalar(select(func.count(m.BankRecognitionRule.id)).where(
                      m.BankRecognitionRule.determines_purpose.is_(True),
                      m.BankRecognitionRule.match_field == "DESCRIPTION")))
            check("23. WHO recognition determines no WHY: no decision, default or association was written",
                  s.scalar(select(func.count(m.BankTransactionExplanation.id))) == 0
                  and s.scalar(select(func.count(m.BankOccurrence.id)).where(
                      m.BankOccurrence.default_transaction_reason_id.is_not(None))) == 0
                  and s.scalar(select(func.count(m.BankOccurrenceReasonAssociation.id))) == 0)
            credit = rec[tx["wix_credit"]]
            check("24. the approved Wix Payment Online CREDIT resolves to Giftedd through the rule",
                  credit.occurrence_id == giftedd.id and credit.tier == wr.DETERMINISTIC
                  and "rule" in credit.evidence)
            check("25. a Wix DEBIT stays Wix and never becomes Giftedd",
                  on("wix_debit") == wix.id)
            check("25b. a DEBIT carrying the CREDIT-only pattern does not become Giftedd",
                  rec[tx["wix_pattern_debit"]].occurrence_id != giftedd.id)
            check("summary counts the resolutions",
                  summary.resolved_by_alias >= 5 and summary.resolved_by_rule == 1
                  and summary.held_for_review == 3,
                  detail=f"name={summary.resolved_by_name} alias={summary.resolved_by_alias} "
                         f"rule={summary.resolved_by_rule} held={summary.held_for_review}")

            occurrences_after = s.scalar(select(func.count(m.BankOccurrence.id)))
            aliases_after = s.scalar(select(func.count(m.BankOccurrenceAlias.id)))
            second, _ = wr.recognize_transactions(s)
            s.commit()
            check("17. a repeated run creates no WHO, no alias and changes no recognition",
                  second.occurrences_created == 0 and second.aliases_created == 0
                  and second.recognitions_created == 0 and second.recognitions_updated == 0
                  and s.scalar(select(func.count(m.BankOccurrence.id))) == occurrences_after
                  and s.scalar(select(func.count(m.BankOccurrenceAlias.id))) == aliases_after
                  and occurrences_after == occurrences_before)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    print()
    print(f"{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
