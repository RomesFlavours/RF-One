"""Generic Role Model (01 Domains/Cross Domain/Selection/
ResumeScreening/RoleModel.md). Selection Core defines only the shape; every
concrete role name/list is Industry Extension / Client / Role Configuration
content supplied by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TARGET = "TARGET"
EQUIVALENT = "EQUIVALENT"
PROPEDEUTIC = "PROPEDEUTIC"
ADJACENT = "ADJACENT"
OTHER = "OTHER"


@dataclass
class RoleConfiguration:
    """One role's Configuration (RoleModel.md, "Shape"). `transition_flags`
    names categories of prior role (e.g. "BOH") whose move into
    `target_role` should generate an investigative Flag, never automatic
    exclusion (ExperienceAndTrajectory.md, "Do not infer motive")."""

    target_role: str
    equivalent_roles: set[str] = field(default_factory=set)
    propedeutic_roles: set[str] = field(default_factory=set)
    adjacent_roles: set[str] = field(default_factory=set)
    transition_flags: set[str] = field(default_factory=set)


def classify_role(normalized_role: str | None, config: RoleConfiguration) -> str:
    """Classify one normalized role code against `config`. Never guesses —
    an unrecognized code is `OTHER`, not silently folded into the nearest
    category."""

    if not normalized_role:
        return OTHER
    if normalized_role == config.target_role:
        return TARGET
    if normalized_role in config.equivalent_roles:
        return EQUIVALENT
    if normalized_role in config.propedeutic_roles:
        return PROPEDEUTIC
    if normalized_role in config.adjacent_roles:
        return ADJACENT
    return OTHER
