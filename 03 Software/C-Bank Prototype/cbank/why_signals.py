"""WHY signals and WHO WHY rule simulation (BANK_WHO_WHY_MODE_001), read-only.

`signals` evaluates every movement with the one engine and groups the movements whose WHO is recognised but
whose WHY is not determinable, by WHO, Source and reason (pair missing, rule missing, document or
clarification missing, rules in conflict), with the action that resolves each group.
`simulate` shows what a draft WHO WHY rule would change before it is saved or activated: the engine is
evaluated on the WHO's movements without and with the draft. Nothing is written anywhere.
"""
from __future__ import annotations

from types import SimpleNamespace

from .legacy import who_why_rules as wr

ACTIONS = {wr.NEEDS_PAIR: "CLASSIFY_PAIR", wr.NEEDS_RULE: "DEFINE_RULE", wr.NEEDS_DOCUMENT: "PROVIDE_DOCUMENT",
           wr.CONFLICT: "REVIEW_RULES", wr.SPLIT_INCOMPLETE: "OPEN_SPLIT"}


def _decided(r):
    """The WHY outcome of a result: its WHY, or SPLIT for a complete split (BANK_SPLIT_ALLOCATION_001)."""
    return r["why_id"] or ("SPLIT" if (r.get("split") or {}).get("complete") else None)


def _movement(engine, txn, r) -> dict:
    return dict(id=txn.id, date=str(txn.posting_date or ""), description=txn.description_original or "",
                amount_minor=txn.amount_minor, why=r.get("why"), status=r.get("status"),
                detail=next((x.get("message") for x in r["exceptions"] if x["code"] in wr.OPEN_REASONS), None))


def signals(engine) -> dict:
    groups, counts = {}, dict.fromkeys(wr.OPEN_REASONS, 0)
    for txn in engine.txns:
        r = engine.evaluate(txn)
        open_ = [x for x in r["exceptions"] if x["code"] in wr.OPEN_REASONS]
        if not open_ or not r.get("who_id"):
            continue
        code = open_[0]["code"]
        counts[code] += 1
        key = (r["who_id"], txn.payment_instrument_id, code)
        g = groups.get(key)
        if g is None:
            source = engine.c.instruments.get(txn.payment_instrument_id)
            owner = engine.owner(txn)
            g = groups[key] = dict(who_id=r["who_id"], who=r["who_name"], source_id=txn.payment_instrument_id,
                                   source=source.display_name if source else None, owner=owner.name if owner else None,
                                   owner_kind=owner.entity_type if owner else None, reason=code, label=wr.LABELS[code],
                                   action=ACTIONS[code], mode=engine.why_resolver.mode(r["who_id"]), movements=[],
                                   missing=set())
        g["movements"].append(_movement(engine, txn, r))
        g["missing"].update(open_[0].get("missing") or [])
    out = []
    for g in groups.values():
        g["count"] = len(g["movements"])
        g["total_minor"] = sum(mv["amount_minor"] for mv in g["movements"])
        g["missing"] = sorted(g["missing"])
        out.append(g)
    out.sort(key=lambda g: (-g["count"], g["who"] or "", g["source"] or ""))
    return dict(groups=out, counts=counts, movements=sum(counts.values()))


def simulate(engine, spec: dict) -> dict:
    """What the draft rule changes on the movements of its WHOs (the draft counts as active)."""
    spec = wr.validate(engine.db, dict(spec, scope=wr.SCOPE))
    who_ids = set(spec["who_ids"])
    resolver = engine.why_resolver
    before = {}
    for txn in engine.txns:
        r = engine.evaluate(txn)
        if r.get("who_id") in who_ids:
            before[txn.id] = r
    draft = (SimpleNamespace(id="draft"), SimpleNamespace(version_no=0), spec)
    saved = {w: list(resolver.by_who.get(w, [])) for w in who_ids}
    try:
        for w in who_ids:
            resolver.by_who.setdefault(w, []).append(draft)
        rows, summary = [], dict(new_why=0, changed_why=0, unchanged=0, still_open=0, protected=0)
        for tid, old in before.items():
            txn = engine.by_id[tid]
            new = engine.evaluate(txn)
            info = resolver.info_builder.info(txn, who=new.get("who_name"), row=engine.c.rule_row(txn))
            outcome, why_id, missing, detail = resolver.evaluate_rule(spec, txn, info)
            if new.get("protected"):
                effect = "protected"
            elif _decided(new) and not _decided(old):
                effect = "new_why"
            elif _decided(new) and _decided(new) != _decided(old):
                effect = "changed_why"
            elif not _decided(new):
                effect = "still_open"
            else:
                effect = "unchanged"
            summary[effect] += 1
            open_ = next((x for x in new["exceptions"] if x["code"] in wr.OPEN_REASONS), None)
            rows.append(dict(_movement(engine, txn, new), source=new.get("source"), rule=outcome, effect=effect,
                             before=old.get("why"), after=new.get("why"), mode=new.get("why_mode"),
                             open_label=open_["label"] if open_ else None, missing=missing,
                             rule_detail=detail or (engine._why_name(why_id) if why_id else "")))
    finally:
        for w, entries in saved.items():
            resolver.by_who[w] = entries
    rows.sort(key=lambda x: (x["effect"] != "new_why", x["effect"] != "changed_why", x["date"]))
    return dict(rows=rows, summary=summary, movements=len(rows),
                text=wr.describe(spec, engine.c.whys, engine.c.whos))
