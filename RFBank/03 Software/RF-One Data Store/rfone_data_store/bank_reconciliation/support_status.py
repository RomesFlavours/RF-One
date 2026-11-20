"""Status of one payment observed in several support documents (PayPal, Zelle) — RFBank, 2026-11-17.

The result never depends on the order in which files were uploaded: the most recent file is not assumed to carry
the most recent status. Statuses are ordered by what can follow what:

    pending  ->  completed  ->  reversed / refunded / returned
    pending  ->  canceled / denied / failed / expired / declined

* all observations agree                          -> that status (CONSISTENT)
* pending plus exactly one later status           -> the later status (UPDATED)
* completed plus exactly one after-completion one -> the after-completion status (UPDATED)
* anything else (two different final statuses, completed and canceled, an unknown status that differs)
  -> no status, with the reason (CONFLICT): the case stays to be clarified.
"""
from __future__ import annotations

PENDING = {"pending", "in progress", "processing", "scheduled", "unclaimed", "held", "on hold"}
COMPLETED = {"completed", "sent", "delivered", "paid", "cleared"}
AFTER_COMPLETION = {"reversed", "refunded", "partially refunded", "returned"}
INSTEAD_OF_COMPLETION = {"canceled", "cancelled", "denied", "failed", "expired", "declined", "voided"}


def _class(status: str) -> str:
    s = status.casefold()
    for name, values in (("P", PENDING), ("C", COMPLETED), ("A", AFTER_COMPLETION), ("X", INSTEAD_OF_COMPLETION)):
        if s in values:
            return name
    return "U"


def resolve(statuses) -> tuple[str | None, str, str | None]:
    """(status, basis, conflict). basis: NOT_STATED, CONSISTENT, UPDATED, CONFLICT."""
    distinct = {}
    for s in statuses:
        s = " ".join(str(s or "").split())
        if s:
            distinct.setdefault(s.casefold(), s)
    if not distinct:
        return None, "NOT_STATED", None
    if len(distinct) == 1:
        return next(iter(distinct.values())), "CONSISTENT", None
    later = {k: v for k, v in distinct.items() if _class(v) != "P"}
    if len(later) == 1 and _class(next(iter(later.values()))) != "U":
        return next(iter(later.values())), "UPDATED", None
    classes = {_class(v): v for v in later.values()}
    if len(later) == 2 and set(classes) == {"C", "A"}:
        return classes["A"], "UPDATED", None
    return None, "CONFLICT", "Stati non conciliabili: " + ", ".join(sorted(distinct.values()))
