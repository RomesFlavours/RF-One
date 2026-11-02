"""Position profiles as approved requirements (CV Selection SP).

Shelbi's Position Selection Profiles (`Selection/workspace/position_profiles.py`,
reused unchanged) supply the professional standard of each role. Here each
profile dimension becomes one Pino-style requirement with a criticality and
a weight, so one list serves both purposes: the manager reviews and approves
it, the analysis evaluates against it, the ranking weighs it. Nothing is
duplicated: the dimension text, weights and role knowledge stay in Shelbi's
file, and the approved snapshot stored with every position records exactly
what was used.
"""

from __future__ import annotations

from .. import position_profiles as pp

MUST_HAVE, PREFERRED, OPTIONAL = "MUST_HAVE", "PREFERRED", "OPTIONAL"
CRITICALITY_LABELS = {MUST_HAVE: "Must-have", PREFERRED: "Preferred", OPTIONAL: "Optional"}

# Computed in code from the verified dates, never scored by the AI.
COMPUTED = {"stability"}

ROLES = {code: profile["title"] for code, profile in pp.PROFILES.items()}


def profile_for(role_code: str) -> dict:
    return pp.PROFILES[role_code]


def default_requirements(role_code: str) -> list[dict]:
    """The profile's dimensions as a draft requirement list (weight >= 25 must-have, 10-15 preferred, else optional).
    A computed requirement (stability) starts Preferred whatever its weight: short or broken job histories also
    come from studies, caring for someone, health or pregnancy, so the dates alone must not decide a group; the
    manager can still make it a Must-have, and the interview asks about it."""
    out = []
    for d in profile_for(role_code)["dimensions"]:
        crit = MUST_HAVE if d["weight"] >= 25 else PREFERRED if d["weight"] >= 10 else OPTIONAL
        if d["id"] in COMPUTED and crit == MUST_HAVE:
            crit = PREFERRED
        out.append({"id": d["id"], "name": d["name"], "look_for": d["look_for"], "weight": d["weight"],
                    "criticality": crit, "computed": d["id"] in COMPUTED,
                    "source": profile_for(role_code)["version"]})
    return out


def custom_requirement(index: int, name: str, look_for: str, criticality: str, weight: int) -> dict:
    return {"id": f"custom{index}", "name": name.strip(), "look_for": look_for.strip(), "weight": max(0, weight),
            "criticality": criticality if criticality in CRITICALITY_LABELS else PREFERRED, "computed": False,
            "source": "Added by the manager"}
