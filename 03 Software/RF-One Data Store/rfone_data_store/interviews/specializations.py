"""Domains supply direction; the session engine owns conversation continuity."""

KNOW_HOW = {
    "code": "KNOW_HOW",
    "direction": (
        "Acquire reusable knowledge for the administrator's stated purpose. "
        "Explore concrete experiences, including successes and mistakes, context, "
        "observed cues, decisions, alternatives, outcomes and limits of applicability. "
        "Ask neutral questions and distinguish testimony, evidence and your inferences. "
        "Do not assess the person's worth or silently publish any knowledge."
    ),
}


def get_specialization(code):
    if code != KNOW_HOW["code"]:
        raise ValueError("Specialization unavailable.")
    return dict(KNOW_HOW)
