"""Evaluation rules of a Job (CV Selection SP) — the rules the analysis already applies, shown per Role.

No new rule is defined here: every entry names a check that `analysis` / `timeline` already perform, with its
real parameters read from the code. A Job may turn off the switchable ones; the Role standard (the profile in
`position_profiles` and the constants in `timeline`) is never changed.

Switching a rule off filters what the stored analysis shows and counts for that Job; the analysis itself is
kept whole, so changing rules never calls the AI again. Stability as a ranking dimension is a requirement
(switched on or off, weighted, in the requirement list), not one of these rules.
"""

from __future__ import annotations

from . import timeline


def catalogue(role_code: str) -> list[dict]:
    """Rules of this Role: id, name, what the code does (with its parameters), switchable or fixed."""
    rules = [
        {"id": "short_stays", "switchable": True, "name": "Short stays and job changes",
         "detail": f"Red flag computed from the verified CV dates: 2 or more consecutive jobs under "
                   f"{timeline.SHORT_MONTHS} months, or 5 or more jobs started in the last 36 months. "
                   f"{timeline.LONG_MONTHS}+ months at one relevant employer counts as positive evidence."},
        {"id": "gaps", "switchable": True, "name": "Employment gaps",
         "detail": f"A gap between two dated jobs is listed to verify when it is certainly at least "
                   f"{timeline.GAP_MONTHS} months. Never a negative judgement."},
        {"id": "cv_flags", "switchable": True, "name": "Red flags supported by the CV",
         "detail": "Risks for this Role that the CV shows, each kept only with an exact quote found in the CV."},
    ]
    if role_code == "SERVER":
        rules.insert(2, {"id": "environment", "switchable": True, "name": "Professional environments",
                         "detail": "Restaurant work only in diner, breakfast-chain or fast-food models raises a "
                                   "provisional role-fit flag (not a ban; later full-service experience counts)."})
    rules += [
        {"id": "durations", "switchable": False, "name": "Job durations",
         "detail": "Computed by code from dates found word for word in the CV, never written by the AI."},
        {"id": "claimed", "switchable": False, "name": "Declared and demonstrated competences",
         "detail": "A skill only listed (skills section or title) counts as claimed; demonstrated needs work "
                   "evidence quoted from the CV."},
        {"id": "absence", "switchable": False, "name": "Missing information",
         "detail": "Something the CV does not mention is never a red flag: it is listed under To verify."},
        {"id": "sensitive", "switchable": False, "name": "Excluded information",
         "detail": "Residence, commute, age and personal characteristics are never used."},
    ]
    return rules


def defaults(role_code: str) -> dict[str, bool]:
    return {r["id"]: True for r in catalogue(role_code) if r["switchable"]}


def effective(role_code: str, chosen: dict | None) -> dict[str, bool]:
    """The Job's choices over the Role defaults (a rule added to the Role later starts switched on)."""
    out = defaults(role_code)
    for key, value in (chosen or {}).items():
        if key in out:
            out[key] = bool(value)
    return out


_FLAG_SOURCE = {"cv_flags": "CV", "environment": "PROFILE", "short_stays": "DATES"}


def apply(analysis: dict | None, role_code: str, chosen: dict | None) -> dict | None:
    """A copy of the analysis showing only what this Job's rules keep. The stored analysis is not changed."""
    if not analysis:
        return analysis
    on = effective(role_code, chosen)
    off_sources = {source for rule, source in _FLAG_SOURCE.items() if not on.get(rule, True)}
    out = dict(analysis)
    out["flags"] = [f for f in analysis.get("flags") or [] if f.get("source") not in off_sources]
    if not on.get("gaps", True):
        out["gaps"] = []
        out["unknowns"] = [u for u in analysis.get("unknowns") or [] if not str(u).startswith("Gap of ")]
    if not on.get("short_stays", True) and isinstance(analysis.get("stability"), dict):
        out["stability"] = {**analysis["stability"], "flags": []}
    return out
