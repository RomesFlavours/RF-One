#!/usr/bin/env python
"""Apply deterministic accounting classification to unclassified receivers
(BANK_CANONICAL_ACCOUNTING_CATALOG_001).

Only descriptions that carry their own accounting meaning are classified:
a foreign transaction fee, a bank service charge, a merchant processing
fee, a credit-card settlement, a sales-tax remittance, an internal
transfer, a loan advance. Everything else — every mixed supplier, every
label resolvable only by history — is left for a human and reported.

For each matched group it creates, idempotently:

* the Why the rule names, pointing at the canonical account;
* a Who named after the normalized description, whose default Why is that
  one;
* a human-visible decision on each canonical transaction of the group;
* an exact-match recognition rule so the next import is automatic.

It never overwrites a decision a human already made, never touches a
suppressed accounting copy, and previews by default.

    python apply_deterministic_bank_classification.py           # preview
    python apply_deterministic_bank_classification.py --apply   # write

Never contacts AWS, RDS or any network service.
"""

from __future__ import annotations

import argparse
import sys

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import canonical_catalog
from rfone_data_store.bank_reconciliation import classification as classification_service
from rfone_data_store.bank_reconciliation import deterministic_rules
from rfone_data_store.bank_reconciliation import receiver_candidates as rc
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    redact_database_url,
)

OCCURRENCE_TYPE_CODE = "COUNTERPARTY"
OCCURRENCE_TYPE_NAME = "Counterparty"


def _ensure_occurrence_type(session):
    existing = session.query(m.BankOccurrenceType).filter_by(code=OCCURRENCE_TYPE_CODE).first()
    if existing is not None:
        return existing
    created = m.BankOccurrenceType(
        code=OCCURRENCE_TYPE_CODE, name=OCCURRENCE_TYPE_NAME,
        description=(
            "The party a bank movement concerns, where the movement's own description "
            "identifies it. Deliberately generic: Supplier is only one possible kind, and "
            "a bank line rarely says which."
        ),
    )
    session.add(created)
    session.flush()
    return created


def _ensure_why(session, rule: deterministic_rules.DeterministicRule):
    """The Why a deterministic rule names, created once and reused.

    A Why here carries real explanatory content — why the money moved —
    rather than repeating the account name, which is the What."""
    existing = session.query(m.BankTransactionReason).filter_by(code=rule.why_code).first()
    account = canonical_catalog.by_code(session, rule.account_code)
    if account is None:
        raise ValueError(
            f"The canonical account {rule.account_code} is missing — seed the catalog first."
        )
    if existing is not None:
        return existing
    return classification_service.create_transaction_reason(
        session, code=rule.why_code, name=rule.why_name,
        accounting_classification_id=account.id,
        description=rule.rationale,
    )


def main() -> int:
    # BANK_FINAL_RELEASE_BLOCKERS_001 — retired. This script classified
    # transactions by creating a Who whose DEFAULT Why then decided them,
    # which is exactly "WHO determines WHY". The one automatic WHY engine is
    # `structural_why` (import, reprocess, `apply_structural_why.py`).
    print("RETIRED: WHY is decided by the structural engine only — use "
          "apply_structural_why.py. Nothing was read or written.")
    return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write (default: preview)")
    args = parser.parse_args()

    url = get_database_url()
    print(f"Database: {redact_database_url(url)}")
    print()

    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            if session.query(m.BankAccountingClassification).count() == 0:
                print("The canonical catalog is empty. Run the migration or "
                      "seed_canonical_accounting_catalog.py --apply first.")
                return 1

            # BANK_ACCOUNTING_CLASSIFICATION_SEMANTICS_001 §6: a rule whose
            # destination this catalog refuses as an automatic classification
            # stops the run rather than quietly writing to it. There is no
            # such rule today; this is what keeps that true.
            unsafe = deterministic_rules.destination_problems(session)
            if unsafe:
                print("REFUSED — a deterministic rule points where automatic classification "
                      "may never land:")
                for problem in unsafe:
                    print("  -", problem)
                return 1

            candidates = rc.build_candidates(session, include_assigned=False)
            matched: list[tuple] = []
            mixed: list = []
            unmatched: list = []

            for candidate in candidates:
                if deterministic_rules.is_mixed_supplier(candidate.payee_normalized):
                    mixed.append(candidate)
                    continue
                found = deterministic_rules.match(candidate.payee_normalized)
                if found is None:
                    unmatched.append(candidate)
                else:
                    matched.append((candidate, found))

            print("PREVIEW — deterministic matches")
            print("=" * 92)
            for candidate, found in matched:
                account = canonical_catalog.by_code(session, found.account_code)
                effect = "NO P&L EFFECT" if found.rule.no_pl_effect else "P&L"
                print(
                    f"  {candidate.transaction_count:>3} txn  "
                    f"{candidate.absolute_total_minor / 100:>12,.2f}  "
                    f"{candidate.payee_normalized[:42]:<42} -> {found.account_code} "
                    f"{(account.name if account else '?')[:30]:<30} [{effect}]"
                )
            print("=" * 92)
            print(f"  deterministic groups      : {len(matched)}")
            print(f"  transactions covered      : {sum(c.transaction_count for c, _ in matched)}")
            print(f"  mixed suppliers (refused) : {len(mixed)}")
            print(f"  unmatched -> human review : {len(unmatched)}")
            print()

            if mixed:
                print("Mixed suppliers deliberately NOT classified (invoice required):")
                for candidate in sorted(mixed, key=lambda c: -c.absolute_total_minor)[:15]:
                    print(f"  {candidate.payee_normalized[:56]:<56} "
                          f"{candidate.transaction_count:>3} txn  "
                          f"{candidate.absolute_total_minor / 100:>12,.2f}")
                print()

            if not args.apply:
                print("Preview only. Re-run with --apply to classify these groups.")
                return 0

            occurrence_type = _ensure_occurrence_type(session)
            classified_transactions = 0
            created_groups = 0

            for candidate, found in matched:
                why = _ensure_why(session, found.rule)
                occurrence = session.query(m.BankOccurrence).filter_by(
                    canonical_name=candidate.payee_normalized
                ).first()
                if occurrence is None:
                    occurrence = classification_service.create_occurrence(
                        session,
                        canonical_name=candidate.payee_normalized,
                        occurrence_type_id=occurrence_type.id,
                        default_transaction_reason_id=why.id,
                        optional_notes=(
                            "Created by deterministic accounting recognition: "
                            f"{found.rule.rationale}"
                        ),
                    )
                outcome = rc.approve_candidates(
                    session,
                    payee_keys=[candidate.group_key],
                    occurrence_id=occurrence.id,
                    confirmed_by_account_id=None,
                    learn_description=True,
                )
                classified_transactions += outcome.transactions_classified
                created_groups += 1

            session.commit()
            print(f"APPLIED: {created_groups} group(s), "
                  f"{classified_transactions} transaction(s) classified.")
            print(f"Left for human review: {len(mixed) + len(unmatched)} group(s).")
            return 0
    except ValueError as exc:
        print(f"REFUSED: {exc}")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
