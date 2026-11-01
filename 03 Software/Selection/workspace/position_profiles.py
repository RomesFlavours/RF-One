"""Position Selection Profiles (SELECTION_POSITION_PROFILES_001).

One shared CV engine, different standards for every position. A profile says
what the CV screening looks for in ONE position: evidence dimensions and
their proposed weights, how prior work environments count, the stability
thresholds, the commute bands and what must be verified later.

Source: "RF-One Selection — AI CV Preselection Model: SERVER" v1.0 and
"... LINE COOK" v1.0, and "Position-Specific Standards" (31 October 2026).
Every weight and threshold here is a DRAFT setting from those documents,
proposed and not yet approved; the profile version is stored with every
screening result so a later change never rewrites history.

A position uses the profile of its `role_code`. Roles without a profile keep
the existing screening only.
"""

from __future__ import annotations

STATUS = "Proposed, not yet approved"

# Evidence level the AI assigns to each dimension. Unknown is NOT zero:
# a dimension the CV says nothing about is "not shown" (0 points) and is
# listed separately as missing information, never as a negative.
LEVELS = {
    0: "Not shown in the CV",
    1: "Weak or claimed only",
    2: "Some documented evidence",
    3: "Clear documented evidence",
    4: "Strong, repeated documented evidence",
}

# One-way drive from where the candidate lives to the restaurant.
# Rome's Flavours' experience: around 45 minutes often stops working after a few shifts.
COMMUTE_BANDS = (
    (20, "FAVORABLE", "Favorable (0–20 min)", 5),
    (30, "MANAGEABLE", "Generally manageable (21–30 min)", 0),
    (44, "CONFIRM", "Needs confirmation (31–44 min)", -5),
    (None, "CUTOFF", "45 min or more: business cut-off only once the drive is confirmed", -15),
)

# Typical one-way drive (minutes) from nearby towns to the restaurant, used before the AI's own estimate,
# which proved unreliable (Leesburg came back as 45 minutes). Approximate: to be confirmed by the restaurant.
DRIVE_MINUTES = {
    "mount dora": {
        "mount dora": 5, "eustis": 12, "tavares": 12, "sorrento": 12, "mount plymouth": 15, "zellwood": 15,
        "plymouth": 18, "astatula": 20, "umatilla": 22, "leesburg": 25, "apopka": 25, "paisley": 25,
        "howey-in-the-hills": 25, "altoona": 25, "fruitland park": 30, "lady lake": 32, "minneola": 35,
        "sanford": 35, "lake mary": 35, "longwood": 35, "ocoee": 35, "altamonte springs": 38, "maitland": 38,
        "the villages": 38, "clermont": 40, "groveland": 40, "winter garden": 40, "winter park": 40,
        "orlando": 45, "deland": 45, "deltona": 45, "kissimmee": 60, "ocala": 60,
    },
}

HOURS_BANDS = (
    (35, "Potential full-time fit (35–40 h)"),
    (25, "Substantial regular commitment (25–34 h)"),
    (16, "Part-time; match to the vacancy (16–24 h)"),
    (10, "May be supplementary; clarify (10–15 h)"),
    (0, "Very limited availability (under 10 h)"),
)

SERVER = {
    "code": "SERVER",
    "version": "SERVER v1.0",
    "title": "Server",
    "summary": ("Owns the guest's table experience from welcome to payment: personal hospitality, menu and wine "
                "guidance, thoughtful selling, several tables at once, coordination with kitchen and bar, and "
                "faithful use of Rome's Flavours' service standards."),
    "dimensions": [
        {"id": "table_service", "name": "Relevant table-service experience", "weight": 25,
         "look_for": "Full-service table ownership in comparable restaurants (see environment table)."},
        {"id": "stability", "name": "Employment stability", "weight": 25,
         "look_for": "Tenure per employer, repeated short stays, continuity in restaurant roles. Computed from the dates."},
        {"id": "guest_selling", "name": "Guest relationship and commercial service", "weight": 15,
         "look_for": "Menu and wine guidance, recommendations, appropriate upselling, sales results."},
        {"id": "trusted", "name": "Documented trusted responsibilities", "weight": 10,
         "look_for": "Opening/closing, cash-out, training others, shift coordination."},
        {"id": "learning", "name": "Documented learning and adaptation", "weight": 10,
         "look_for": "New systems, new service styles, training received, openings, cross-training."},
        {"id": "progression", "name": "Career progression", "weight": 5,
         "look_for": "Promotions to trainer, key holder or supervisor."},
        {"id": "versatility", "name": "Relevant FOH versatility", "weight": 5,
         "look_for": "Server, bartender, host, runner or FOH supervisor roles. Unrelated jobs do not count."},
        {"id": "recency", "name": "Recency of relevant work", "weight": 5,
         "look_for": "Relevant table service in the last 12–24 months."},
    ],
    "environments": [
        ("Italian full-service, upscale casual, fine dining", "Very high"),
        ("Steakhouse, wine-focused full-service, traditional full-service", "High"),
        ("Country club, hotel table service", "Variable: depends on actual duties"),
        ("Diner, breakfast chain", "Limited transferability: investigate"),
        ("Fast food, quick-service", "Low direct evidence of refined table service"),
        ("Retail, general customer service", "Partial transferable skills only"),
        ("Landscaping, warehouse, construction and other unrelated work", "No evidence of server competence"),
    ],
    "role_flags": [
        "Background predominantly in McDonald's, IHOP or similar operating models: provisional role-fit flag, "
        "not a ban; later substantial full-service experience counts.",
        "Mostly unrelated or fragmented work, with no table service.",
    ],
    "must_not_assume": "Retail or fast-food experience does not prove refined service. Years worked do not prove "
                       "adaptability, and long experience is never a negative.",
    "interview_focus": [
        "Desired and minimum weekly hours, and evening and weekend availability.",
        "Whether this would be the main job or a second job.",
        "An example of changing an established habit to meet a restaurant's standards.",
        "A guest asks for a wine to go with their dish: what do you say?",
    ],
}

LINE_COOK = {
    "code": "LINE_COOK",
    "version": "LINE COOK v1.0",
    "title": "Line Cook",
    "summary": ("Rome's Flavours serves traditional cuisine with established recipes. The Line Cook learns and "
                "reproduces them faithfully and consistently under pressure: ingredients, methods, portions, "
                "presentation, timing and food safety. Creativity or menu redesign is not an advantage for this role. "
                "Anthony is the guardian of the dish Legacy: recipe changes and new dishes go through him."),
    "dimensions": [
        {"id": "kitchen_stations", "name": "Relevant kitchen and station experience", "weight": 25,
         "look_for": "Line cooking in comparable scratch or full-service kitchens; stations actually worked."},
        {"id": "stability", "name": "Employment stability", "weight": 25,
         "look_for": "Tenure per employer, repeated short stays, continuity in kitchen roles. Computed from the dates."},
        {"id": "techniques", "name": "Cooking techniques and preparation", "weight": 15,
         "look_for": "Sauté, pasta, sauces, grill, prep, cooking from raw ingredients, where documented."},
        {"id": "ownership", "name": "Station ownership and responsibility", "weight": 10,
         "look_for": "Independent setup, service and breakdown, opening/closing, prep lists, inventory."},
        {"id": "recipe_standards", "name": "Recipe and standard execution", "weight": 10,
         "look_for": "Documented adherence to standardized recipes, portions, quality controls."},
        {"id": "food_safety", "name": "Food safety and sanitation", "weight": 5,
         "look_for": "Food handling, temperature controls, certifications where stated. Missing ServSafe is not a negative."},
        {"id": "versatility", "name": "Relevant BOH versatility", "weight": 5,
         "look_for": "Complementary kitchen stations actually worked, not unrelated occupations."},
        {"id": "recency", "name": "Recency and documented learning", "weight": 5,
         "look_for": "Recent line work, new stations or systems learned, cross-training."},
    ],
    "environments": [
        ("Traditional Italian full-service kitchen; scratch pasta and sauces", "Very high, subject to actual duties"),
        ("Full-service scratch kitchen with sauté/grill and coordinated ticket service", "High"),
        ("Upscale or fine-dining kitchen", "Potentially high: confirm willingness to execute fixed recipes"),
        ("Country club, hotel restaurant, high-volume full-service line", "Potentially high: inspect stations"),
        ("Casual chain with a real cook line", "Mixed: may show station, pace and sanitation"),
        ("Quick-service, fast food, diner", "Not a negative for BOH: pace, standardization and hygiene, "
         "but not proof of scratch cooking"),
        ("Prep-only, bakery-only or dishwashing-only", "Useful for those tasks; not enough alone for the line"),
        ("Landscaping, warehouse, construction and other unrelated work", "No evidence of line cook competence"),
    ],
    "station_levels": ["claimed", "assisted", "executed", "owned", "coordinated"],
    "role_flags": [
        "Mostly assembly-only work for a scratch-cooking vacancy.",
        "Stations listed only in a skills section: claimed, not demonstrated.",
        "Chef or management background: role-expectation alignment to clarify (will they cook the assigned line "
        "to established recipes?). Never inferred from age or years.",
    ],
    "must_not_assume": "A generic \"cook\" title does not prove every station. Menu creation is not a bonus for "
                       "changing Rome's Flavours' dishes. Long experience is never a negative.",
    "interview_focus": [
        "Desired and minimum weekly hours, and evening and weekend availability.",
        "Which stations they ran alone during a busy service.",
        "A recipe you think could be better: what do you do on the line, and who do you tell?",
        "How they keep portions and timing the same on every plate.",
    ],
}

PROFILES = {p["code"]: p for p in (SERVER, LINE_COOK)}


def for_role(role_code: str | None) -> dict | None:
    return PROFILES.get((role_code or "").upper())


def commute_band(minutes: int | None) -> tuple[str, str, int] | None:
    """(code, label, ranking points) for an estimated one-way drive, or None when unknown."""
    if minutes is None:
        return None
    for limit, code, label, points in COMMUTE_BANDS:
        if limit is None or minutes <= limit:
            return code, label, points
    return None


def known_drive(location: str | None, place: str | None) -> int | None:
    """Minutes from the restaurant's town table, or None when the location or the town is not listed."""
    if not isinstance(location, str) or not isinstance(place, str):
        return None
    table = next((t for key, t in DRIVE_MINUTES.items() if key in location.lower()), None)
    town = place.split(",")[0].strip().lower()
    return table.get(town) if table else None


def hours_band(hours: int | None) -> str | None:
    if hours is None:
        return None
    return next((label for floor, label in HOURS_BANDS if hours >= floor), None)
