#!/usr/bin/env python
"""Explicit, operator-invoked import of the 51 new Training menu pills
(dish guide extension from 3 to 54 dishes total — "RF-ONE: importare le
51 nuove pillole" task).

Reads `RF-One-51-Pillole-Quiz.json` (bundled next to this script — an
editorial content package, never served publicly: no route in this
application exposes arbitrary filenames from this directory, only the
explicitly named `RF-One-Training.html`) and creates the corresponding
`TrainingPill`/`TrainingQuestion` rows, using each pill's stable `id` as
`TrainingPill.slug` and each question's `(kind, position)` as its natural
key — exactly the same natural-key convention `service.ensure_pills_
seeded()` already uses for the original 3 pills.

Idempotent and atomic:
  - A pill/question already present with content matching the package is
    silently skipped (safe to re-run, e.g. once per release).
  - A pill/question already present with DIFFERENT content is a conflict:
    the entire run aborts with nothing written (no partial import) and the
    conflict is reported — never a silent overwrite.
  - The three existing pills (`caprese`, `carbonara`, `shrimp-pistachio`)
    are never touched; if the package ever named one of them, that alone
    is treated as a conflict and aborts the run.

Never imported/run automatically — not at app import, not at Gunicorn
worker boot, not on a GET request. An explicit, separate step from
`initialize_training.py` (which only seeds the original 3 pills) and from
Alembic migrations.

Usage:
    python import_menu_pills.py [--source PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from db import SessionFactory  # noqa: E402  (local import — see db.py's sys.path setup)
from rfone_data_store import models as m  # noqa: E402

DEFAULT_SOURCE = Path(__file__).resolve().parent / "RF-One-51-Pillole-Quiz.json"

PRESERVE_IDS = {"caprese", "carbonara", "shrimp-pistachio"}

# JSON question-family name -> existing TrainingQuestion.kind vocabulary.
KIND_MAP = {"practice": "self_check", "final": "final_quiz", "overall": "overall_quiz"}

# Content-based classification into the existing category vocabulary
# ('ingredients', 'sales_pairing', 'allergen_warning' — see
# rfone_data_store/training/pills_content.py's own docstring). The
# package's three questions per family follow one consistent template
# across all 51 pills (verified against the source content): this mapping
# reflects what each (kind, position) slot actually asks, it is not an
# arbitrary guess.
CATEGORY_MAP = {
    ("self_check", 1): "ingredients",       # "Which ingredient or component is identified..."
    ("self_check", 2): "ingredients",       # "Which flavour and texture profile is used..." (characteristics)
    ("self_check", 3): "sales_pairing",     # "Which wine is one of the two listed pairings..."
    ("final_quiz", 1): "sales_pairing",     # "...Which introduction matches the dish?" (sales phrase)
    ("final_quiz", 2): "allergen_warning",  # "Before making an allergy recommendation..."
    ("final_quiz", 3): "sales_pairing",     # "...the alternative listed pairing... Which wine?"
    ("overall_quiz", 1): "ingredients",     # "Which description correctly identifies..."
    ("overall_quiz", 2): "sales_pairing",   # "Which recommendation approach fits..."
    ("overall_quiz", 3): "allergen_warning",  # "...kitchen-verification notes..."
}


def _pill_learning_objectives(pill_json: dict) -> str:
    return " ".join(pill_json["learning_objectives"])


def _question_options_json_and_index(question_json: dict) -> tuple[str, int]:
    options = [opt["text"] for opt in question_json["options"]]
    correct_index = next(
        i for i, opt in enumerate(question_json["options"]) if opt["id"] == question_json["correct_option_id"]
    )
    return json.dumps(options), correct_index


def _check_pill_conflict(existing: "m.TrainingPill", pill_json: dict) -> str | None:
    expected_title = pill_json["name"]
    expected_objectives = _pill_learning_objectives(pill_json)
    if existing.title != expected_title:
        return f"title mismatch: db={existing.title!r} package={expected_title!r}"
    if existing.learning_objectives != expected_objectives:
        return "learning_objectives mismatch"
    return None


def _check_question_conflict(existing: "m.TrainingQuestion", q_json: dict, category: str) -> str | None:
    options_json, correct_index = _question_options_json_and_index(q_json)
    if existing.prompt != q_json["prompt"]:
        return "prompt mismatch"
    if existing.options_json != options_json:
        return "options mismatch"
    if existing.correct_index != correct_index:
        return "correct_index mismatch"
    if existing.explanation != q_json["explanation"]:
        return "explanation mismatch"
    if existing.version != q_json["version"]:
        return "version mismatch"
    if existing.category != category:
        return "category mismatch"
    return None


def plan_import(session, pills_json: list[dict]):
    """Read-only pass: determines what to create vs. skip, and collects any
    conflicts. Never writes to the session — safe to call repeatedly."""
    to_create_pills: list[dict] = []
    to_create_questions: list[tuple[str, str, int, dict, str]] = []
    skipped_pills: list[str] = []
    conflicts: list[str] = []

    for pill_json in pills_json:
        slug = pill_json["id"]
        if slug in PRESERVE_IDS:
            conflicts.append(f"{slug}: package pill id collides with a preserved existing pill")
            continue

        existing_pill = session.query(m.TrainingPill).filter(m.TrainingPill.slug == slug).first()
        if existing_pill is None:
            to_create_pills.append(pill_json)
        else:
            conflict = _check_pill_conflict(existing_pill, pill_json)
            if conflict is not None:
                conflicts.append(f"{slug}: pill conflict — {conflict}")
                continue
            skipped_pills.append(slug)

        for json_kind, db_kind in KIND_MAP.items():
            for position, q_json in enumerate(pill_json["questions"][json_kind], start=1):
                category = CATEGORY_MAP[(db_kind, position)]
                existing_q = None
                if existing_pill is not None:
                    existing_q = session.query(m.TrainingQuestion).filter(
                        m.TrainingQuestion.pill_id == existing_pill.id,
                        m.TrainingQuestion.kind == db_kind,
                        m.TrainingQuestion.position == position,
                    ).first()
                if existing_q is not None:
                    conflict = _check_question_conflict(existing_q, q_json, category)
                    if conflict is not None:
                        conflicts.append(f"{slug}:{db_kind}:{position}: question conflict — {conflict}")
                    continue
                to_create_questions.append((slug, db_kind, position, q_json, category))

    return to_create_pills, to_create_questions, skipped_pills, conflicts


def apply_import(session, to_create_pills: list[dict], to_create_questions: list[tuple]) -> tuple[int, int]:
    pills_by_slug: dict[str, "m.TrainingPill"] = {}
    for pill_json in to_create_pills:
        pill = m.TrainingPill(
            slug=pill_json["id"], title=pill_json["name"],
            learning_objectives=_pill_learning_objectives(pill_json), content_version=1,
        )
        session.add(pill)
        session.flush()
        pills_by_slug[pill_json["id"]] = pill

    question_count = 0
    for slug, db_kind, position, q_json, category in to_create_questions:
        pill = pills_by_slug.get(slug) or session.query(m.TrainingPill).filter(m.TrainingPill.slug == slug).first()
        options_json, correct_index = _question_options_json_and_index(q_json)
        session.add(m.TrainingQuestion(
            pill_id=pill.id, kind=db_kind, category=category, position=position,
            version=q_json["version"], prompt=q_json["prompt"], options_json=options_json,
            correct_index=correct_index, explanation=q_json["explanation"],
        ))
        question_count += 1

    session.flush()
    return len(pills_by_slug), question_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the 51 new Training menu pills (idempotent, atomic).")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="Path to the pills/quiz JSON package.")
    args = parser.parse_args()

    with open(args.source, encoding="utf-8") as f:
        package = json.load(f)
    pills_json = package["new_pills"]

    with SessionFactory() as session:
        to_create_pills, to_create_questions, skipped_pills, conflicts = plan_import(session, pills_json)

        if conflicts:
            print("IMPORT ABORTED — conflict(s) detected, nothing was written:", file=sys.stderr)
            for c in conflicts:
                print(" -", c, file=sys.stderr)
            return 1

        pill_count, question_count = apply_import(session, to_create_pills, to_create_questions)
        session.commit()

    print(
        f"Import OK: {pill_count} new pill(s) created, {question_count} new question(s) created, "
        f"{len(skipped_pills)} pill(s) already present and unchanged."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
