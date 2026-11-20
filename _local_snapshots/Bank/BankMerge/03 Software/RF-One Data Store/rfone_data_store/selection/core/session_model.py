"""Selection Session vocabulary (Task 5C). Defines the generic, restaurant-
agnostic MEANING of a Session's lifecycle status — never a specific
Session's actual data, which always lives in the persisted
`SelectionSession` row (`.. models`), populated via `selection/
session_service.py`. Mirrors `core/stage_model.py`'s role exactly:
vocabulary + one small pure function, no persistence.
"""

from __future__ import annotations

DRAFT = "DRAFT"
RULES_REVIEW = "RULES_REVIEW"
ACTIVE = "ACTIVE"
PAUSED = "PAUSED"
CLOSED = "CLOSED"

SESSION_STATUSES = (DRAFT, RULES_REVIEW, ACTIVE, PAUSED, CLOSED)

# Statuses under which "prepare the Session" actions are allowed (task §13:
# view/edit setup, review rules, modify rules, configure Selezionatori) —
# deliberately NOT a strict forward-only sequence (mirrors `stage_model.py`'s
# own "total freedom" philosophy): a Session may be paused and its rules
# revisited without being force-marched through a fixed state machine.
PREPARATION_STATUSES = (DRAFT, RULES_REVIEW, PAUSED)


def validate_session_status(status: str) -> None:
    if status not in SESSION_STATUSES:
        raise ValueError(f"Unknown Selection Session status {status!r}; expected one of {SESSION_STATUSES}")
