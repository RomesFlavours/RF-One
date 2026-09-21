#!/usr/bin/env python
"""What the bank data actually proves about WHO and about WHY
(BANK_MEMO_PURPOSE_CLASSIFICATION_001 §13).

READ-ONLY. Opens no file, writes nothing, classifies nothing. It answers
one question per transaction, twice: is the counterparty identifiable,
and is the reason the money moved proven?

    A  WHO identifiable + purpose PROVEN      classifiable
    B  WHO identifiable + purpose ABSENT      human review
    C  WHO identifiable + purpose AMBIGUOUS   human review
    D  WHO unknown      + purpose PROVEN      classifiable on purpose alone
    E  neither sufficient                     human review

Category B is the one this task exists for. A Zelle payment names a
person and says nothing else; the person's identity is not evidence of
tips, of contract labour, or of anything else.

Never contacts AWS, RDS, Clover, ADP, Mercury or any network service.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import accounting_dedup
from rfone_data_store.bank_reconciliation import canonical_catalog
from rfone_data_store.bank_reconciliation import deterministic_rules
from rfone_data_store.bank_reconciliation import purpose_evidence as pe
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    redact_database_url,
)


def main() -> int:
    url = get_database_url()
    print(f"Database: {redact_database_url(url)}")
    print("READ-ONLY analysis — nothing is written.")
    print()

    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            transactions = [
                txn for txn in session.query(m.FinancialTransaction).all()
                if accounting_dedup.is_accounting_visible(txn)
            ]
            total_rows = session.query(m.FinancialTransaction).count()
            print(f"Transactions            : {total_rows}")
            print(f"Accounting-visible rows : {len(transactions)}")
            print()

            # --- evidence available at all --------------------------------
            with_memo = [t for t in transactions if (t.source_memo or "").strip()]
            print("SOURCE TEXT")
            print(f"  with a source memo / note     : {len(with_memo)}")
            print(f"  description only              : {len(transactions) - len(with_memo)}")
            memo_fields = Counter(t.source_memo_field for t in with_memo)
            for field, count in memo_fields.most_common():
                print(f"      from column {field!r}: {count}")
            print()

            # --- the five categories --------------------------------------
            buckets: dict[str, list] = defaultdict(list)
            channels = Counter()
            for txn in transactions:
                who = pe.who_evidence(txn.description_original)
                purpose = pe.purpose_evidence(txn.description_original, txn.source_memo)
                channels[who.channel] += 1
                known_who = who.names_counterparty or not who.is_person_channel
                if known_who and purpose.status == pe.PROVEN:
                    buckets["A"].append((txn, who, purpose))
                elif who.names_counterparty and purpose.status == pe.ABSENT:
                    buckets["B"].append((txn, who, purpose))
                elif who.names_counterparty and purpose.status == pe.AMBIGUOUS:
                    buckets["C"].append((txn, who, purpose))
                elif not who.names_counterparty and purpose.status == pe.PROVEN:
                    buckets["D"].append((txn, who, purpose))
                else:
                    buckets["E"].append((txn, who, purpose))

            labels = {
                "A": "WHO identifiable + purpose PROVEN      -> classifiable",
                "B": "WHO identifiable + purpose ABSENT      -> human review",
                "C": "WHO identifiable + purpose AMBIGUOUS   -> human review",
                "D": "WHO unknown      + purpose PROVEN      -> classifiable on purpose",
                "E": "neither WHO nor purpose sufficient     -> human review",
            }
            print("EVIDENCE CATEGORIES")
            for key in "ABCDE":
                print(f"  {key}. {labels[key]:<52} {len(buckets[key]):>4}")
            print()

            print("CHANNELS")
            for channel, count in channels.most_common():
                print(f"  {channel:<10} {count:>4}")
            print()

            # --- the person-payment question ------------------------------
            zelle = [
                (txn, pe.who_evidence(txn.description_original))
                for txn in transactions
                if pe.who_evidence(txn.description_original).channel == pe.ZELLE
            ]
            recipients = Counter(
                who.counterparty_name for _, who in zelle if who.counterparty_name
            )
            zelle_with_purpose = [
                txn for txn, _ in zelle
                if pe.purpose_evidence(txn.description_original, txn.source_memo).is_proven
            ]
            print("ZELLE / PERSON PAYMENTS")
            print(f"  transactions                      : {len(zelle)}")
            print(f"  distinct recipients               : {len(recipients)}")
            print(f"  recipient identifiable            : "
                  f"{sum(1 for _, who in zelle if who.counterparty_name)}")
            print(f"  with USEFUL PURPOSE evidence      : {len(zelle_with_purpose)}")
            print(f"  WITHOUT purpose evidence          : {len(zelle) - len(zelle_with_purpose)}")

            tips = [t for t in zelle_with_purpose
                    if pe.purpose_evidence(t.description_original, t.source_memo).account_code == "2300"]
            contract = [t for t in zelle_with_purpose
                        if pe.purpose_evidence(t.description_original, t.source_memo).account_code == "6800"]
            print(f"  safely classifiable as Tips (2300): {len(tips)}")
            print(f"  safely classifiable as 1099 (6800): {len(contract)}")
            print(f"  REMAIN for human review           : {len(zelle) - len(zelle_with_purpose)}")
            print()
            print("  recipients, by payment count:")
            for name, count in recipients.most_common():
                print(f"      {count:>3}  {name}")
            print()
            print("  NOTE: a recipient's name is WHO evidence only. No Tips or 1099 label is")
            print("  inferred from it, however strongly the name suggests a trade.")
            print()

            # --- what could be classified from purpose, outside Zelle -----
            unresolved = [
                txn for txn in transactions
                if txn.explanation_id is None
                or (session.get(m.BankTransactionExplanation, txn.explanation_id) or
                    m.BankTransactionExplanation()).decision_status == "NEEDS_HUMAN_REVIEW"
            ]
            newly = defaultdict(list)
            for txn in unresolved:
                purpose = pe.purpose_evidence(txn.description_original, txn.source_memo)
                if purpose.is_proven:
                    newly[purpose.account_code].append(txn)
            print("UNRESOLVED TRANSACTIONS WITH PROVEN PURPOSE")
            print(f"  unresolved rows                   : {len(unresolved)}")
            if newly:
                for code in sorted(newly):
                    account = canonical_catalog.by_code(session, code)
                    name = account.name if account is not None else "?"
                    print(f"      {code} {name:<40} {len(newly[code]):>4}")
            else:
                print("      none — no unresolved row carries proven purpose text")
            print()

            deterministic = [
                txn for txn in unresolved
                if deterministic_rules.match(
                    txn.payee_normalized or txn.description_original or ""
                ) is not None
            ]
            print(f"  additionally recognisable by the existing deterministic "
                  f"description rules: {len(deterministic)}")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
