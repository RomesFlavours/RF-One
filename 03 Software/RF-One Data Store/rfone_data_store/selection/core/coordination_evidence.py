"""Declared coordination responsibilities (SELECTION_COORDINATION_EVIDENCE_001).

Reads the duties written under each Work History record and keeps, as
evidence of what the candidate DECLARES, the sentences that describe a
responsibility exercised on OTHER people:

    COORDINATION  coordinating the team or the service
    ASSIGNMENT    assigning tasks, shifts or priorities
    TRAINING      training or onboarding colleagues or new hires
    SUPERVISION   supervising work, checking completion, giving feedback
    LIAISON       linking management and the team

A written duty is a declaration, not an independent verification and not a
measure of leadership quality. This module never changes a normalized
role, never counts months, never scores: each piece of evidence keeps its
original sentence and the experience it was written under. Generic
self-descriptions ("team player", "leadership skills") and supporting
someone else ("assisted the supervisor") are not evidence. Being trained
oneself is not training others. A sentence with no explicit reference to
other people (e.g. "managed reservations") is not evidence — the one
exception is delivering training, which by its nature has trainees; their
identity is then "not specified".

Selection Core knows no industry: the AREA (e.g. dining room / kitchen) is
supplied by the Industry Extension through `area_fn`. The people count is
taken only when the sentence states a number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .profile import WorkHistoryRecord

COORDINATION = "COORDINATION"
ASSIGNMENT = "ASSIGNMENT"
TRAINING = "TRAINING"
SUPERVISION = "SUPERVISION"
LIAISON = "LIAISON"

CATEGORY_LABELS = {
    COORDINATION: "Coordinating the team or the service",
    ASSIGNMENT: "Assigning tasks, shifts or priorities",
    TRAINING: "Training or onboarding colleagues",
    SUPERVISION: "Supervising work, checking completion, giving feedback",
    LIAISON: "Linking management and the team",
}

AREA_TO_CLARIFY = "TO_CLARIFY"

# Order matters only for the label of a sentence matching several patterns:
# the most specific responsibility wins (liaison, training, assignment,
# supervision, then plain coordination).
_VERBS: list[tuple[str, re.Pattern]] = [
    (TRAINING, re.compile(
        r"\b(train(?:ed|s|ing)?|onboard(?:ed|s|ing)?|mentor(?:ed|s|ing)?|coach(?:ed|es|ing)?|"
        r"taught|teach(?:es|ing)?|formavo|formato|affiancavo)\b", re.I)),
    (ASSIGNMENT, re.compile(
        r"\b(assign(?:ed|s|ing)?|schedul(?:ed|es|ing|e)|delegat(?:ed|es|ing|e)|allocat(?:ed|es|ing|e)|"
        r"prioriti[sz](?:ed|es|ing|e)|rota|roster(?:ed|s|ing)?|assegnavo|organizzavo i turni)\b", re.I)),
    (SUPERVISION, re.compile(
        r"\b(supervis(?:ed|es|ing|e)|oversaw|oversee(?:s|ing)?|monitor(?:ed|s|ing)?|"
        r"(?:gave|give|giving|provided|providing)\s+feedback|evaluat(?:ed|es|ing|e)|"
        r"ensur(?:ed|es|ing|e)|check(?:ed|s|ing)?|supervisionavo|controllavo)\b", re.I)),
    (COORDINATION, re.compile(
        r"\b(coordinat(?:ed|es|ing|e)|led|lead(?:s|ing)|manag(?:ed|es|ing|e)|direct(?:ed|s|ing)?|"
        r"ran\s+(?:a|the)\s+(?:team|shift|crew|floor|service)|coordinavo|gestivo|guidavo)\b", re.I)),
]
# Explicit other people. "Team" alone counts: it names a group of people.
_PEOPLE = re.compile(
    r"\b(team(?:s)?|staff|crew|colleagues?|co-?workers?|employees?|new\s+hires?|new\s+staff|trainees?|"
    r"members?|associates?|workers?|personnel|people|servers?|waiters?|waitress(?:es)?|hosts?|hostess(?:es)?|"
    r"runners?|bussers?|bartenders?|baristas?|cooks?|chefs?|dishwashers?|cashiers?|pickers?|drivers?|"
    r"juniors?|apprentices?|interns?|colleghi|personale|camerieri|cuochi|nuovi\s+assunti|squadra)\b", re.I)
_TRAINING_DELIVERED = re.compile(
    r"\b(deliver(?:ed|s|ing)?|conduct(?:ed|s|ing)?|provid(?:ed|es|ing|e)|ran|led|organi[sz](?:ed|es|ing|e))"
    r"\s+(?:\w+\s+){0,2}training\b", re.I)
_TRAINED_ONESELF = re.compile(
    r"\b(was|were|been|got|get)\s+trained\b|\btrained\s+(?:by|in|on)\b(?!.*\b(?:new|staff|team|colleagues?)\b)|"
    r"\b(received|completed|attended|undertook|passed)\s+(?:\w+\s+){0,2}training\b", re.I)
_LIAISON = re.compile(
    r"\b(liaison|point\s+of\s+contact|link|bridge|relay(?:ed|s|ing)?|communicat(?:ed|es|ing|e)|"
    r"report(?:ed|s|ing)?)\b.*\b(management|manager|managers|direzione|owner|owners)\b.*\b(team|staff|crew)\b|"
    r"\b(management|manager|managers|direzione)\b.*\b(team|staff|crew)\b.*\b(liaison|point\s+of\s+contact)\b",
    re.I)
# The candidate supported a superior: support, not the responsibility itself.
_SUPPORTING_SUPERIOR = re.compile(
    r"\b(assist(?:ed|s|ing)?|support(?:ed|s|ing)?|help(?:ed|s|ing)?|aid(?:ed|s|ing)?)\s+(?:\w+\s+){0,2}"
    r"(supervisors?|managers?|team\s+leaders?|head\s+\w+|chefs?|owners?)\b", re.I)
_NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
}
_PEOPLE_COUNT = re.compile(
    r"\b(\d{1,3}|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty)\b"
    r"(?:\+)?\s+(?:[a-z-]+\s+){0,2}?(?=" + _PEOPLE.pattern[2:-2] + r")", re.I)


@dataclass
class CoordinationEvidence:
    category: str
    sentence: str  # the original sentence, as written in the résumé
    experience_index: int  # position in the candidate's Work History
    experience_title: str | None
    experience_employer: str | None
    area: str  # supplied by the Industry Extension, or AREA_TO_CLARIFY
    people_count: int | None  # only when the sentence states it
    recipients_stated: bool  # False: the people involved are not specified
    attribution_to_verify: bool  # the experience's reading is uncertain (LOW)
    question: str

    @property
    def label(self) -> str:
        return CATEGORY_LABELS[self.category]


GENERAL_QUESTION = ("Have you had responsibility for coordinating or training other colleagues? "
                    "Describe a concrete example.")


def _sentences(text: str | None) -> list[str]:
    parts = re.split(r"\n+|(?<=[.;])\s+", text or "")
    return [p.strip(" -•*·\t") for p in parts if p and p.strip(" -•*·\t.;")]


def _people_count(sentence: str) -> int | None:
    match = _PEOPLE_COUNT.search(sentence)
    if not match:
        return None
    token = match.group(1).lower()
    return int(token) if token.isdigit() else _NUMBER_WORDS.get(token)


def classify_sentence(sentence: str) -> tuple[str, bool] | None:
    """(category, recipients_stated) when the sentence declares a
    responsibility on other people; None otherwise."""

    if _SUPPORTING_SUPERIOR.search(sentence):
        return None
    if _LIAISON.search(sentence):
        return LIAISON, True
    people = bool(_PEOPLE.search(sentence))
    for category, pattern in _VERBS:
        if not pattern.search(sentence):
            continue
        if category == TRAINING:
            if _TRAINED_ONESELF.search(sentence) and not people:
                continue
            if people:
                return TRAINING, True
            if _TRAINING_DELIVERED.search(sentence):
                return TRAINING, False
            continue
        if people:
            return category, True
    return None


def _question(evidence_sentence: str, title: str | None, employer: str | None) -> str:
    where = " ".join(filter(None, [f'as "{title}"' if title else None, f"at {employer}" if employer else None]))
    return (f'You wrote: "{evidence_sentence}"{(" (" + where + ")") if where else ""}. Who was involved and how '
            "many people, which decisions were yours to take, and what was the result?")


def detect_coordination_evidence(
    work_history: list[WorkHistoryRecord],
    *,
    area_fn: Callable[[str, WorkHistoryRecord], str | None] | None = None,
) -> list[CoordinationEvidence]:
    evidence: list[CoordinationEvidence] = []
    for index, record in enumerate(work_history):
        for text in (record.responsibilities, record.achievements):
            for sentence in _sentences(text):
                result = classify_sentence(sentence)
                if result is None:
                    continue
                category, recipients_stated = result
                uncertain = record.structure_confidence == "LOW"
                title = None if uncertain else record.original_job_title
                employer = None if uncertain else record.employer
                evidence.append(CoordinationEvidence(
                    category=category, sentence=sentence, experience_index=index,
                    experience_title=title, experience_employer=employer,
                    area=(area_fn(sentence, record) if area_fn else None) or AREA_TO_CLARIFY,
                    people_count=_people_count(sentence), recipients_stated=recipients_stated,
                    attribution_to_verify=uncertain, question=_question(sentence, title, employer),
                ))
    return evidence
