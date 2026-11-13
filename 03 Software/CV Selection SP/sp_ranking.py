"""Preselection ranking (CV Selection SP).

A motivated preselection priority, not a validated prediction: no number is
shown as a probability of success, and nobody is excluded.

Order, from first to last:
1. the manager's manual order, when set;
2. the group, from the APPROVED must-have requirements (Pino's transparent
   rule, `engine.propose_group`, extended with "concerns documented"):
   A  every must-have shown in the CV
   B  must-haves partly shown or to verify, none missing
   C  a must-have not documented in the CV (missing information, to verify)
   D  a must-have with documented evidence against it (dates or a CV quote)
   Missing information (C) is placed before documented concerns (D): it is
   something to verify, not a negative judgement;
3. within a group, documented evidence weighted by the approved weights
   (Shelbi's dimensions), as a share of what the CV can show: requirements
   that cannot be judged from a CV, or a stability with no usable dates,
   are left out instead of counting as zero.
The internal evidence share orders candidates; the page shows the reasons,
the levels and the quotes, not the number.
"""

from __future__ import annotations

import sp_profiles as spp

SHOWN, PARTIAL, CLAIMED, MISSING, NOT_ASSESSABLE, AGAINST = (
    "SHOWN", "PARTIAL", "CLAIMED", "MISSING", "NOT_ASSESSABLE", "AGAINST")
STATUS_LABELS = {
    SHOWN: "Shown in the CV", PARTIAL: "Partly shown", CLAIMED: "Claimed only (skills list or title)",
    MISSING: "Not documented (missing information, not proof of absence)",
    NOT_ASSESSABLE: "Cannot be judged from a CV: verify at interview", AGAINST: "Evidence against",
}
GROUPS = {
    "A": "Strong evidence: contact first",
    "B": "Promising: verify a few points",
    "C": "Key evidence missing: verify before deciding",
    "D": "Documented concerns on a must-have",
}


def status_of(result: dict) -> str:
    level = result.get("level")
    if not result.get("assessable", True) or level is None:
        return NOT_ASSESSABLE
    if result.get("computed") and level <= 1:
        return AGAINST                                  # stability: short-job pattern computed from the dates
    if result.get("against") and level <= 1:
        return AGAINST
    return SHOWN if level >= 3 else PARTIAL if level == 2 else CLAIMED if level == 1 else MISSING


def assess(analysis: dict, requirements: list[dict]) -> dict:
    """Group, internal evidence share and the per-requirement statuses of one analyzed candidate."""
    items, got, possible = [], 0.0, 0.0
    for req in requirements:
        res = analysis["requirements"].get(req["id"], {"level": 0, "quotes": [], "assessable": True})
        status = status_of(res)
        items.append({**req, **res, "status": status, "status_label": STATUS_LABELS[status]})
        if status != NOT_ASSESSABLE and req["weight"]:
            possible += req["weight"]
            got += req["weight"] * (res["level"] or 0) / 4
    must = [i for i in items if i["criticality"] == spp.MUST_HAVE]
    against = [i for i in must if i["status"] == AGAINST]
    missing = [i for i in must if i["status"] in (MISSING, CLAIMED)]
    unclear = [i for i in must if i["status"] in (PARTIAL, NOT_ASSESSABLE)]
    if against:
        group, why = "D", "Evidence against: " + "; ".join(i["name"] for i in against)
    elif missing:
        group, why = "C", "Not documented in the CV: " + "; ".join(i["name"] for i in missing)
    elif unclear:
        group, why = "B", "Partly shown or to verify: " + "; ".join(i["name"] for i in unclear)
    else:
        group, why = "A", "Every must-have is shown in the CV: " + "; ".join(i["name"] for i in must)
    return {"group": group, "group_label": GROUPS[group], "group_reason": why, "items": items,
            "evidence_share": round(got / possible, 4) if possible else 0.0}


def _proposed_key(c: dict):
    a = c["assessment"]
    return (a["group"], -a["evidence_share"], c["uploaded_at"])


def rank(candidates: list[dict], requirements: list[dict], manual_order: list[str] | None) -> list[dict]:
    """candidates: analyzed ones ({"id", "analysis", "uploaded_at", ...}). Returns them ordered, each with
    "assessment", "rank", "proposed_rank", "rank_moved" and "why_ahead"."""
    for c in candidates:
        c["assessment"] = assess(c["analysis"], requirements)
    proposed = sorted(candidates, key=_proposed_key)
    for i, c in enumerate(proposed, 1):
        c["proposed_rank"] = i
    ordered = proposed
    if manual_order:
        pos = {cid: i for i, cid in enumerate(manual_order)}
        ordered = sorted(proposed, key=lambda c: (pos.get(c["id"], len(pos) + c["proposed_rank"]),))
    for i, c in enumerate(ordered, 1):
        c["rank"], c["rank_moved"] = i, c["proposed_rank"] != i
    for c, nxt in zip(ordered, ordered[1:] + [None]):
        c["why_ahead"] = why_ahead(c, nxt) if nxt else None
    return ordered


def _name(c: dict) -> str:
    return c["analysis"].get("full_name") or c["filename"]


def why_ahead(c: dict, nxt: dict) -> str:
    if c.get("rank_moved") or nxt.get("rank_moved"):
        if c["proposed_rank"] > nxt["proposed_rank"]:
            return f"Placed before {_name(nxt)} by the manager."
    a, b = c["assessment"], nxt["assessment"]
    if a["group"] != b["group"]:
        return f"Ahead of {_name(nxt)}: group {a['group']} ({a['group_label'].split(':')[0]}) vs {b['group']} — {b['group_reason']}."
    diffs = []
    lb = {i["id"]: i for i in b["items"]}
    for item in a["items"]:
        other = lb.get(item["id"])
        if not other or item["status"] == NOT_ASSESSABLE or other["status"] == NOT_ASSESSABLE:
            continue
        delta = ((item["level"] or 0) - (other["level"] or 0)) * item["weight"]
        if delta > 0:
            diffs.append((delta, f"{item['name']} ({spp_level(item['level'])} vs {spp_level(other['level'])})"))
    diffs.sort(reverse=True)
    if diffs:
        return f"Ahead of {_name(nxt)}, same group: stronger documented evidence on " + "; ".join(d for _, d in diffs[:2]) + "."
    return f"Same documented evidence as {_name(nxt)}: kept in upload order."


def spp_level(level) -> str:
    return {None: "unknown", 0: "not documented", 1: "claimed", 2: "some", 3: "clear", 4: "strong"}.get(level, str(level))


def summary(c: dict) -> str:
    """One-line motivation for the candidate's place."""
    a, an = c["assessment"], c["analysis"]
    shown = [i["name"] for i in a["items"] if i["status"] == SHOWN and i["criticality"] != spp.MUST_HAVE][:2]
    text = a["group_reason"] + "."
    if shown:
        text += " Also shown: " + "; ".join(shown) + "."
    if an["flags"]:
        text += f" {len(an['flags'])} flag(s) to discuss."
    return text
