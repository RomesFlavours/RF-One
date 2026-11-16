"""What counts as a real job ad (16 November 2026).

A job is posted to Indeed through its public page, and the website's Careers
page reads the same published ad from careers.json, so one rule decides both:
a placeholder such as "Nessun annuncio" or a few words is not an ad. It cannot
be published, and anything already published that fails the rule is left out
(the feed sends no text, the job page shows none) instead of reaching the public.
"""
import re

MIN_LENGTH = 80
PLACEHOLDERS = {"nessun annuncio", "nessun annuncio disponibile", "annuncio", "no ad", "no job ad", "job ad",
                "n/a", "na", "tbd", "todo", "to do", "da fare", "da completare", "placeholder", "test", "xxx"}


def problem(text):
    """Why this text can't be published as a job ad, or None if it can."""
    plain = " ".join((text or "").split())
    key = re.sub(r"[^\w\s/]", "", plain.lower()).strip()
    if not plain:
        return "Write the job ad first."
    if key in PLACEHOLDERS:
        return f"“{plain}” is a placeholder, not a job ad. Write the ad candidates will read on the website and on Indeed."
    if len(plain) < MIN_LENGTH:
        return f"The job ad is too short ({len(plain)} characters). Write at least {MIN_LENGTH} characters: what the job is and what the person does."
    return None


def public(text):
    """The published ad if it is a real one, else an empty string."""
    return (text or "").strip() if problem(text) is None else ""
