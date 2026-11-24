"""What counts as a real job ad (16 November 2026).

A job is posted to Indeed through its public page, and the website's Careers
page reads the same published ad from careers.json, so one rule decides both:
a placeholder such as "Nessun annuncio" or a few words is not an ad. It cannot
be published, and anything already published that fails the rule is left out
(the feed sends no text, the job page shows none) instead of reaching the public.
The job ad box starts with the Role's default ad and falls back to it whenever it
is left empty or holds a placeholder, so a person can't publish junk by mistake.
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


def _standard_key(name):
    """The standard-ad key for a role or job name: exact first, then a close spelling, then a
    standard name contained in it ("Dishwasher Prep" -> Dishwasher, "Prep Cok" -> Prep Cook)."""
    import difflib
    from .role_descriptions import ROLE_DESCRIPTIONS
    from .routes import ROLE_CHOICES
    norm = lambda v: " ".join(re.sub(r"[^a-z ]", " ", (v or "").lower()).split())
    labels = {}
    for code, label in ROLE_CHOICES:
        if code in ROLE_DESCRIPTIONS:
            for variant in {label, code.replace("_", " ")} | set(label.split("/")):
                labels.setdefault(norm(variant), code)
    target = norm(name)
    if not target:
        return None
    if target in labels:
        return labels[target]
    close = difflib.get_close_matches(target, list(labels), n=1, cutoff=0.8)
    if close:
        return labels[close[0]]
    # A standard name at the start, followed only by words that don't make it another role
    # ("Dishwasher Prep", "Busser/Food runner"); never "Server Assistant" or "Pastry Chef".
    other_role = {"assistant", "manager", "lead", "leader", "head", "sous", "pastry", "supervisor", "chef", "captain"}
    words = target.split()
    for label in sorted(labels, key=len, reverse=True):
        n = len(label.split())
        if label and words[:n] == label.split() and not (set(words[n:]) & other_role):
            return labels[label]
    return None


def role_default(role_code, title=None):
    """The standard English ad for this Job: by its Role code, else by its title or its Role's name
    (Roles created in RF-One have generated codes, so the name is what identifies them)."""
    from .role_descriptions import ROLE_DESCRIPTIONS
    if role_code in ROLE_DESCRIPTIONS:
        return ROLE_DESCRIPTIONS[role_code]
    names = [title]
    try:
        from .routes import ROLE_LABEL
        names.append(ROLE_LABEL.get(role_code or "", ""))
    except Exception:
        pass
    for name in names:
        key = _standard_key(name)
        if key:
            return ROLE_DESCRIPTIONS[key]
    return ""


def or_default(text, role_code, title=None):
    """What goes in the job ad box on save: the text typed, or the standard ad when the box was
    left empty or holds a placeholder. So a Job never carries a placeholder as its ad."""
    return public(text) or role_default(role_code, title) or (text or "").strip()


def for_public(position):
    """The ad the website and Indeed show: the Job's published ad if real, else its standard ad."""
    return public(position.approved_job_ad_en) or role_default(position.role_code, getattr(position, "title", None))
