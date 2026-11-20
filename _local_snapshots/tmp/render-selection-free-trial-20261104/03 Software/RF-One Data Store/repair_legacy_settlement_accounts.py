#!/usr/bin/env python
"""Recover settlement configuration saved through the legacy field
(BANK_SETTLEMENT_UI_AND_MODAL_REPAIR_001).

Why this exists: the Edit Payment Instrument page offered two apparently
equivalent controls — the older `Settles to` (`linked_instrument_id`) and
the new historized Settlement Account. Operators reasonably used the
first, so the information WAS saved, just not where the accounting layer
reads it from. This script moves that existing, human-entered decision
into the historized table. It invents nothing: the only source is the
`linked_instrument_id` a human already saved, never a file name, a
`last_four` or an institution.

Safe by default: it PREVIEWS and writes nothing unless `--apply` is
given, and it is idempotent — a card that already has a historized row is
skipped entirely, so a second run creates no duplicate and overwrites no
human decision.

Usage:
    python repair_legacy_settlement_accounts.py                  # preview
    python repair_legacy_settlement_accounts.py --apply          # write
    python repair_legacy_settlement_accounts.py --apply --expect 6

`--expect N` refuses to write unless exactly N cards are recoverable —
the guard that makes "apply only after verifying it matches what the
operator actually configured" enforceable rather than a matter of
attention.

Never contacts AWS, RDS or any network service: it operates on whatever
database `RFONE_DATABASE_URL` resolves to.
"""

from __future__ import annotations

import argparse
import sys

from rfone_data_store.bank_reconciliation import accounting_dedup, card_configuration
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    redact_database_url,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="write the recovered assignments (default is a read-only preview)",
    )
    parser.add_argument(
        "--expect", type=int, default=None,
        help="refuse to write unless exactly this many cards are recoverable",
    )
    parser.add_argument(
        "--recompute", action="store_true",
        help="run accounting deduplication after writing (implies --apply)",
    )
    args = parser.parse_args()
    if args.recompute:
        args.apply = True

    url = get_database_url()
    print(f"Database: {redact_database_url(url)}")
    print()

    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            candidates = card_configuration.plan_legacy_settlement_recovery(session)

            if not candidates:
                print("Nothing to recover: no credit card has a legacy "
                      "`linked_instrument_id` awaiting historization.")
                return 0

            recoverable = [c for c in candidates if c.recoverable]
            skipped = [c for c in candidates if not c.recoverable]

            print("PREVIEW — nothing has been written yet")
            print("=" * 78)
            for candidate in candidates:
                marker = "  " if candidate.recoverable else "! "
                print(
                    f"{marker}card {candidate.credit_card_id:>3} "
                    f"{candidate.credit_card_name:<22} -> "
                    f"account {candidate.settlement_account_id:>3} "
                    f"{candidate.settlement_account_name:<22} "
                    # `date` interprets a format spec as strftime, so a width
                    # spec must be applied to the string, not to the date.
                    f"valid_from={(candidate.valid_from.isoformat() if candidate.valid_from else '—'):<12} "
                    f"transactions={candidate.transaction_count}"
                )
                if candidate.skip_reason:
                    print(f"      SKIPPED: {candidate.skip_reason}")
            print("=" * 78)
            print(f"  recoverable : {len(recoverable)}")
            print(f"  skipped     : {len(skipped)} (left untouched, for a human to decide)")
            print()

            if args.expect is not None and len(recoverable) != args.expect:
                print(
                    f"REFUSING TO WRITE: --expect {args.expect} but {len(recoverable)} "
                    "card(s) are recoverable. Nothing was changed."
                )
                return 1

            if not args.apply:
                print("Preview only. Re-run with --apply to write these assignments.")
                return 0

            written = card_configuration.apply_legacy_settlement_recovery(session)
            print(f"WROTE {len(written)} historized settlement assignment(s).")

            if args.recompute:
                outcome = accounting_dedup.recompute_accounting_dedup(session)
                print()
                print("Accounting deduplication recomputed")
                print(f"  raw rows preserved       : {outcome.raw_rows_preserved}")
                print(f"  transactions considered  : {outcome.transactions_considered}")
                print(f"  canonical                : {outcome.canonical_transactions}")
                print(f"  duplicate groups         : {outcome.duplicate_groups}")
                print(f"  excluded from accounting : {outcome.suppressed_transactions}")
                print(f"  no settlement account    : {outcome.unresolved_transactions}")

            session.commit()
            print()
            print("Committed.")
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
