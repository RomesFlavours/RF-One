"""Group analysis for Guided Reconciliation (Review): analyse ALL the movements of one group and propose a WHY rule.

Read-only. It reuses, unchanged, the WHY discovery of BANK_WHY_PATTERNS_001 (`why_patterns`): the movements of the
group's WHO (its whole history, decided movements included as examples and counterexamples) are grouped by
description format; the AI reads each format once, in batches (within the approved context sharing: up to three
masked descriptions per format, counts and conditions — never amounts, dates, account or card numbers); RF-One code
consolidates the readings into verifiable conditions. Each proposal becomes a draft WHO WHY rule
(BANK_WHO_WHY_MODE_001) and is simulated with the existing `why_signals.simulate` on the WHO's movements: the draft
counts as active only inside the simulation. Nothing is saved, activated or applied here; the engine session is
opened read-only (`legacy.session`, PRAGMA query_only).

The per-call limit of the provider is a batching detail (`why_patterns.AI_BATCH` formats per call), never a limit on
the number of movements analysed. A rule resting on the WHO name alone is never proposed.

Completeness: missing files or answers of OTHER Sources never stop this analysis. Requests that concern a Source
of this group are reported as limitations of the analysis, with what is missing.
"""
from __future__ import annotations

import dataclasses
from collections import Counter, defaultdict

from . import why_signals
from .legacy import who_why_rules as wr, why_patterns as wp

PROPOSAL, NO_RULE, LIMITED, ERROR = "PROPOSAL", "NO_RULE", "LIMITED", "ERROR"


def _source_breakdown(mvs) -> list[dict]:
    c = Counter((mv.info.get("source") or "—", mv.info.get("subject") or "—") for mv in mvs)
    return [dict(source=s, subject=k, movements=n) for (s, k), n in c.most_common()]


def _group_limits(engine, rows, group_mvs) -> list[dict]:
    """What is missing for THIS group only: WHO not recognised, documents the WHY needs, coverage requests on
    the group's own Sources. Requests about other Sources are not listed."""
    out = []
    no_who = [r["txn_id"] for r in rows if not r.get("who_id")]
    if no_who:
        out.append(dict(kind="WHO_MISSING", movements=len(no_who), ids=no_who,
                        text="WHO not recognised: a WHY rule needs the WHO first."))
    docs = [r["txn_id"] for r in rows if any(e["code"] == wr.NEEDS_DOCUMENT for e in r["exceptions"])]
    if docs:
        out.append(dict(kind="DOCUMENT_MISSING", movements=len(docs), ids=docs,
                        text="A document or clarification is needed to read the WHY of these movements."))
    sources = {engine.by_id[r["txn_id"]].payment_instrument_id for r in rows if r["txn_id"] in engine.by_id}
    amazon = any("AMAZON" in (r.get("who_name") or "").upper() or "AMZN" in (r.get("who_name") or "").upper()
                 for r in rows)
    try:
        from rfone_data_store.bank_reconciliation import intake
        check = intake.completeness(engine.db)
        for gap in check.gaps:
            if gap.source_id in sources or (gap.kind == intake.GAP_AMAZON_REPORT and amazon):
                out.append(dict(kind="COVERAGE", source=gap.source, start=str(gap.start), end=str(gap.end),
                                text=f"{gap.source}: {gap.reason} ({gap.start} – {gap.end}). Movements of these dates "
                                     "may be missing from the group; the analysis uses the movements available."))
    except Exception as exc:  # noqa: BLE001 — the analysis goes on; the check itself is reported as unavailable
        out.append(dict(kind="COVERAGE_UNKNOWN", text=f"Coverage of this group's Sources could not be checked ({exc})."))
    finally:
        engine.db.rollback()
    return out


def _who_spec(proposal, who_ids, whys) -> dict | None:
    """The consolidated proposal as a WHO WHY rule. The WHO is the rule's anchor: a condition on the WHO name is
    redundant and dropped; what remains must be a real condition (never the WHO name alone)."""
    conditions = [c for c in proposal["conditions"] if c["field"] != "who"]
    if not conditions:
        return None
    why = whys[proposal["why_id"]]
    exceptions = [e for e in proposal.get("exceptions", []) if all(c["field"] != "who" for c in e["conditions"])]
    return dict(engine=wp.ENGINE, version=wp.SPEC_VERSION, scope=wr.SCOPE, who_ids=sorted(who_ids), why_id=why.id,
                why=why.name, conditions=conditions, exceptions=exceptions)


def _row(mv) -> dict:
    return dict(id=mv.id, date=str(mv.date or ""), description=mv.info["description"][:160],
                amount_minor=mv.info["_amount"], source=mv.info.get("source"), subject=mv.info.get("subject"))


def analyze(engine, rows: list[dict], generate) -> dict:
    """Analyse the open movements `rows` (C-Bank results) of one group. Read-only."""
    group_ids = {r["txn_id"] for r in rows}
    who_ids = {r["who_id"] for r in rows if r.get("who_id")}
    who_names = {r["who_name"] for r in rows if r.get("who_id") and r.get("who_name")}
    base = dict(movements=len(group_ids), who=sorted(who_names))
    movements, meta = wp.load_movements(engine.db)
    whys, whats = meta["whys"], meta["whats"]
    by_id = {mv.id: mv for mv in movements}
    group_mvs = [by_id[i] for i in sorted(group_ids) if i in by_id]
    base["sources"] = _source_breakdown(group_mvs)
    limits = _group_limits(engine, rows, group_mvs)
    if not who_ids:
        return dict(base, state=LIMITED, limits=limits, proposals=[], formats=[], excluded=[])
    # The WHO's whole history: decided movements are examples and counterexamples of the proposal.
    scope = [mv for mv in movements if not mv.structural and (mv.id in group_ids or mv.info.get("who") in who_names)]
    formats = wp._format_groups(scope)
    engine.db.rollback()   # no read transaction stays open during the AI step
    readings, errors, calls, _cache = wp.read_formats(formats, whys, generate, whats=whats)
    if errors and not readings:
        return dict(base, state=ERROR, limits=limits, proposals=[], formats=[], excluded=[], ai_calls=calls,
                    errors=errors)
    wp.label_movements(scope, readings, whys, meta["provisional"])
    approved = [s for _r, _v, s in wp.active_rules(engine.db)]
    # The WHO is already the rule's anchor: consolidation looks for verifiable conditions OTHER than the WHO name
    # (format, Source ownership at the date, direction, Source information, evidence), or splits into subgroups.
    anchored = [dataclasses.replace(mv, info={k: v for k, v in mv.info.items() if k != "who"}) for mv in scope]
    consolidated = wp.consolidate(anchored, whys, approved=approved, provisional=meta["provisional"])

    proposals, name_only, covered = [], [], defaultdict(set)
    for p in consolidated:
        spec = _who_spec(p, who_ids, whys)
        if spec is None:
            name_only.append(whys[p["why_id"]].name)
            continue
        try:
            wr.validate(engine.db, spec)
            sim = why_signals.simulate(engine, spec)
        except ValueError as exc:
            name_only.append(f"{whys[p['why_id']].name} ({exc})")
            continue
        finally:
            engine.db.rollback()
        in_group = [x for x in sim["rows"] if x["id"] in group_ids]
        resolved = [x for x in in_group if x["rule"] == wp.MATCH and x["effect"] in ("new_why", "changed_why")]
        if not resolved:
            continue
        for x in resolved:
            covered[x["id"]].add(spec["why_id"])
        reason = next((rd[3] for fmt in {by_id[x["id"]].info["format"] for x in resolved if x["id"] in by_id}
                       for rd in readings.get(fmt, []) if rd[0] == spec["why_id"] and rd[3]), "")
        proposals.append(dict(
            why=spec["why"], what=whats.get(wp._what_of(whys, spec["why_id"])), spec=spec, text=sim["text"],
            conditions=[wp.describe(c) for c in spec["conditions"]],
            exceptions=[" and ".join(wp.describe(c) for c in e["conditions"]) for e in spec["exceptions"]],
            basis=p["basis"], reason=reason,
            resolves=len(resolved), resolved=[x for x in in_group if x in resolved],
            # covered by the rule's conditions although no example confirms their nature: to verify
            uncertain=[x["id"] for x in resolved if x["id"] in by_id and not by_id[x["id"]].label],
            open_in_group=[x for x in in_group if x not in resolved],
            outside_group=sum(1 for x in sim["rows"] if x["id"] not in group_ids and x["effect"] in ("new_why", "changed_why")),
            summary=sim["summary"], sources=_source_breakdown([by_id[x["id"]] for x in resolved if x["id"] in by_id])))
    proposals.sort(key=lambda p: -p["resolves"])

    # The formats of the group: the differences between descriptions and what the AI read in each.
    group_formats = Counter(mv.info["format"] for mv in group_mvs)
    fmt_rows = []
    for fmt, n in group_formats.most_common():
        sample = next(mv for mv in group_mvs if mv.info["format"] == fmt)
        read = readings.get(fmt)
        fmt_rows.append(dict(format=fmt, movements=n, example=sample.info["description"][:120],
                             reading=None if read is None else [dict(why=whys[w].name, conditions=[wp.describe(c) for c in cs], raw=cs,
                                                                     confidence=conf, reason=rs) for w, cs, conf, rs in read],
                             read=read is not None))

    excluded = []
    for mv in group_mvs:
        hit = covered.get(mv.id)
        if hit and len(hit) == 1:
            continue
        if hit:
            note = "CONFLICT"
        elif mv.protected:
            note = "PROTECTED"
        elif readings.get(mv.info["format"]) is None:
            note = "NOT_READ"
        elif not readings[mv.info["format"]]:
            note = "UNCLEAR"
        else:
            note = "NOT_SUPPORTED"
        excluded.append(dict(_row(mv), reason=note))

    if errors:
        limits.append(dict(kind="AI_PARTIAL", text=f"{len(errors)} AI batch(es) could not be read: retry the analysis.",
                           errors=errors[:3]))
    state = PROPOSAL if proposals else NO_RULE
    return dict(base, state=state, limits=limits, proposals=proposals, formats=fmt_rows, excluded=excluded,
                name_only=name_only, ai_calls=calls, examined=len(scope),
                applied=False, note="Nothing was saved, activated or applied.")
