"""Consolidate the legacy WHY names of the Bank AI rules (Product Owner decisions 61-84, 2026-10-24).

The legacy text rules still named WHYs that the USAR catalog no longer has, so they could not classify.
This script, in one transaction:

* creates ONLY the WHYs the Product Owner approved, each on an EXISTING WHAT (decisions 64-67, 77, 80, 83),
  and the three provisional WHYs without WHAT in the "Provisional" group (decisions 74-76, 79 — the only
  exception to BANK_WHY_REQUIRES_WHAT_001, see `why_what.PROVISIONAL_WHY_CODES`);
* gives each affected rule a NEW VERSION through the normal save path (`ai_rule_operations.save_rule`):
  earlier versions, application history and rollback stay as they are;
* marks "WHY to verify" the rules whose WHY depends on facts not known yet (which vehicle; the relationship
  behind an owner draw), so that creating the approved WHYs never makes them classify by themselves;
* records the two WHO -> WHY associations the decisions approve (CARD FEE, Cash Redemption).

It never touches a movement, a decision or an allocation: the new versions act on future imports and on
the C-Bank runs (dry runs). Rules still pending (WALMART #17/#31, Appliance #100, fees #67, EV charging #10,
Amazon #107) are left exactly as they are. Run without --apply for a dry run (rolled back).

    python consolidate_legacy_why_rules.py --db <rfone.db> [--apply] [--log <changes.json>]
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import ai_rule_operations as ops
from rfone_data_store.bank_reconciliation import classification, flow, why_catalog, why_what
from rfone_data_store.database import create_configured_engine, create_session_factory

TAG = "BANK_WHY_LEGACY_CONSOLIDATION_001"
PROVENANCE = ("PRODUCT_OWNER_DECISION", "decisions 61-84 (2026-10-24)")

# (code, name, WHAT code or None, group code, decision)
NEW_WHYS = [
    ("COMPANY_CARS_FUEL", "Company Cars - Fuel", "7920", "VEHICLE_TRAVEL", "64"),
    ("COMPANY_CARS_LEASE", "Company Cars - Lease", "7910", "VEHICLE_TRAVEL", "65"),
    ("COMPANY_CARS_INSURANCE", "Company Cars - Insurance", "7730", "VEHICLE_TRAVEL", "66"),
    ("COMPANY_CARS_MAINTENANCE", "Company Cars - Maintenance", "7930", "VEHICLE_TRAVEL", "67"),
    ("MEMBER_OWNER_DRAW", "Member / Owner Draw", "3400", "OWNER_PERSONAL", "77"),
    ("MEMBER_CONTRIBUTION", "Member Contribution", "3300", "MONEY_MOVEMENT", "80"),
    ("CASH_WITHDRAWAL_BUSINESS", "Cash Withdrawal for Business Payments", "1130", "MONEY_MOVEMENT", "80"),
    ("CASHBACK_CARD_REWARDS", "Cashback / Credit Card Rewards", "8500", "OTHER_INCOME_EXPENSE", "83"),
    ("ONLINE_PURCHASE_UNIDENTIFIED", "Online Purchase – Unidentified", None, "PROVISIONAL", "74"),
    ("CASH_CHECK_DEPOSIT", "Cash / Check Deposit", None, "PROVISIONAL", "75"),
    ("WITHDRAWAL", "Withdrawal", None, "PROVISIONAL", "76"),
]
DEFINITIONS = {
    "COMPANY_CARS_FUEL": "Fuel or charging of a COMPANY vehicle. The vehicle decides it, never the card used.",
    "COMPANY_CARS_LEASE": "Lease of a COMPANY vehicle. The vehicle decides it, never the card used.",
    "COMPANY_CARS_INSURANCE": "Insurance of a COMPANY vehicle. The vehicle decides it, never the card used.",
    "COMPANY_CARS_MAINTENANCE": "Repairs, maintenance or washing of a COMPANY vehicle. The vehicle decides it.",
    "MEMBER_OWNER_DRAW": "Money moved from the LLC to its owner or member for personal use. Not a P&L cost; "
                         "requires the relationship with the owner/member to be verified.",
    "MEMBER_CONTRIBUTION": "Money the owner or member puts into the LLC. Not revenue.",
    "CASH_WITHDRAWAL_BUSINESS": "Cash withdrawn for the company's cash payments. No cost at withdrawal: "
                                "the cost arises when the cash is spent.",
    "CASHBACK_CARD_REWARDS": "Cashback or rewards redeemed on a credit card. Not a card statement payment.",
    "ONLINE_PURCHASE_UNIDENTIFIED": "PROVISIONAL: an online purchase whose nature is not known yet. "
                                    "The movement stays an Exception until its definitive WHY is set.",
    "CASH_CHECK_DEPOSIT": "PROVISIONAL: a cash or check deposit whose nature (revenue, member contribution, loan, "
                          "transfer, other) is not established yet. Never revenue by default.",
    "WITHDRAWAL": "PROVISIONAL: a cash withdrawal whose destination (owner draw, business cash, other) is not "
                  "established yet. On a personal Source it is normally a personal withdrawal.",
}

# rule id -> list of (old text, new text) replacements, applied to the rule text and to every fixed WHY name.
RENAME = {
    9: [("Business Meal", "Business Meals & Entertainment")],
    33: [("Building / Facility Maintenance", "Building, Facility & Grounds Maintenance")],
    35: [("Meals / Entertainment", "Owner Personal — Restaurant"), ("BUSINESS Meal", "Business Meals & Entertainment")],
    36: [("Card Payment", "Credit Card Statement Payment")],
    38: [("Card Payment", "Credit Card Statement Payment")],
    44: [("Loan principal advanced into the account", "Loan Proceeds Received")],
    45: [("Building / Facility Maintenance", "Building, Facility & Grounds Maintenance")],
    47: [("Card Payment", "Credit Card Statement Payment")],
    50: [("Card Payment", "Credit Card Statement Payment")],
    55: [("Business Meal", "Business Meals & Entertainment")],
    56: [("Business Meal", "Business Meals & Entertainment")],
    60: [("Building / Facility Maintenance", "Building, Facility & Grounds Maintenance")],
    61: [("Building / Facility Maintenance", "Building, Facility & Grounds Maintenance")],
    65: [("Card Payment", "Cashback / Credit Card Rewards")],
    78: [("Foreign transaction fee charged by the card issuer", "Foreign Transaction Fee")],
    85: [("County Tax", "Property & Occupancy Taxes")],
    88: [("Business Meal", "Business Meals & Entertainment")],
    99: [("Meals / Entertainment", "Business Meals & Entertainment")],
}
DECISION_OF = {9: "63", 33: "62", 35: "61, 63, 81", 36: "70", 38: "70", 44: "69", 45: "62", 47: "70", 50: "70",
               55: "63", 56: "63", 60: "62", 61: "62", 65: "83", 78: "68, 84", 85: "71", 88: "63", 99: "61",
               30: "63, 81", 98: "61, 81"}
# Decision 81: restaurant on a personal card -> Owner Personal — Restaurant; otherwise a business meal.
PERSONAL_MEAL = {30: "BUSINESS Meal", 98: "Meals / Entertainment"}
PERSONAL_SENTENCE = (" If the Source is a card and its classification is Personal, the WHY is “Owner Personal — "
                     "Restaurant”; in all other cases the WHY is “Business Meals & Entertainment”.")
# WHY to verify: vehicle rules (decisions 64-67, 78) and the owner draw to verify (decision 77).
VERIFY = {
    34: "Company Cars - Fuel", 53: "Company Cars - Fuel", 68: "Company Cars - Fuel", 69: "Company Cars - Fuel",
    87: "Company Cars - Fuel", 92: "Company Cars - Fuel", 104: "Company Cars - Fuel", 106: "Company Cars - Fuel",
    43: "Company Cars - Insurance", 54: "Company Cars - Insurance", 62: "Company Cars - Lease",
    93: "Company Cars - Maintenance", 75: "Member / Owner Draw",
}
PERSONAL_OF = {"Company Cars - Fuel": "Vehicle - Fuel", "Company Cars - Insurance": "Vehicle - Insurance",
               "Company Cars - Lease": "Vehicle - Lease", "Company Cars - Maintenance": "Vehicle - Repairs & Maintenance"}
# WHO -> WHY associations approved by the decisions (additive; nothing is replaced).
ASSOCIATIONS = [("CARD FEE", "FOREIGN_TRANSACTION_FEE", "84"), ("CASH REDEMPTION", "CASHBACK_CARD_REWARDS", "83")]


def quoted(text: str, old: str, new: str) -> str:
    out = text
    for left, right in (("“", "”"), ('"', '"'), ("'", "'")):
        out = out.replace(f"{left}{old}{right}", f"{left}{new}{right}")
    return out


def fixed_whys(spec: dict):
    slots = [spec.get("why")] + [b.get("why") for b in spec.get("branches") or []]
    return [w for w in slots if isinstance(w, dict) and w.get("mode") == "fixed"]


def plan_rule(rule_id: int, text: str, spec: dict) -> tuple[str, dict]:
    spec = copy.deepcopy(spec)
    if rule_id in RENAME:
        for old, new in RENAME[rule_id]:
            if old not in text:
                raise ValueError(f"rule #{rule_id}: “{old}” is not in its text")
            text = quoted(text, old, new)
            for w in fixed_whys(spec):
                if w["name"] == old:
                    w["name"] = new
    elif rule_id in PERSONAL_MEAL:
        old = PERSONAL_MEAL[rule_id]
        w = spec.get("why")
        if not (isinstance(w, dict) and w.get("name") == old and not spec.get("branches")):
            raise ValueError(f"rule #{rule_id}: unexpected structure")
        text = text.rstrip() + PERSONAL_SENTENCE
        spec["why"] = None
        spec["branches"] = [
            {"conditions": [{"field": "source_type", "op": "is", "value": "card"},
                            {"field": "source_class", "op": "is", "value": "Personal"}],
             "who": None, "why": {"mode": "fixed", "name": "Owner Personal — Restaurant"}, "for_whom": None},
            {"conditions": [], "who": None, "why": {"mode": "fixed", "name": "Business Meals & Entertainment"},
             "for_whom": None}]
    elif rule_id in VERIFY:
        old = VERIFY[rule_id]
        if old not in text:
            raise ValueError(f"rule #{rule_id}: “{old}” is not in its text")
        if old == "Member / Owner Draw":
            note = ("to verify: “Member / Owner Draw” only after the relationship with the owner or member "
                    "has been verified")
        else:
            note = (f"to verify: “{old}” if the vehicle is a company vehicle, “{PERSONAL_OF[old]}” if it is a "
                    "personal vehicle; the card used does not decide it")
        text = quoted(text, old, note)
        touched = 0
        for slot in [spec] + list(spec.get("branches") or []):
            w = slot.get("why")
            if isinstance(w, dict) and w.get("mode") == "fixed" and w.get("name") == old:
                slot["why"] = {"mode": "to_verify"}
                touched += 1
        if not touched:
            raise ValueError(f"rule #{rule_id}: no fixed WHY “{old}”")
    else:
        raise ValueError(f"rule #{rule_id} is not in the approved list")
    spec["kind"] = "STRUCTURED"
    spec["coverage"] = [{"instruction": text, "represented_by": f"{TAG}: Product Owner decisions "
                         f"{DECISION_OF.get(rule_id, '64-67, 77, 78')}, translated without AI"}]
    spec["unsupported"] = []
    return text, spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--log")
    args = parser.parse_args()
    db_path = Path(args.db).resolve()
    if not db_path.is_file():
        print(f"Database not found: {db_path}")
        return 1
    engine = create_configured_engine(f"sqlite:///{db_path.as_posix()}")
    session = create_session_factory(engine)()
    log = dict(tag=TAG, db=str(db_path), applied=args.apply, whys=[], rules=[], associations=[])
    try:
        admin = session.scalars(select(m.RFOneAccount).where(m.RFOneAccount.username == "admin")).first()
        groups = {g.code: g for g in session.scalars(select(m.BankReasonGroup))}
        if "PROVISIONAL" not in groups:
            order = max((g.display_order for g in groups.values()), default=0) + 1
            groups["PROVISIONAL"] = m.BankReasonGroup(code="PROVISIONAL", name="Provisional", display_order=order,
                                                      active=True)
            session.add(groups["PROVISIONAL"])
            session.flush()
            log["whys"].append(dict(group="PROVISIONAL", created=True))
        whats = {a.code: a for a in session.scalars(select(m.BankAccountingClassification))}
        reasons = {r.code: r for r in session.scalars(select(m.BankTransactionReason))}
        by_name = {flow.clean(r.name): r for r in reasons.values() if r.status == "ACTIVE"}
        for code, name, what_code, group, decision in NEW_WHYS:
            existing = reasons.get(code) or by_name.get(flow.clean(name))
            if existing is not None:
                log["whys"].append(dict(code=existing.code, name=existing.name, id=existing.id, created=False))
                continue
            what = whats[what_code] if what_code else None
            if what is not None and not why_what.valid_what(what):
                raise ValueError(f"WHAT {what_code} is not a valid posting WHAT")
            reason = classification.create_transaction_reason(
                session, code=code, name=name, accounting_classification_id=what.id if what else None,
                description=f"{DEFINITIONS[code]} (decision {decision}, {TAG})")
            reason.reason_group_id = groups[group].id
            session.flush()
            if what is None and not why_what.is_provisional(session, reason):
                raise ValueError(f"{code} should be provisional")
            reasons[code] = reason
            log["whys"].append(dict(code=code, name=name, id=reason.id, what=what_code, group=group,
                                    decision=decision, created=True))

        def generate_for(spec):
            return lambda _prompt: dict(spec)

        for rule_id in sorted(set(RENAME) | set(PERSONAL_MEAL) | set(VERIFY)):
            rule = session.get(m.BankAiRule, rule_id)
            if rule is None or rule.deleted_at is not None:
                raise ValueError(f"rule #{rule_id} not found")
            current = ops.current_version(rule)
            text, spec = plan_rule(rule_id, current.rule_text, flow.unpack(current))
            for w in fixed_whys(spec):
                target = by_name.get(flow.clean(w["name"])) or next(
                    (r for r in reasons.values() if r.name == w["name"]), None)
                if target is None or why_what.assignment_problem(session, target):
                    raise ValueError(f"rule #{rule_id}: WHY “{w['name']}” is not usable")
            result = ops.save_rule(
                session, rule_id=rule_id, rule_text=text, create_missing_who=current.create_missing_who,
                apply_future=rule.apply_future, origin_transaction_id=None, account_id=admin.id if admin else None,
                generate=generate_for(spec), override_protected=current.override_protected)
            if not result.new_version:
                raise ValueError(f"rule #{rule_id}: no new version was created")
            interpretation = session.get(m.BankAiRuleInterpretation, result.version.interpretation_id)
            interpretation.provider, interpretation.model = PROVENANCE
            session.flush()
            log["rules"].append(dict(rule=rule_id, from_version=current.version_no,
                                     to_version=result.version.version_no, decision=DECISION_OF.get(rule_id, "64-67, 77, 78"),
                                     kind=("rename" if rule_id in RENAME else "personal meal branch"
                                           if rule_id in PERSONAL_MEAL else "WHY to verify"),
                                     text=text))
        for who_name, why_code, decision in ASSOCIATIONS:
            who = next((o for o in session.scalars(select(m.BankOccurrence).where(m.BankOccurrence.status == "ACTIVE"))
                        if flow.clean(o.canonical_name) == flow.clean(who_name)), None)
            if who is None:
                raise ValueError(f"WHO {who_name} not found")
            association = why_catalog.associate(session, occurrence_id=who.id,
                                                transaction_reason_id=reasons[why_code].id, source="HUMAN",
                                                confirm=False)
            previous_source = association.source
            if association.source != "HUMAN":
                # An association seen only in history becomes an approved one: the decision approves it.
                association.source = "HUMAN"
                session.flush()
            log["associations"].append(dict(who=who.canonical_name, who_id=who.id, why=reasons[why_code].name,
                                            decision=decision, previous_source=previous_source))
        if args.apply:
            session.commit()
        else:
            session.rollback()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()
    if args.log:
        Path(args.log).write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{'APPLIED' if args.apply else 'DRY RUN (rolled back)'} — WHYs created: "
          f"{sum(1 for w in log['whys'] if w.get('created') and 'code' in w)}, rules versioned: {len(log['rules'])}, "
          f"associations: {len(log['associations'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
