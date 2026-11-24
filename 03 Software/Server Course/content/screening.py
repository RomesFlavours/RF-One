"""CV screening for the Server role: Pino's six Primary Screening criteria
(copied from RF-One's primary_screening_criteria, restaurant 1, 29 Oct 2026)
and the red flags his Selection code already looks for. The AI proposes a
level for each criterion from the CV; the weighted total puts the CVs in
order; the selector checks the order and decides.
"""

CRITERIA = [
    {"id": "experience", "name": "Relevant experience", "coefficient": 2, "direction": 1,
     "description": "How much directly relevant restaurant service experience the CV shows.",
     "levels": {0: "No relevant restaurant experience found.", 1: "Brief or tangential relevant experience.",
                2: "Some directly relevant experience.", 3: "Solid, multi-role relevant experience.",
                4: "Extensive, clearly strong relevant experience."}},
    {"id": "recency", "name": "Experience recency", "coefficient": 1.5, "direction": 1,
     "description": "How recently the candidate held relevant restaurant experience.",
     "levels": {0: "No relevant recent experience.", 1: "Limited: relevant experience is old.",
                2: "Moderate: some relevant experience within the last couple of years.",
                3: "Recent: relevant experience within the last year.",
                4: "Very recent: current or just-ended relevant role."}},
    {"id": "availability", "name": "Availability problems", "coefficient": 3, "direction": -1, "hard_stop": 4,
     "description": "How incompatible the stated availability is with the role (evenings, weekends). 0 if not stated.",
     "levels": {0: "Fully compatible, or not stated.", 1: "Minor gaps, easily worked around.",
                2: "Some real limitations on availability.", 3: "Significant, hard-to-accommodate limitations.",
                4: "Availability is fundamentally incompatible with the role's schedule."}},
    {"id": "repeat", "name": "Repeated application", "coefficient": 1, "direction": 1,
     "description": "Whether a repeat applicant shows progress since a prior application. 0 for a first application.",
     "levels": {0: "First-time applicant, or not known.", 1: "Repeat applicant, no notable change.",
                2: "Repeat applicant with a minor positive change.", 3: "Repeat applicant with a clear positive change.",
                4: "Repeat applicant with strong, directly relevant progression."}},
    {"id": "stability", "name": "Job stability problems", "coefficient": 1.5, "direction": -1,
     "description": "How much of a concern short jobs and frequent changes are.",
     "levels": {0: "Stable employment record.", 1: "One shorter-than-typical role.", 2: "A couple of shorter roles.",
                3: "A clear pattern of short tenures.", 4: "A strong, repeated pattern of very short tenures."}},
    {"id": "motivation", "name": "Motivation signals", "coefficient": 1, "direction": 1,
     "description": "Strength of any explicit motivation or interest in this job (cover letter, summary).",
     "levels": {0: "No motivation signal found.", 1: "Weak or generic signal.", 2: "Some genuine signal.",
                3: "Clear, specific signal.", 4: "Strong, specific, well-supported signal."}},
]

# From Pino's Selection flags (short tenure, gaps, overlaps, role transitions,
# title inconsistency, missing information), plus recency for a server.
RED_FLAGS = (
    "three or more short jobs in a row (under about 6 months each); gaps between jobs; dates that overlap or don't add up; "
    "a job title that doesn't match the duties described; a move from kitchen or other work to the floor with no floor "
    "experience; missing dates or employers; no restaurant work in the last two years; availability that doesn't fit "
    "evenings and weekends"
)


def total(levels: dict) -> float:
    return sum(c["coefficient"] * c["direction"] * int(levels.get(c["id"], 0)) for c in CRITERIA)


def hard_stop(levels: dict) -> bool:
    return any("hard_stop" in c and int(levels.get(c["id"], 0)) >= c["hard_stop"] for c in CRITERIA)


def chance(levels: dict) -> str:
    if hard_stop(levels):
        return "Check availability"
    t = total(levels)
    return "Higher chance" if t >= 10 else "Medium chance" if t >= 5 else "Lower chance"
