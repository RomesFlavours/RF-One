#!/usr/bin/env python
"""The deterministic bank classification script is canonical-WHO safe
(BANK_WHO_WHY_CANONICAL_CATALOG_001).

`apply_deterministic_bank_classification.py` is RETIRED
(BANK_FINAL_RELEASE_BLOCKERS_001): it refuses before reading anything,
because a Who's default Why deciding a transaction is "WHO determines WHY".
Its body is kept, and a group's Who is chosen there only through
`canonical_group_who`, which delegates to the SAME
`CanonicalWhoResolver.resolve` that WHO recognition uses.

This suite proves, on a throwaway database shaped like the approved
canonical WHO/WHY import:

* the script still refuses, and running it — twice — writes nothing;
* the group Who is the ACTIVE canonical WHO by exact name or by alias;
* an INACTIVE merged fragment is never reused, recreated or reactivated;
  without a safe target, and on ambiguity, the group is held;
* only a genuinely new identity may follow the COUNTERPARTY creation path,
  never GENERIC_OPERATIONAL;
* the Wix Payment Online CREDIT resolves to Giftedd, a Wix DEBIT never does;
* for every case the result is identical to WHO recognition's resolution.

Never touches AWS, RDS, the operational database, or a real bank file.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

import apply_deterministic_bank_classification as script
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import accounting_dedup
from rfone_data_store.bank_reconciliation import deterministic_rules
from rfone_data_store.bank_reconciliation import receiver_candidates as rc
from rfone_data_store.bank_reconciliation import who_recognition as wr
from rfone_data_store.database import (
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)

HERE = Path(__file__).resolve().parent
DAY = date(2026, 9, 15)


def group(payee: str, direction: str = "DEBIT", sample: str | None = None) -> rc.ReceiverCandidate:
    return rc.ReceiverCandidate(payee_normalized=payee, direction=direction, transaction_count=1,
                                first_date=DAY, last_date=DAY, total_minor=0, absolute_total_minor=0,
                                sample_descriptions=[sample or payee])


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

    url = resolve_test_database_url("deterministic_classification_who_safety")
    print(f"Database: {redact_database_url(url)}")
    run_migrations_to_head(url)
    db_path = Path(url[len("sqlite:///"):])
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as s:
            counterparty = s.scalars(select(m.BankOccurrenceType).where(
                m.BankOccurrenceType.code == "COUNTERPARTY")).one()
            generic = m.BankOccurrenceType(code="GENERIC_OPERATIONAL", name="Generic Operational")
            s.add(generic)
            s.flush()

            def who(name, status="ACTIVE", type_=counterparty):
                o = m.BankOccurrence(canonical_name=name, occurrence_type_id=type_.id, status=status)
                s.add(o)
                s.flush()
                return o

            def alias(o, text, family="ACH_ORIGINATOR"):
                s.add(m.BankOccurrenceAlias(occurrence_id=o.id, alias_text=text, alias_key=wr.who_key(text),
                                            source_family=family, source="HUMAN"))

            def merged(canonical, fragment_name):
                fragment = who(fragment_name, status="INACTIVE")
                alias(canonical, fragment_name)
                alias(canonical, fragment_name, family="MERGED_WHO_NAME")
                return fragment

            gordon = who("Gordon Food Service")
            gfs = merged(gordon, "GFS STORE 1971")
            publix = who("Publix")
            alias(publix, "PUBLIX", family="MERGED_WHO_NAME")
            publix_fragment = merged(publix, "PUBLIX SUPER MA")
            costco = who("Costco")
            costco_fragment = merged(costco, "COSTCO WHSE 0183")
            fcb = who("First Citizens Bank")
            fcb_fragment = merged(fcb, accounting_dedup.normalize_payee("FRST BK MRCH SVC FEE ********0885"))
            abc = who("ABC")
            abc_fragment = merged(abc, "ABC FINE WINE S")
            cheney = who("CHENEY BROTHERS")
            wix = who("Wix")
            wix_fragment = merged(wix, "WIX COM INC 415 6399034")
            giftedd = who("Giftedd")
            car_gas = who("Car-Gas", type_=generic)
            orphan = who("OLD MERGED VENDOR", status="INACTIVE")
            twin_a, twin_b = who("Twin Vendor A"), who("Twin Vendor B")
            alias(twin_a, "SHARED VENDOR")
            alias(twin_b, "SHARED VENDOR")
            s.add(m.BankRecognitionRule(
                match_type="PREFIX", normalized_pattern="WIXCOM WIX PAYMEN", match_field="DESCRIPTION",
                determines_purpose=False, direction="CREDIT", occurrence_id=giftedd.id,
                transaction_reason_id=None, priority=0, status="ACTIVE", auto_apply_enabled=True,
                human_confirmations=1, human_contradictions=0))
            s.commit()
            fragments = {gfs.id, publix_fragment.id, costco_fragment.id, fcb_fragment.id, abc_fragment.id,
                         wix_fragment.id, orphan.id}

            resolver = wr.CanonicalWhoResolver(s)
            resolve = lambda g: script.canonical_group_who(resolver, g)

            # The groups as `receiver_candidates.build_candidates` would key them.
            cases = {
                "cheney": group("CHENEY BROTHERS"),
                "publix_renamed": group("PUBLIX"),
                "gordon": group("GFS STORE 1971"),
                "publix_alias": group("PUBLIX SUPER MA"),
                "costco": group("COSTCO WHSE 0183"),
                "fcb": group(accounting_dedup.normalize_payee("FRST BK MRCH SVC FEE ********0885")),
                "abc": group("ABC FINE WINE S"),
                "orphan": group("OLD MERGED VENDOR"),
                "shared": group("SHARED VENDOR"),
                "new": group("BRAND NEW VENDOR LLC"),
                "wix_credit": group(accounting_dedup.normalize_payee("Wixcom Wix Paymen ST-F*W*T1A0L0F6"),
                                    "CREDIT", "Wixcom Wix Paymen ST-F*W*T1A0L0F6"),
                "wix_debit_alias": group("WIX COM INC 415 6399034", "DEBIT",
                                         "POS SIG 07/01 VISA #5363 Wix.Com, Inc. 415-6399034 CA"),
                "wix_pattern_debit": group(accounting_dedup.normalize_payee("Wixcom Wix Paymen ST-Q*Q*Q1Q1Q1Q1"),
                                           "DEBIT", "Wixcom Wix Paymen ST-Q*Q*Q1Q1Q1Q1"),
            }
            out = {k: resolve(g) for k, g in cases.items()}
            occ = lambda k: out[k].occurrence.id if out[k].occurrence else None

            check("1. an exact ACTIVE canonical WHO is reused", occ("cheney") == cheney.id
                  and out["cheney"].how == wr.RESOLVED_BY_NAME)
            check("1b. a renamed canonical WHO is reused by its identity key (PUBLIX -> Publix)",
                  occ("publix_renamed") == publix.id)
            check("2. an alias resolves to its ACTIVE canonical WHO (no example is hard-coded: the alias rows decide)",
                  [occ(k) for k in ("publix_alias", "costco", "fcb", "abc")] == [publix.id, costco.id, fcb.id, abc.id]
                  and all(out[k].how == wr.RESOLVED_BY_ALIAS for k in ("publix_alias", "costco", "fcb", "abc")),
                  detail=str([(occ(k), out[k].how) for k in ("publix_alias", "costco", "fcb", "abc")]))
            check("3. an INACTIVE merged fragment is never the result",
                  not any(occ(k) in fragments for k in out))
            check("4. an inactive merged fragment with a canonical target resolves to that target",
                  occ("gordon") == gordon.id)
            check("5. an inactive WHO with no safe target is held, not resolved",
                  out["orphan"].occurrence is None and out["orphan"].held is not None
                  and not out["orphan"].is_new and "INACTIVE" in out["orphan"].held)
            check("6. an alias held by two active WHO is held, never chosen arbitrarily",
                  out["shared"].occurrence is None and out["shared"].held is not None)
            check("10. a genuinely new identity is reported as new — the only state allowed to create",
                  out["new"].is_new and out["new"].occurrence is None)
            source = (HERE / "apply_deterministic_bank_classification.py").read_text(encoding="utf-8")
            check("11. the only creation path is COUNTERPARTY; GENERIC_OPERATIONAL is never invented",
                  script.OCCURRENCE_TYPE_CODE == "COUNTERPARTY" and "GENERIC_OPERATIONAL" not in source
                  and out["new"].occurrence is None)
            check("11b. an unknown name is never resolved to a configured GENERIC_OPERATIONAL WHO",
                  not any(occ(k) == car_gas.id for k in out))
            check("13. the approved Wix Payment Online CREDIT group resolves to Giftedd by the rule",
                  occ("wix_credit") == giftedd.id and out["wix_credit"].how == wr.RESOLVED_BY_RULE)
            check("14. a Wix DEBIT stays Wix (by alias) and never becomes Giftedd",
                  occ("wix_debit_alias") == wix.id and occ("wix_pattern_debit") != giftedd.id)
            check("14b. no Wix group matches a deterministic rule, so the script would never classify one",
                  all(deterministic_rules.match(cases[k].payee_normalized) is None
                      for k in ("wix_credit", "wix_debit_alias", "wix_pattern_debit")))
            def shape(resolution):
                return (resolution.occurrence.id if resolution.occurrence else None,
                        resolution.how, resolution.held)

            agree = all(
                shape(r) == shape(resolver.resolve(
                    cases[k].payee_normalized, description=cases[k].sample_descriptions[0],
                    amount_minor=1 if cases[k].direction == "CREDIT" else -1, instrument_id=None))
                for k, r in out.items())
            check("15. every outcome equals CanonicalWhoResolver.resolve — the resolver WHO recognition uses",
                  agree and script.canonical_group_who.__module__ == "apply_deterministic_bank_classification"
                  and "CanonicalWhoResolver" in source and ".resolve(" in source)
            check("15b. the old exact-name lookup is gone from the script",
                  "filter_by(\n                    canonical_name=candidate.payee_normalized" not in source
                  and "canonical_name=candidate.payee_normalized\n                ).first()" not in source)
            check("12. BANK_WHO_WHY invariant: a resolution carries no WHY and no rule determines purpose",
                  not hasattr(out["cheney"], "transaction_reason_id")
                  and not s.scalar(select(func.count(m.BankRecognitionRule.id)).where(
                      m.BankRecognitionRule.determines_purpose.is_(True),
                      m.BankRecognitionRule.match_field == "DESCRIPTION")))
            check("resolution itself writes nothing", not s.new and not s.dirty and not s.deleted)
    finally:
        engine.dispose()

    # ---------------------------------------------------- the script itself
    def digest() -> str:
        return hashlib.sha256(db_path.read_bytes()).hexdigest()

    env = dict(os.environ, RFONE_DATABASE_URL=url, PYTHONIOENCODING="utf-8")
    before = digest()
    runs = [subprocess.run([sys.executable, str(HERE / "apply_deterministic_bank_classification.py"), *args],
                           cwd=str(HERE), env=env, capture_output=True, text=True)
            for args in ([], ["--apply"], ["--apply"])]
    check("7. the script stays RETIRED: preview and two applies refuse before reading anything",
          all(r.returncode == 1 and "RETIRED" in r.stdout for r in runs),
          detail=str([(r.returncode, r.stdout[:60]) for r in runs]))
    after = digest()
    check("8/9. running it (three times) writes nothing — no WHO recreated, no reference moved to a fragment",
          before == after)

    cleanup_disposable_test_database_url(url)
    print()
    print(f"{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
