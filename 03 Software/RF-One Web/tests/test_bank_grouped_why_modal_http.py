"""The grouped three-column "Select WHO / WHY" popup (BANK_WHY_NAVIGATION_GROUPS_001).

Proves, on a throwaway database migrated to head, that:

* `BankReasonGroup` — the one WHY grouping — holds exactly the 15 approved
  navigation groups (stored in the approved order, shown alphabetically); every canonical WHY is in exactly
  one of them, as approved (including the eight Product Owner REVIEW
  decisions); no WHY changed its name, WHAT, destination or P&L / Balance
  Sheet nature; the retired groups are inactive, not deleted;
* the popup has three columns WHO | WHY GROUP | WHY and is fed by ONE
  catalog request (groups alphabetical with counts, every active WHY with its
  group and WHAT) — no WHO x WHY matrix;
* any active WHY may be chosen for any WHO: Confirm adds the missing WHO ->
  WHY association, an existing one is left as it is (idempotent);
* a new WHY needs a group, is filed under it, reuses an existing WHY of the
  same name, and leaves nothing behind when the save fails;
* Configuration's own WHY creation, Rules and Standards are unchanged.

The browser behaviour (search, selection, contrast) is verified separately on
a disposable local server. Never touches a real bank file, AWS, or any
production database.
"""

from __future__ import annotations

import csv
import io
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_grouped_why_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-grouped-why-secret"

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
from rfone_data_store.bank_reconciliation import why_catalog  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
AUG = date(2026, 8, 12)
REVIEW_AUG = "/bank/review?year=2026&month=8"
FROZEN_V1 = Path(_DATA_STORE_DIR) / "migrations" / "migration_data" / "c4a9e7d21b56_rfone_restaurant_why_v1.csv"

APPROVED_GROUPS = [
    ("PRODUCT_COST", "Food, Beverage & Supplies", 8), ("PAYROLL", "Payroll", 14),
    ("OCCUPANCY", "Rent & Occupancy", 4), ("UTILITIES", "Utilities & Communications", 6),
    ("FACILITY", "Maintenance, Repairs & Cleaning", 4), ("PROFESSIONAL_SERVICES", "Professional Services", 4),
    ("OFFICE_ADMIN", "Office, Software & Admin", 5), ("INSURANCE", "Insurance", 4),
    ("MARKETING", "Marketing & Entertainment", 2), ("VEHICLE_TRAVEL", "Vehicles & Travel", 5),
    ("BANKING", "Banking, Fees & Interest", 5), ("TRANSFERS_CARD_PAYMENTS", "Transfers & Card Payments", 4),
    ("DEPOSITS_SETTLEMENTS", "Deposits, Settlements & Liabilities", 6), ("OWNER_PERSONAL", "Owner", 8),
    ("CAPITAL_PROJECTS", "Capital Purchases", 2),
]
REVIEW_DECISIONS = {
    "WORKERS_COMPENSATION": "PAYROLL", "RECRUITING_TRAINING": "PAYROLL", "TIPS_SETTLEMENT": "PAYROLL",
    "VEHICLE_INSURANCE": "INSURANCE", "MEALS_ENTERTAINMENT": "MARKETING",
    "BUSINESS_TRAVEL_SCOUTING": "VEHICLE_TRAVEL", "PAYABLE_SETTLEMENT": "DEPOSITS_SETTLEMENTS",
    "EQUIPMENT_PURCHASE_CAPEX": "CAPITAL_PROJECTS",
}
RETIRED = ("KITCHEN_LABOR", "FOH_LABOR", "PEOPLE", "ADMINISTRATION", "MONEY_MOVEMENT")


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    # ------------------------------------------------------------------
    # GROUP DATA (1-5)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        active = why_catalog.groups(s)
        all_groups = {g.code: g for g in s.scalars(select(m.BankReasonGroup))}
        reasons = {r.code: r for r in s.scalars(select(m.BankTransactionReason))}
        canonical = {row["Code"]: row for row in why_catalog.catalog_rows()}
        stored = sorted(active, key=lambda g: g.display_order)
        check("1. exactly the 15 approved navigation groups, active; stored display_order still the approved "
              "order, shown alphabetically (Product Owner 2026-10-05: presentation only)",
              [(g.code, g.name) for g in stored] == [(c, n) for c, n, _ in APPROVED_GROUPS]
              and [g.name for g in active] == sorted((n for _, n, _ in APPROVED_GROUPS), key=str.casefold),
              detail=str([(g.code, g.name) for g in active]))
        check("1b. the five superseded groups are inactive, not deleted",
              all(code in all_groups and not all_groups[code].active for code in RETIRED))
        counts = {}
        for reason in reasons.values():
            if reason.code in canonical:
                code = reason.reason_group.code if reason.reason_group else None
                counts[code] = counts.get(code, 0) + 1
        check("2. all 81 canonical WHY are assigned, with the approved number per group",
              len(canonical) == 81 and set(canonical) <= set(reasons)
              and counts == {c: n for c, _, n in APPROVED_GROUPS}, detail=str(counts))
        check("3. each WHY in exactly one ACTIVE group, the one the canonical catalog names",
              all(reasons[c].reason_group is not None and reasons[c].reason_group.active
                  and reasons[c].reason_group.code == row["Group Code"] for c, row in canonical.items()))
        check("3b. the eight REVIEW items follow the Product Owner decisions",
              {c: reasons[c].reason_group.code for c in REVIEW_DECISIONS} == REVIEW_DECISIONS)
        frozen = {row["Code"]: row for row in csv.DictReader(io.StringIO(FROZEN_V1.read_text(encoding="utf-8-sig")))}
        check("4. WHAT / destination unchanged: every WHY resolves to the account the catalog has always named",
              all(reasons[c].accounting_classification.code == row["Account Code"] for c, row in canonical.items())
              and all(canonical[c]["Account Code"] == row["Account Code"] for c, row in frozen.items())
              and not why_catalog.catalog_problems(s), detail=str(why_catalog.catalog_problems(s))[:300])
        pl = sum(1 for c in canonical if reasons[c].is_profit_loss)
        check("5. P&L / Balance Sheet nature unchanged (60 P&L with a WHAT, 21 Balance Sheet without)",
              pl == 60 and all((reasons[c].what is None) == (not reasons[c].is_profit_loss) for c in canonical),
              detail=str((pl, [c for c in canonical if (reasons[c].what is None) != (not reasons[c].is_profit_loss)])))

        # Seed data for the popup.
        account_service.create_account(s, username="grouped_why", display_name="Grouped Why",
                                       password="GroupedWhy123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="grouped_why").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        legal = m.LegalEntity(legal_name="Grouped Why LLC", status="ACTIVE")
        s.add(legal)
        s.flush()
        checking = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                       display_name="Grouped Checking", institution="CHASE", last_four="0042",
                                       currency="USD")
        s.add(checking)
        s.flush()
        batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="seed.csv",
                                  raw_file_bytes=b"x", sha256="9" * 64, status="NORMALIZED",
                                  payment_instrument_id=checking.id)
        s.add(batch)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        plumber = m.BankOccurrence(canonical_name="Plumber Joe", occurrence_type_id=counterparty.id, status="ACTIVE",
                                   optional_notes="Canonical WHO.")
        s.add(plumber)
        s.flush()
        seq = [0]

        def tx(description):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", import_batch_id=batch.id,
                posting_date=AUG, transaction_date=AUG, description_original=description,
                description_normalized=description, amount_minor=-1000 - seq[0], status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"grouped-why-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            return t

        rows = {k: tx(f"GROUPED WHY ROW {k}") for k in ("first", "again", "new", "bad_group", "rollback")}
        s.commit()
        ids = {k: t.id for k, t in rows.items()}
        ids.update(plumber=plumber.id, repair=reasons["EQUIPMENT_REPAIR"].id,
                   repair_what=reasons["EQUIPMENT_REPAIR"].accounting_classification_id,
                   facility=all_groups["FACILITY"].id, retired=all_groups["PEOPLE"].id)
        rules_before = s.scalar(select(func.count(m.BankRecognitionRule.id)))
        standards_before = s.scalar(select(func.count(m.BankReconciliationStandard.id)))
        whats = [c for c in s.scalars(select(m.BankAccountingClassification).order_by(
            m.BankAccountingClassification.code)) if c.is_what]
        ids["what"] = next(c.id for c in whats if c.code == "7310")

    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "grouped_why", "password": "GroupedWhy123!", "csrf_token": csrf})
    review = client.get(REVIEW_AUG).data.decode()
    csrf = CSRF_RE.search(review).group(1)

    def post(key, **data):
        return client.post(f"/bank/transactions/{ids[key]}/who-why", headers={"X-Requested-With": "fetch"},
                           data={"csrf_token": csrf, "return_to": REVIEW_AUG, **data})

    def decision(key):
        with SessionFactory() as s:
            t = s.get(m.FinancialTransaction, ids[key])
            e = s.get(m.BankTransactionExplanation, t.explanation_id) if t.explanation_id else None
            return (e.occurrence_id, e.transaction_reason_id, e.decision_source, e.accounting_classification_id) if e else None

    def associations(reason_id):
        with SessionFactory() as s:
            return s.execute(select(m.BankOccurrenceReasonAssociation.id,
                                    m.BankOccurrenceReasonAssociation.confirmation_count).where(
                m.BankOccurrenceReasonAssociation.occurrence_id == ids["plumber"],
                m.BankOccurrenceReasonAssociation.transaction_reason_id == reason_id)).all()

    # ------------------------------------------------------------------
    # MODAL (6-11)
    # ------------------------------------------------------------------
    popup = review.split('id="who-picker"', 1)[1].split("</form>", 1)[0]
    check("6. the popup has three columns: WHO | WHY GROUP | WHY",
          popup.count('class="ww-col ') == 3
          and [t.strip() for t in re.findall(r'class="ww-col-title"[^>]*>([A-Z ]+)', popup)] == ["WHO", "WHY GROUP", "WHY"]
          and 'id="why-group-list"' in popup and 'id="why-group-search"' in popup and "+ Create New WHY" in popup)
    catalog = client.get("/bank/manual-reconciliation/why-catalog").get_json()
    check("8. the catalog request gives the groups alphabetically, with their WHY counts",
          [(g["name"], g["count"]) for g in catalog["groups"]]
          == sorted(((n, c) for _, n, c in APPROVED_GROUPS), key=lambda x: x[0].casefold()),
          detail=str(catalog["groups"])[:300])
    with SessionFactory() as s:
        active_ids = {r.id for r in why_catalog.active_reasons(s) if r.accounting_classification_id is not None}
    check("11. every active WHY is in the catalog once, with its group and its WHAT / destination",
          sorted(w["id"] for w in catalog["whys"]) == sorted(active_ids)
          and all(w["group_id"] is not None and w["what"] for w in catalog["whys"]))
    js = client.get("/static/js/bank-who-why.js").data.decode()
    check("16b. no WHO x WHY matrix: the catalog is fetched once, the WHO's own WHY only to mark them",
          js.count("fetch(catalogUrl") == 1 and "associatedCache[whoId]" in js and "data-catalog-url" in popup)

    # ------------------------------------------------------------------
    # ASSOCIATIONS (18-20)
    # ------------------------------------------------------------------
    first = post("first", occurrence_id=str(ids["plumber"]), transaction_reason_id=str(ids["repair"]))
    check("19. an existing WHY the WHO did not have is accepted; Confirm adds the association once; WHAT derived",
          first.status_code == 200 and decision("first") == (ids["plumber"], ids["repair"], "HUMAN", ids["repair_what"])
          and [count for _, count in associations(ids["repair"])] == [1],
          detail=str((first.get_json(), associations(ids["repair"]))))
    association_id = associations(ids["repair"])[0][0]
    again = post("again", occurrence_id=str(ids["plumber"]), transaction_reason_id=str(ids["repair"]))
    check("20. an existing association is idempotent: still ONE row, the same one",
          again.status_code == 200 and [a for a, _ in associations(ids["repair"])] == [association_id],
          detail=str((again.status_code, again.get_json(), associations(ids["repair"]))))

    # ------------------------------------------------------------------
    # NEW WHY (21-26)
    # ------------------------------------------------------------------
    no_group = post("new", occurrence_id=str(ids["plumber"]), new_why_name="Backflow Testing",
                    new_why_what_id=str(ids["what"]))
    bad_group = post("bad_group", occurrence_id=str(ids["plumber"]), new_why_name="Backflow Testing",
                     new_why_what_id=str(ids["what"]), new_why_group_id=str(ids["retired"]))
    check("22. a new WHY needs a group — none, or a retired one, is refused and nothing is created",
          no_group.status_code == 400 and bad_group.status_code == 400 and decision("new") is None
          and decision("bad_group") is None)
    created = post("new", occurrence_id=str(ids["plumber"]), new_why_name="Backflow Testing",
                   new_why_what_id=str(ids["what"]), new_why_group_id=str(ids["facility"]))
    with SessionFactory() as s:
        new = s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.name == "Backflow Testing")).all()
        new_group = new[0].reason_group.code if new else None
    check("21. Create New WHY: created in the chosen group with its WHAT, associated, used for this transaction",
          created.status_code == 200 and len(new) == 1 and new_group == "FACILITY"
          and new[0].accounting_classification_id == ids["what"] and [c for _, c in associations(new[0].id)] == [1]
          and decision("new")[:2] == (ids["plumber"], new[0].id), detail=str(created.get_json()))
    reused = post("again", occurrence_id=str(ids["plumber"]), new_why_name="  backflow   TESTING ",
                  new_why_what_id="", new_why_group_id="")
    with SessionFactory() as s:
        same = s.scalar(select(func.count(m.BankTransactionReason.id)).where(
            func.lower(m.BankTransactionReason.name) == "backflow testing"))
    check("24/25. a WHY typed again (case, spacing) is reused — never a duplicate — even without a group",
          reused.status_code == 200 and same == 1 and decision("again")[1] == new[0].id)
    with SessionFactory() as s:
        reasons_before = s.scalar(select(func.count(m.BankTransactionReason.id)))
    broken = client.post("/bank/transactions/999999/who-why", headers={"X-Requested-With": "fetch"},
                         data={"csrf_token": csrf, "occurrence_id": str(ids["plumber"]), "new_why_name": "Orphan Grouped",
                               "new_why_what_id": str(ids["what"]), "new_why_group_id": str(ids["facility"]),
                               "return_to": REVIEW_AUG})
    with SessionFactory() as s:
        reasons_after = s.scalar(select(func.count(m.BankTransactionReason.id)))
    check("26. atomic: a failure after the WHY was created leaves no WHY and no association behind",
          broken.status_code == 400 and reasons_after == reasons_before)

    # ------------------------------------------------------------------
    # REGRESSION (32-37)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        configured = config_service.create_why(s, name="Configured Without Group", description=None,
                                               what_id=ids["what"], active=True)
        configured_group = configured.reason_group_id
        s.rollback()
        rules_after = s.scalar(select(func.count(m.BankRecognitionRule.id)))
        standards_after = s.scalar(select(func.count(m.BankReconciliationStandard.id)))
    check("35. Configuration's WHY creation is unchanged (a group stays optional there)", configured_group is None)
    check("32. no Rule is created by Select WHO / WHY", rules_after == rules_before)
    check("37. Standards unchanged", standards_after == standards_before)
    check("33. the confirmed rows left To Reconcile",
          all(f'data-transaction-id="{ids[k]}"' not in client.get(REVIEW_AUG).data.decode() for k in ("first", "new")))

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
