"""Representative real movements for the MVP cases (spec §5).

Selection uses the operational Bank's CURRENT data only as a way to find
examples; the engine then decides independently. Deterministic: most recent
movements first, a fixed number per case.
"""
from __future__ import annotations

from .legacy import clean

CASES = {
    "PERSON_TO_LLC": "Expense paid by a person for an LLC",
    "LLC_TO_PERSON": "Expense paid by an LLC for a person",
    "LLC_TO_LLC": "Expense paid by one LLC for another LLC",
    "BUSINESS": "Ordinary business purchase",
    "REVENUE": "Revenue",
    "PATRIMONIAL": "Patrimonial operation (asset, financing, equity)",
    "TRANSFER": "Transfer between accounts",
    "CARD_PAYMENT": "Credit card payment",
    "WHO_UNKNOWN": "Unknown WHO",
    "WHO_AMBIGUOUS": "Ambiguous WHO",
    "MULTI_LLC_PROFILE": "Profile with different outcomes per LLC",
}
PER_CASE = 4


def select(engine, per_case: int = PER_CASE) -> dict[str, list[int]]:
    c = engine.c
    picked: dict[str, list[int]] = {k: [] for k in CASES}

    def add(case, txn):
        if len(picked[case]) < per_case and txn.id not in picked[case]:
            picked[case].append(txn.id)

    multi_whos = set()
    for rule, version, spec in engine.photos:
        whoms = {b.get("whom_id") for b in spec.get("branches", []) if b.get("whom_id")}
        if len(whoms) > 1:
            multi_whos.add(clean(spec.get("who")))
    multi_seen: dict[str, set] = {}

    for txn in sorted(engine.txns, key=lambda t: (t.posting_date, t.id), reverse=True):
        b = engine.bank_decision(txn)
        payer = engine.owner(txn)
        payer_kind = payer.entity_type if payer else None
        ben = c.entities.get(b["beneficiary_id"]) if b["beneficiary_id"] else None
        cat = c.classes.get(b["category_id"])
        code = (cat.code if cat else "") or ""
        why = c.whys.get(b["why_id"])
        mt = engine.matches.get(txn.id)
        if payer_kind == "PERSONAL" and ((ben and ben.entity_type == "LEGAL") or (
                cat and cat.statement_type == "PROFIT_LOSS" and not code.startswith("4") and txn.amount_minor < 0
                and not (why and (why.code or "").startswith("OWNER_PERSONAL")))):
            add("PERSON_TO_LLC", txn)
        if payer_kind == "LEGAL" and ((ben and ben.entity_type == "PERSONAL")
                                      or (why and (why.code or "").startswith("OWNER_PERSONAL"))):
            add("LLC_TO_PERSON", txn)
        if payer_kind == "LEGAL" and ben and ben.entity_type == "LEGAL" and ben.id != payer.id:
            add("LLC_TO_LLC", txn)
        if payer_kind == "LEGAL" and cat and cat.statement_type == "PROFIT_LOSS" and txn.amount_minor < 0 \
                and not code.startswith("4") and b["source"] == "HUMAN" and not mt:
            add("BUSINESS", txn)
        if txn.amount_minor > 0 and cat and cat.statement_type == "PROFIT_LOSS" and code.startswith("4"):
            add("REVENUE", txn)
        if code.startswith(("15", "26")) and not mt:   # capital assets and financing first
            add("PATRIMONIAL", txn)
        if mt and mt.kind == "TRANSFER":
            add("TRANSFER", txn)
        if mt and mt.kind == "CARD_SETTLEMENT":
            add("CARD_PAYMENT", txn)
        if not b["who_id"]:
            add("WHO_UNKNOWN", txn)
        text = clean(txn.description_original)
        for who in multi_whos:
            if who and who in text:
                seen = multi_seen.setdefault(who, set())
                key = b["beneficiary_id"] or (payer.id if payer else None)
                if key not in seen or len(picked["MULTI_LLC_PROFILE"]) < 2:
                    seen.add(key)
                    add("MULTI_LLC_PROFILE", txn)
    # Pick one capital asset and one financing movement at least, when they exist.
    by_prefix = {"15": [], "26": []}
    for tid in picked["PATRIMONIAL"]:
        b = engine.bank_decision(engine.by_id[tid])
        code = (c.classes[b["category_id"]].code if b["category_id"] in c.classes else "") or ""
        by_prefix.get(code[:2], []).append(tid)
    if not by_prefix["26"] or not by_prefix["15"]:
        missing = "26" if not by_prefix["26"] else "15"
        for txn in sorted(engine.txns, key=lambda t: (t.posting_date, t.id), reverse=True):
            b = engine.bank_decision(txn)
            code = (c.classes[b["category_id"]].code if b["category_id"] in c.classes else "") or ""
            if code.startswith(missing) and txn.id not in picked["PATRIMONIAL"]:
                if len(picked["PATRIMONIAL"]) >= per_case:
                    picked["PATRIMONIAL"].pop()
                picked["PATRIMONIAL"].append(txn.id)
                break
    # Ambiguous WHO: found by the engine itself (rules disagree), not by Bank data.
    for txn in sorted(engine.txns, key=lambda t: (t.posting_date, t.id), reverse=True):
        if len(picked["WHO_AMBIGUOUS"]) >= per_case:
            break
        names = set()
        row = None
        for rule, version, spec in engine.legacy:
            row = row or c.rule_row(txn)
            try:
                ex = engine_execute(spec, row)
            except Exception:
                continue
            if ex.outcome == "MATCH" and ex.who:
                names.add(clean(ex.who))
            if len(names) > 1:
                add("WHO_AMBIGUOUS", txn)
                break
    return picked


def engine_execute(spec, row):
    from .legacy import ai_rules
    return ai_rules.execute(spec, row)


def case_index(picked: dict[str, list[int]]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for case, ids in picked.items():
        for i in ids:
            out.setdefault(i, []).append(case)
    return out
