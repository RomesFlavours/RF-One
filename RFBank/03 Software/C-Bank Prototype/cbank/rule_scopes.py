"""Review > rules of every scope (BANK_RULE_SCOPE_AND_WHO_CATEGORY_001 §2-3 and §6, Product Owner, 2026-11-03).

One lifecycle for the WHY rules of the three scopes — single WHO, WHO category, general — on the one engine:
define → `simulate` → explicit confirmation → `save` (an inactive draft, or active and applied now).

`simulate` is read-only. It evaluates the draft together with EVERY active rule that concerns the same movements,
with no fixed precedence, and classifies each of those rules:

  EQUIVALENT     same WHY wherever both apply and the other rule covers nothing else: it may be replaced
                 (`future` says whether its conditions imply the draft's too, i.e. also on future data, or the
                 equivalence is only verified on the current movements)
  COMPLEMENTARY  same WHY where both apply, but it also covers movements the draft does not: it is kept
  CONFLICT       a different WHY on some movements: a person decides (keep it as an explicit exception of the
                 draft, change the draft, or leave it); the draft cannot be applied while a conflict is open
  KEPT           a person kept it as a legitimate exception: the draft names its WHO in `exceptions`

The draft's movements are evaluated before and after (with the rules to replace left out), so the person sees
which movements get a WHY, change WHY, stay open, become conflicts or stay protected (human decisions).

`save` repeats the simulation and refuses a token that no longer matches (draft, choices, Bank data, rules or
knowledge changed); the same confirmation cannot be applied twice because saving changes the signature.
Applying = activating the rule (and deactivating the rules the person chose to replace, recorded with
`who_why_rules.supersede`, restorable) and re-evaluating the open movements of the run with the one engine.
"""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

from . import legacy, service
from .legacy import who_why_rules as wr, why_patterns

EQUIVALENT, COMPLEMENTARY, CONFLICT, KEPT = "EQUIVALENT", "COMPLEMENTARY", "CONFLICT", "KEPT"
MATCH = why_patterns.MATCH
KEPT_MARK = "kept_apart"            # marks the exception that names the WHOs kept apart by a person


def _entry(spec):
    return SimpleNamespace(id="draft"), SimpleNamespace(version_no=0), spec


def _decided(r):
    return r.get("why_id") or ("SPLIT" if (r.get("split") or {}).get("complete") else None)


def _anchor_names(engine, spec):
    return [engine.c.whos.get(i) or f"WHO #{i}" for i in spec.get("who_ids", [])]


def with_kept(engine, spec, keep_rules):
    """The draft with one explicit exception naming the WHOs of the specific rules a person keeps apart."""
    names = sorted({n for _r, _v, s in keep_rules for n in _anchor_names(engine, s)})
    exceptions = [e for e in spec.get("exceptions", []) if not e.get(KEPT_MARK)]
    if names:
        exceptions.append({"conditions": [dict(field="who", op="in", value=names)], KEPT_MARK: True})
    out = dict(spec)
    if exceptions:
        out["exceptions"] = exceptions
    else:
        out.pop("exceptions", None)
    return out


def in_scope(resolver, spec, who_id, txn) -> bool:
    if not who_id:
        return False
    if spec["scope"] == wr.SCOPE:
        return who_id in spec["who_ids"]
    if spec["scope"] == wr.SCOPE_CATEGORY:
        category, _basis = resolver.categories.category_for(who_id, txn.payment_instrument_id)
        return category in spec["categories"]
    return True


def _implies(resolver, other, spec) -> bool:
    """True when every movement the other rule decides is, by its conditions, decided the same way by the draft:
    the draft's anchor contains the other's, every draft condition is also one of the other's, and the draft has
    no exception. Then the equivalence holds on future movements too, not only on the current ones."""
    if spec.get("exceptions") or other.get("why_id") != spec.get("why_id") or other.get("document") != spec.get("document"):
        return False
    if spec["scope"] == wr.SCOPE:
        anchored = other["scope"] == wr.SCOPE and set(other["who_ids"]) <= set(spec["who_ids"])
    elif spec["scope"] == wr.SCOPE_CATEGORY:
        if other["scope"] == wr.SCOPE_CATEGORY:
            anchored = set(other["categories"]) <= set(spec["categories"])
        elif other["scope"] == wr.SCOPE:
            # only a CONFIRMED category holds on every Source; a declaration is limited to its Sources
            anchored = all(resolver.categories.confirmed.get(w) in spec["categories"] for w in other["who_ids"])
        else:
            anchored = False
    else:
        anchored = True
    own = [json.dumps(c, sort_keys=True) for c in other.get("conditions", [])]
    return anchored and all(json.dumps(c, sort_keys=True) in own for c in spec.get("conditions", []))


def simulate(engine, results, spec, *, replace=(), keep=(), group_ids=()) -> dict:
    """Read-only. `results`: the run's results (they say which WHO each movement has); `replace`: rule ids the
    person proposes to deactivate; `keep`: rule ids kept apart as exceptions; `group_ids`: the movements of the
    group under review (their outcome is reported separately)."""
    resolver = engine.why_resolver
    active = {r.id: (r, v, s) for r, v, s in resolver.rules}
    replace = [i for i in replace if i in active]
    keep = [i for i in keep if i in active and active[i][2]["scope"] == wr.SCOPE]
    spec = wr.validate(engine.db, with_kept(engine, dict(spec), [active[i] for i in keep]))
    whys = engine.c.whys
    population, stats = [], {}
    for r in results:
        txn = engine.by_id.get(r["txn_id"])
        if txn is None or not r.get("who_id"):
            continue
        applicable = resolver.applicable(r["who_id"], txn)
        mine = in_scope(resolver, spec, r["who_id"], txn)
        if not mine and not any(e[0].id in replace for e in applicable):
            continue
        info = resolver.info_builder.info(txn, who=r.get("who_name"), row=engine.c.rule_row(txn))
        draft = resolver.evaluate_rule(spec, txn, info) if mine else (why_patterns.NO_MATCH, None, [], "")
        touched = draft[0] != why_patterns.NO_MATCH
        for rule, version, other in applicable:
            outcome, why_id, _missing, _detail = resolver.evaluate_rule(other, txn, info)
            if outcome != MATCH:
                continue
            s = stats.setdefault(rule.id, dict(rule_id=rule.id, version=version.version_no, scope=other["scope"],
                                               text=version.rule_text, why=(whys[why_id].name if why_id in whys else None),
                                               matched=0, same=0, different=0, only_other=0, movements=[]))
            s["matched"] += 1
            if draft[0] == MATCH:
                s["same" if draft[1] == why_id else "different"] += 1
                if draft[1] != why_id:
                    s["movements"].append(txn.id)
            else:
                s["only_other"] += 1
            touched = True
        if touched:
            population.append(txn)
    rules = []
    for rule_id, s in stats.items():
        other = active[rule_id][2]
        if rule_id in keep:
            s["kind"] = KEPT
        elif s["different"]:
            s["kind"] = CONFLICT
        elif s["same"] and not s["only_other"]:
            s["kind"] = EQUIVALENT
        elif s["same"] or s["only_other"]:
            s["kind"] = COMPLEMENTARY
        else:
            continue
        s["future"] = s["kind"] == EQUIVALENT and _implies(resolver, other, spec)
        s["replaceable"] = s["kind"] == EQUIVALENT
        s["keepable"] = s["kind"] in (CONFLICT, KEPT) and other["scope"] == wr.SCOPE and spec["scope"] != wr.SCOPE
        s["replace"] = rule_id in replace
        s["movements"] = s["movements"][:50]
        rules.append(s)
    for rule_id in replace:
        if rule_id not in stats:
            r, v, other = active[rule_id]
            rules.append(dict(rule_id=rule_id, version=v.version_no, scope=other["scope"], text=v.rule_text,
                              why=None, matched=0, same=0, different=0, only_other=0, movements=[], kind=EQUIVALENT,
                              future=False, replaceable=True, keepable=False, replace=True))
    refused = [s["rule_id"] for s in rules if s["replace"] and not s["replaceable"]]
    if refused:
        raise ValueError("Only an equivalent rule can be replaced: " + ", ".join(f"#{i}" for i in refused) + ".")

    rows, summary = [], dict(new_why=0, changed_why=0, lost_why=0, conflict=0, still_open=0, unchanged=0, protected=0)
    before = {t.id: engine.evaluate(t) for t in population}
    with resolver.variant(add=[_entry(spec)], hide=replace):
        after = {t.id: engine.evaluate(t) for t in population}
    group = set(group_ids)
    group_resolved = 0
    for txn in population:
        old, new = before[txn.id], after[txn.id]
        if new.get("protected"):
            effect = "protected"
        elif any(x["code"] == wr.CONFLICT for x in new["exceptions"]):
            effect = "conflict"
        elif _decided(new) and not _decided(old):
            effect = "new_why"
        elif _decided(new) and _decided(new) != _decided(old):
            effect = "changed_why"
        elif _decided(old) and not _decided(new):
            effect = "lost_why"
        elif not _decided(new):
            effect = "still_open"
        else:
            effect = "unchanged"
        summary[effect] += 1
        if txn.id in group and effect in ("new_why", "changed_why"):
            group_resolved += 1
        rows.append(dict(id=txn.id, date=str(txn.posting_date or ""), description=txn.description_original or "",
                         amount_minor=txn.amount_minor, source=new.get("source"), who=new.get("who_name"),
                         before=old.get("why"), after=new.get("why"), effect=effect, in_group=txn.id in group))
    order = ("conflict", "lost_why", "changed_why", "new_why", "protected", "still_open", "unchanged")
    rows.sort(key=lambda x: (order.index(x["effect"]), not x["in_group"], x["date"]))
    conflicts = [s for s in rules if s["kind"] == CONFLICT]
    signature = service.current_bank_signature()
    return dict(spec=spec, text=wr.describe(spec, whys, engine.c.whos), rules=rules, rows=rows[:400],
                movements=len(rows), summary=summary, group_movements=len(group), group_resolved=group_resolved,
                open_conflicts=len(conflicts) + summary["conflict"], replace=sorted(replace), keep=sorted(keep),
                verified_on="current movements of the run", token=token(spec, replace, keep, signature))


def token(spec, replace, keep, signature) -> str:
    payload = json.dumps([spec, sorted(replace), sorted(keep), signature], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


def save(con, run_id, results, spec, *, mode, replace, keep, expected, account_id, group_ids=(), title=None) -> dict:
    """mode DRAFT: saved INACTIVE (nothing changes). mode APPLY: active now, replaced rules deactivated, open
    movements of the run re-evaluated. The simulation is repeated first: a different token is refused."""
    if mode not in ("DRAFT", "APPLY"):
        raise ValueError("Choose Save draft or Save and apply now.")
    eng = service.new_engine(con)
    try:
        sim = simulate(eng, results, spec, replace=replace, keep=keep, group_ids=group_ids)
    finally:
        eng.db.close()
    if sim["token"] != expected:
        raise ValueError("The simulation is no longer valid: the rule, the choices, the data or the rules changed. "
                         "Simulate again before saving.")
    if mode == "APPLY" and sim["open_conflicts"]:
        raise ValueError("Decide the conflicts first: keep the other rule as an exception, or change the rule.")
    from sqlalchemy import text
    db = legacy._writer_session()
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        rule = wr.save_rule(db, sim["spec"], account_id=account_id, active=(mode == "APPLY"), title=title)
        replaced = None
        if mode == "APPLY" and sim["replace"]:
            replaced = wr.supersede(db, rule.id, sim["replace"], account_id=account_id, evidence=dict(
                summary=sim["summary"], rules=[dict(rule_id=s["rule_id"], kind=s["kind"], future=s["future"],
                                                   matched=s["matched"]) for s in sim["rules"] if s["replace"]],
                verified_on=sim["verified_on"], token=sim["token"]))
        db.commit()
        rule_id, status = rule.id, rule.status
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    changed = service.reevaluate(con, run_id) if mode == "APPLY" else 0
    return dict(rule_id=rule_id, status=status, replaced=replaced, reevaluated_changed=changed,
                expected=sim["summary"], text=sim["text"])
