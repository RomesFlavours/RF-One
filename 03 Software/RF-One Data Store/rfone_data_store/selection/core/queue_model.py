"""Operational Queue/List vocabulary (Task 5A-FIX §7/§8/§9). A queue/list
is a restaurant-configurable, PURELY ORGANIZATIONAL concept (e.g. "Active
Review," "Call Later," "Reconsider") — never a hiring decision (task §14).
Mirrors every other `core/*_model.py` module's role: vocabulary only, no
persistence.

`SOURCES` distinguishes an Outcome-driven queue move from a direct,
independent Selezionatore action — both are recorded identically in
`ApplicationQueueMovement` history, distinguished only by this field (task
§9's own "source/reason").
"""

from __future__ import annotations

MANUAL = "MANUAL"
OUTCOME_ACTION = "OUTCOME_ACTION"
# Task 5E §28 — the READY FOR PHONE REVIEW move: an explicit, restaurant-
# configured automatic move (task's own "RF-One may determine that
# sufficient early-stage evidence is available"), never a hiring decision
# and never `ADVANCE_TO_PHONE` (task §29 — that stays exclusively a
# Selezionatore-driven Outcome/Stage action).
AUTOMATIC_READINESS = "AUTOMATIC_READINESS"

SOURCES = (MANUAL, OUTCOME_ACTION, AUTOMATIC_READINESS)


def validate_source(value: str) -> None:
    if value not in SOURCES:
        raise ValueError(f"Unknown queue-movement source {value!r}; expected one of {SOURCES}")
