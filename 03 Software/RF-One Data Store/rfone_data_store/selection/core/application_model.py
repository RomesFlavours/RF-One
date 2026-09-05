"""Application workflow-status vocabulary (Task 3C-FIX §7, extended by Task
4A §22) — the operational review outcome a Selezionatore records for one
Application, kept structurally separate from Review Priority
(`core/signal_model.py`) and from the Phone Interview Plan's own process
status (`core/phone_interview_model.py` — NOT_STARTED/IN_PROGRESS/etc.,
never to be confused with this module's ADVANCE_TO_PHONE/ADVANCE_TO_IN_PERSON/
HOLD/STOP). Review Priority is always a system-proposed starting point for
where to look first; workflow status is a human decision only. Nothing in
this codebase sets a workflow status automatically — a brand-new
Application simply starts at NEW, and every other transition (including the
post-Phone-Interview ADVANCE_TO_IN_PERSON/HOLD/STOP decision, Task 4A §22)
is an explicit Selezionatore action (`application_service.
set_workflow_status`)."""

from __future__ import annotations

NEW = "NEW"
IN_REVIEW = "IN_REVIEW"
ADVANCE_TO_PHONE = "ADVANCE_TO_PHONE"
ADVANCE_TO_IN_PERSON = "ADVANCE_TO_IN_PERSON"
HOLD = "HOLD"
STOP = "STOP"

WORKFLOW_STATUSES = (NEW, IN_REVIEW, ADVANCE_TO_PHONE, ADVANCE_TO_IN_PERSON, HOLD, STOP)

# Statuses for which recording a concise Selezionatore reason is especially
# meaningful (task §8) — the reason field itself stays optional everywhere,
# this is only used to prompt for one in the UI.
DECISION_STATUSES = (ADVANCE_TO_PHONE, ADVANCE_TO_IN_PERSON, HOLD, STOP)

# Task 4A §22 — the three outcomes a Selezionatore may record after (or
# during) a Phone Interview. A strict subset of WORKFLOW_STATUSES, reused
# rather than duplicated as a parallel decision vocabulary.
POST_PHONE_INTERVIEW_DECISIONS = (ADVANCE_TO_IN_PERSON, HOLD, STOP)
