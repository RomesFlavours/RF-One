"""Restaurant Industry Extension (01 Domains/Business Domain/Restaurant/Selection/README.md).

Adds Restaurant-specific interpretation on top of Selection Core: a
normalized role catalog, title normalization, seniority ranking (for
trajectory detection only), role-category classification (for the
BOH/MANAGEMENT/NON_HOSPITALITY transition Flags), and the first real
`RoleConfiguration` — Rome's Flavours' Server role. Nothing here is known to
`..core`.

Task 2B additions (role/title normalization for `selection/normalization.py`):
`ROLE_FAMILY`/`role_family()`, `DISPLAY_NAME`/`display_name_for()`,
`split_multi_role_title()`, `seniority_level_from_title()`. These are a
separate axis from `SENIORITY_RANK`/`seniority_rank()` below — that dict is
an internal ranking used ONLY for trajectory-direction detection (its own
docstring: "never a compensation scale, never shown to the evaluator as a
'level'"); `seniority_level_from_title()` is the opposite — a human-facing
label, but ONLY ever derived from explicit title wording, never from tenure
or from that internal rank.
"""

from __future__ import annotations

import re

from ..core.role_model import RoleConfiguration

FOH_ROLES = {
    "SERVER", "BARTENDER", "HOST", "BUSSER", "FOOD_RUNNER", "FOH_SUPERVISOR", "FOH_MANAGER",
}
BOH_ROLES = {
    "PREP_COOK", "LINE_COOK", "PIZZA_COOK", "DISHWASHER", "SOUS_CHEF", "CHEF", "BOH_MANAGER",
}
# GENERAL_MANAGER/ASSISTANT_GENERAL_MANAGER/MANAGER are deliberately kept out
# of FOH_ROLES/BOH_ROLES — management is a distinct axis from front/back of
# house (role_category() below still reports them as "MANAGEMENT").
OTHER_ROLES = {"GENERAL_MANAGER", "ASSISTANT_GENERAL_MANAGER", "MANAGER"}

# Server-equivalent title codes (RoleModel.md's own worked example: "Waiter"/
# "Waitress" for "Server" — different title, same substance). Not part of the
# task §11 FOH/BOH/OTHER catalog list itself (that list reports at the
# coarser "SERVER" level); kept as distinct normalized codes ONLY so
# RoleConfiguration's TARGET vs. EQUIVALENT classification (RoleModel.md) is
# meaningfully exercised, per the Server Role Configuration below. Treated as
# full FOH/Server-equivalent for every other classification in this module.
SERVER_EQUIVALENT_ROLES = {"WAITER", "WAITRESS", "DINING_SERVER"}

ALL_CATALOG_ROLES = FOH_ROLES | BOH_ROLES | OTHER_ROLES | SERVER_EQUIVALENT_ROLES

# Ordered (most specific keyword first) so e.g. "sous chef" matches before
# the more general "chef" — used by normalize_title() below.
_TITLE_KEYWORDS: list[tuple[str, str]] = [
    ("sous chef", "SOUS_CHEF"),
    ("executive chef", "CHEF"),
    ("head chef", "CHEF"),
    ("chef", "CHEF"),
    ("pizza cook", "PIZZA_COOK"),
    ("pizza maker", "PIZZA_COOK"),
    ("prep cook", "PREP_COOK"),
    ("line cook", "LINE_COOK"),
    ("cook", "LINE_COOK"),
    ("dishwasher", "DISHWASHER"),
    ("kitchen manager", "BOH_MANAGER"),
    ("boh manager", "BOH_MANAGER"),
    # Must precede "general manager"/"restaurant manager" below — each
    # contains that shorter phrase as a substring, so the more specific match
    # has to be checked first (Task 2B: AGM must not collapse into GM).
    ("assistant general manager", "ASSISTANT_GENERAL_MANAGER"),
    ("assistant restaurant manager", "ASSISTANT_GENERAL_MANAGER"),
    ("assistant manager", "ASSISTANT_GENERAL_MANAGER"),
    ("general manager", "GENERAL_MANAGER"),
    ("restaurant manager", "GENERAL_MANAGER"),
    ("foh manager", "FOH_MANAGER"),
    ("front of house manager", "FOH_MANAGER"),
    ("floor supervisor", "FOH_SUPERVISOR"),
    ("shift supervisor", "FOH_SUPERVISOR"),
    ("supervisor", "FOH_SUPERVISOR"),
    ("bartender", "BARTENDER"),
    ("mixologist", "BARTENDER"),
    ("host", "HOST"),
    ("hostess", "HOST"),
    ("busser", "BUSSER"),
    ("bus person", "BUSSER"),
    ("food runner", "FOOD_RUNNER"),
    ("runner", "FOOD_RUNNER"),
    ("dining server", "DINING_SERVER"),
    ("waiter", "WAITER"),
    ("waitress", "WAITRESS"),
    ("server", "SERVER"),
    # Generic fallback — checked last, so it only ever catches a bare
    # "Manager" that none of the more specific management phrases above
    # matched (task's own "Manager / Bartender" multi-role example: "Manager"
    # alone is genuinely ambiguous, but still real evidence worth keeping
    # rather than discarding as unrecognized).
    ("manager", "MANAGER"),
]

# Short acronyms need word-boundary matching, not substring — a plain
# `"gm" in lowered` would false-positive inside unrelated words. Checked
# before the phrase-keyword loop; AGM must precede GM for the same
# most-specific-first reason as in `_TITLE_KEYWORDS`.
_ACRONYM_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bagm\b", re.IGNORECASE), "ASSISTANT_GENERAL_MANAGER"),
    (re.compile(r"\bgm\b", re.IGNORECASE), "GENERAL_MANAGER"),
]


def normalize_title(original_job_title: str | None) -> str | None:
    """Maps a free-text job title to a catalog code by transparent keyword
    matching. Returns None when nothing clearly matches — never guessed."""

    if not original_job_title:
        return None
    lowered = original_job_title.lower()
    for pattern, code in _ACRONYM_PATTERNS:
        if pattern.search(lowered):
            return code
    for keyword, code in _TITLE_KEYWORDS:
        if keyword in lowered:
            return code
    return None


# Seniority, for trajectory detection only (01 Domains/Business Domain/Restaurant/Selection/
# README.md, "Seniority, for trajectory detection") — never a compensation
# scale, never shown to the evaluator as a "level."
SENIORITY_RANK: dict[str, int] = {
    "DISHWASHER": 1, "BUSSER": 1, "HOST": 1, "PREP_COOK": 1,
    "FOOD_RUNNER": 2, "SERVER": 2, "WAITER": 2, "WAITRESS": 2, "DINING_SERVER": 2,
    "BARTENDER": 2, "LINE_COOK": 2, "PIZZA_COOK": 2,
    "SOUS_CHEF": 3, "FOH_SUPERVISOR": 3,
    "CHEF": 4, "FOH_MANAGER": 4, "BOH_MANAGER": 4, "ASSISTANT_GENERAL_MANAGER": 4, "MANAGER": 4,
    "GENERAL_MANAGER": 5,
}


def seniority_rank(normalized_role: str | None) -> int | None:
    if not normalized_role:
        return None
    return SENIORITY_RANK.get(normalized_role)


# Role classification for Indicators (README.md, "Role classification for
# Indicators").
CUSTOMER_FACING_ROLES = FOH_ROLES | SERVER_EQUIVALENT_ROLES
COMMERCIAL_ROLES = {"SERVER", "WAITER", "WAITRESS", "DINING_SERVER", "BARTENDER"}
SUPERVISORY_ROLES = {
    "FOH_SUPERVISOR", "FOH_MANAGER", "SOUS_CHEF", "CHEF", "BOH_MANAGER",
    "GENERAL_MANAGER", "ASSISTANT_GENERAL_MANAGER", "MANAGER",
}
INDUSTRY_ROLES = ALL_CATALOG_ROLES

# Category classification for the BOH/MANAGEMENT transition Flags (README.md,
# "Rome's Flavours Server Role Configuration"). A role not covered here (and
# with no normalized_role at all) is left for Core's own NON_HOSPITALITY
# fallback — this dict never claims to cover roles outside this catalog.
_MANAGEMENT_ROLES = {"GENERAL_MANAGER", "FOH_MANAGER", "BOH_MANAGER", "ASSISTANT_GENERAL_MANAGER", "MANAGER"}


def role_category(normalized_role: str | None) -> str | None:
    if not normalized_role:
        return None
    if normalized_role in _MANAGEMENT_ROLES:
        return "MANAGEMENT"
    if normalized_role in BOH_ROLES:
        return "BOH"
    if normalized_role in FOH_ROLES or normalized_role in SERVER_EQUIVALENT_ROLES:
        return "FOH"
    return None


def transition_detail_type(category: str) -> str:
    """BOH -> SERVER gets the more specific Flag type FlagsAndIndicators.md
    names (`BOH_TO_FOH`); other investigated transitions use the generic
    Core `ROLE_TRANSITION` type."""
    if category == "BOH":
        return "BOH_TO_FOH"
    return "ROLE_TRANSITION"


ROME_FLAVOURS_SERVER_ROLE_CONFIG = RoleConfiguration(
    target_role="SERVER",
    equivalent_roles={"WAITER", "WAITRESS", "DINING_SERVER"},
    propedeutic_roles={"BARTENDER", "FOOD_RUNNER", "BUSSER", "HOST"},
    adjacent_roles={"RETAIL_SALES", "HOTEL_GUEST_SERVICE", "CUSTOMER_SERVICE"},
    transition_flags={"BOH", "MANAGEMENT", "NON_HOSPITALITY"},
)

# Registry, keyed by target role code — the smallest coherent "Role
# Configuration lookup" the MVP needs (01 Domains/Cross Domain/Personnel Management/
# Selection/ResumeScreening/README.md, "Domain architecture", layer D).
ROLE_CONFIGURATIONS: dict[str, RoleConfiguration] = {
    "SERVER": ROME_FLAVOURS_SERVER_ROLE_CONFIG,
}


# ---------------------------------------------------------------------------
# Task 2B — role families, display names, multi-role titles, seniority
# ---------------------------------------------------------------------------

# Practical hospitality role families (task's own minimum list). A catalog
# code missing here falls back to "Other / Unknown" in role_family() below —
# defensive only; every code in ALL_CATALOG_ROLES is listed explicitly.
ROLE_FAMILY: dict[str, str] = {
    "SERVER": "FOH Service", "WAITER": "FOH Service", "WAITRESS": "FOH Service", "DINING_SERVER": "FOH Service",
    "BARTENDER": "Bar",
    "HOST": "Host / Guest Reception",
    "BUSSER": "Support / Busser / Runner", "FOOD_RUNNER": "Support / Busser / Runner",
    "PREP_COOK": "Kitchen / BOH", "LINE_COOK": "Kitchen / BOH", "PIZZA_COOK": "Kitchen / BOH",
    "DISHWASHER": "Kitchen / BOH",
    "SOUS_CHEF": "Culinary Leadership", "CHEF": "Culinary Leadership",
    "FOH_SUPERVISOR": "Restaurant Management", "FOH_MANAGER": "Restaurant Management",
    "BOH_MANAGER": "Restaurant Management", "ASSISTANT_GENERAL_MANAGER": "Restaurant Management",
    "MANAGER": "Restaurant Management",
    "GENERAL_MANAGER": "Operations / General Management",
}


def role_family(normalized_role: str | None) -> str | None:
    """None when there is no normalized role at all (nothing to classify);
    "Other / Unknown" only for the defensive case of a catalog code this
    table has not been kept in sync with — never guessed from free text."""

    if not normalized_role:
        return None
    return ROLE_FAMILY.get(normalized_role, "Other / Unknown")


# Human-readable canonical display name per catalog code (task's
# `normalized_title`). WAITER/WAITRESS/DINING_SERVER collapse to "Server" for
# display — RoleModel.md's own note: those codes exist only to exercise
# TARGET/EQUIVALENT classification, and are "full FOH/Server-equivalent for
# every other classification" (role_model.py's docstring already says this).
DISPLAY_NAME: dict[str, str] = {
    "SERVER": "Server", "WAITER": "Server", "WAITRESS": "Server", "DINING_SERVER": "Server",
    "BARTENDER": "Bartender",
    "HOST": "Host",
    "BUSSER": "Busser",
    "FOOD_RUNNER": "Food Runner",
    "PREP_COOK": "Prep Cook",
    "LINE_COOK": "Line Cook",
    "PIZZA_COOK": "Pizza Cook",
    "DISHWASHER": "Dishwasher",
    "SOUS_CHEF": "Sous Chef",
    "CHEF": "Chef",
    "FOH_SUPERVISOR": "Shift Supervisor",
    "FOH_MANAGER": "Front of House Manager",
    "BOH_MANAGER": "Kitchen Manager",
    "ASSISTANT_GENERAL_MANAGER": "Assistant General Manager",
    "MANAGER": "Manager",
    "GENERAL_MANAGER": "General Manager",
}


def display_name_for(normalized_role: str | None, original_job_title: str | None = None) -> str | None:
    """`DISPLAY_NAME` lookup, with one conservative refinement: CHEF keeps
    "Executive Chef"/"Head Chef" instead of collapsing to the generic "Chef"
    when the original title said so — task §"COMMON HOSPITALITY ROLE
    NORMALIZATION": "without collapsing meaningful distinctions
    unnecessarily." The underlying catalog code stays CHEF either way
    (classification/RoleModel behavior is unchanged); only the human-facing
    label gets more specific."""

    if not normalized_role:
        return None
    if normalized_role == "CHEF" and original_job_title:
        lowered = original_job_title.lower()
        if "executive chef" in lowered:
            return "Executive Chef"
        if "head chef" in lowered:
            return "Head Chef"
    return DISPLAY_NAME.get(normalized_role, normalized_role.replace("_", " ").title())


# Separators a hospitality résumé commonly uses for a genuinely combined
# title ("Server/Bartender", "Host & Server", "Cook / Dishwasher"). Kept
# deliberately small (task §"Do NOT create a giant universal occupation
# ontology" applies just as much here) — a title with none of these stays a
# single segment, which is exactly the previous (Task 2A) single-title
# behavior.
_MULTI_ROLE_SEPARATOR_RE = re.compile(r"\s*(?:/|&|\+|,|\band\b)\s*", re.IGNORECASE)


def split_multi_role_title(original_job_title: str | None) -> list[str]:
    """Splits a title into candidate role segments. Returns `[title]`
    unchanged (never `[]`) when no separator is found, so a caller can
    always iterate the result the same way regardless of whether the title
    was single- or multi-role."""

    if not original_job_title or not original_job_title.strip():
        return []
    parts = [p.strip() for p in _MULTI_ROLE_SEPARATOR_RE.split(original_job_title) if p.strip()]
    return parts or [original_job_title.strip()]


# Seniority evidenced by the TITLE TEXT ITSELF only — never inferred from
# tenure/years worked (task §"SENIORITY": "Do NOT infer seniority merely from
# years worked"). Checked in this order so a more specific phrase always wins
# over a more generic one it contains (e.g. "Assistant General Manager"
# before the bare "manager" pattern); the AGM pattern also matches the bare
# "AGM" acronym. "Executive"/"Director" deliberately excludes "Executive
# Chef" — that is a Culinary Leadership title (see `display_name_for`), not
# a generic seniority rung.
_SENIORITY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bassistant\s+general\s+manager\b|\bagm\b", re.IGNORECASE), "Assistant Manager"),
    (re.compile(r"\bassistant\s+manager\b", re.IGNORECASE), "Assistant Manager"),
    (re.compile(r"\bgeneral\s+manager\b|\bgm\b", re.IGNORECASE), "General Manager"),
    (re.compile(r"\bdirector\b|\bexecutive\b(?!\s+chef)", re.IGNORECASE), "Director / Executive"),
    (re.compile(r"\bsupervisor\b", re.IGNORECASE), "Supervisor"),
    (re.compile(r"\blead\b|\bhead\s+(server|bartender|host)\b", re.IGNORECASE), "Lead"),
    (re.compile(r"\btrainee\b|\bapprentice\b", re.IGNORECASE), "Trainee"),
    (re.compile(r"\bjunior\b|\bjr\.?\b", re.IGNORECASE), "Junior"),
    (re.compile(r"\bmanager\b", re.IGNORECASE), "Manager"),
]


def seniority_level_from_title(original_job_title: str | None) -> str | None:
    """None whenever the title carries no explicit seniority wording — never
    fabricated, and never derived from anything but this one string."""

    if not original_job_title:
        return None
    for pattern, level in _SENIORITY_PATTERNS:
        if pattern.search(original_job_title):
            return level
    return None
