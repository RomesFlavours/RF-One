"""WHO categories and contextual declarations (BANK_RULE_SCOPE_AND_WHO_CATEGORY_001 §4-5, Product Owner, 2026-11-03).

A WHO category describes the ACTIVITY of the counterparty or service (food service, passenger transport, ...).
It is not the WHAT (which always derives from the WHY) and it is not the WHO WHY mode UNIQUE / MULTIPLE.

Category
  The AI (also with internet research) or a person PROPOSES a category with its evidence, sources and
  certainty; only a person's CONFIRMATION authorises its use by category rules. A REJECTED proposal is kept.
  Every proposal and decision is a new append-only record (`bank_flow_artifacts`, kind WHO_CATEGORY): the
  latest record of a WHO is its current state, the earlier ones are its history.

Contextual declaration
  A statement a person makes about how THEY use a WHO ("Io uso UBER soltanto per trasporto"). It is recorded
  with its exact text, the category it states and the Sources it concerns (kind WHO_DECLARATION). It is never
  a universal property of the WHO: it gives the WHO that category only on the declared Sources, so a category
  rule can be proposed for them, simulated and confirmed. Descriptions or documents that contradict it are
  isolated by the rule's exceptions, never covered by the declaration.

Nothing here classifies a movement. `category_for` is read by the WHY determination (`who_why_rules`).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select

from .. import models as m

KIND_CATEGORY = "WHO_CATEGORY"
KIND_DECLARATION = "WHO_DECLARATION"
PROPOSED, CONFIRMED, REJECTED = "PROPOSED", "CONFIRMED", "REJECTED"
ACTIVE, WITHDRAWN = "ACTIVE", "WITHDRAWN"
CERTAINTY = ("high", "medium", "low")
AI, HUMAN = "AI", "HUMAN"

# Activity of the counterparty or service. HETEROGENEOUS categories (marketplaces, general retailers) never
# support a category rule: what is bought there differs from one purchase to the next (§4, last line).
CATEGORIES = {
    "FOOD_SERVICE": "Food service (restaurant, bar, café)",
    "PASSENGER_TRANSPORT": "Passenger transport (ride, taxi, transit)",
    "AIRLINE": "Airline",
    "LODGING": "Lodging",
    "FUEL": "Fuel station",
    "GROCERY": "Grocery store, supermarket",
    "SOFTWARE": "Software and online services",
    "UTILITIES": "Utilities and telecommunications",
    "PROFESSIONAL_SERVICES": "Professional services",
    "MARKETPLACE": "Marketplace or general retailer (heterogeneous purchases)",
}
HETEROGENEOUS = {"MARKETPLACE"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _records(db, kind):
    return [(a.id, json.loads(a.payload)) for a in db.scalars(
        select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind == kind).order_by(m.BankFlowArtifact.id))]


def _add(db, kind, payload, account_id):
    record = m.BankFlowArtifact(kind=kind, payload=json.dumps(payload, ensure_ascii=False), account_id=account_id)
    db.add(record)
    db.flush()
    return dict(payload, record_id=record.id)


def _check_who(db, who_id):
    who = db.get(m.BankOccurrence, who_id) if isinstance(who_id, int) else None
    if who is None or who.status != "ACTIVE":
        raise ValueError("WHO not found.")
    return who


def _check_category(category):
    if category not in CATEGORIES:
        raise ValueError("Unknown WHO category.")


# ---------------------------------------------------------------- categories

def history(db, who_id: int) -> list[dict]:
    return [dict(p, record_id=i) for i, p in _records(db, KIND_CATEGORY) if p.get("who_id") == who_id]


def current(db) -> dict[int, dict]:
    """The latest category record of every WHO (proposed, confirmed or rejected)."""
    out = {}
    for i, p in _records(db, KIND_CATEGORY):
        out[p["who_id"]] = dict(p, record_id=i)
    return out


def confirmed(db) -> dict[int, str]:
    return {w: p["category"] for w, p in current(db).items() if p["status"] == CONFIRMED}


def propose(db, who_id: int, category: str, *, certainty: str, evidence: str, sources=(), origin: str = AI,
            account_id: int | None = None) -> dict:
    """A proposal: it authorises nothing until a person confirms it."""
    _check_who(db, who_id)
    _check_category(category)
    if certainty not in CERTAINTY:
        raise ValueError("Certainty must be high, medium or low.")
    clean = [dict(title=str(s.get("title") or "Source")[:200], url=str(s["url"])[:500])
             for s in sources or () if isinstance(s, dict) and str(s.get("url") or "").startswith(("http://", "https://"))]
    return _add(db, KIND_CATEGORY, dict(who_id=who_id, category=category, status=PROPOSED, certainty=certainty,
                                        evidence=str(evidence or "")[:4000], sources=clean[:8], origin=origin,
                                        proposed_at=_now(), decided_by=None, decided_at=None), account_id)


def decide(db, who_id: int, decision: str, *, account_id: int | None, category: str | None = None) -> dict:
    """A person confirms or rejects the current proposal (or confirms a category chosen directly)."""
    if decision not in (CONFIRMED, REJECTED):
        raise ValueError("Confirm or reject the category.")
    _check_who(db, who_id)
    latest = current(db).get(who_id)
    if category is not None:
        _check_category(category)
        base = dict(latest or {}, category=category) if latest and latest["category"] == category else dict(
            who_id=who_id, category=category, certainty="high", evidence="Chosen by a person.", sources=[], origin=HUMAN,
            proposed_at=_now())
    elif latest is None or latest["status"] != PROPOSED:
        raise ValueError("There is no category proposal to decide.")
    else:
        base = latest
    base = {k: v for k, v in base.items() if k != "record_id"}
    return _add(db, KIND_CATEGORY, dict(base, status=decision, decided_by=account_id, decided_at=_now()), account_id)


# ---------------------------------------------------------------- declarations

def declarations(db, who_id: int | None = None) -> list[dict]:
    """Active declarations (latest record per WHO and text)."""
    latest = {}
    for i, p in _records(db, KIND_DECLARATION):
        latest[(p["who_id"], p["text"])] = dict(p, record_id=i)
    return [p for p in latest.values() if p["status"] == ACTIVE and (who_id is None or p["who_id"] == who_id)]


def declare(db, who_id: int, text: str, category: str, source_ids: list[int], *, account_id: int | None) -> dict:
    """A person's statement about how they use a WHO, limited to the Sources it names."""
    _check_who(db, who_id)
    _check_category(category)
    text = " ".join(str(text or "").split())
    if not text:
        raise ValueError("Write the declaration.")
    ids = sorted({int(i) for i in source_ids or ()})
    if not ids or any(db.get(m.PaymentInstrument, i) is None for i in ids):
        raise ValueError("Name the Sources the declaration concerns.")
    return _add(db, KIND_DECLARATION, dict(who_id=who_id, text=text, category=category, source_ids=ids,
                                           status=ACTIVE, declared_by=account_id, declared_at=_now()), account_id)


def withdraw(db, record_id: int, *, account_id: int | None) -> dict:
    record = db.get(m.BankFlowArtifact, record_id)
    if record is None or record.kind != KIND_DECLARATION:
        raise ValueError("Declaration not found.")
    p = json.loads(record.payload)
    return _add(db, KIND_DECLARATION, dict(p, status=WITHDRAWN, withdrawn_by=account_id, withdrawn_at=_now()), account_id)


# ---------------------------------------------------------------- use by the WHY determination

class Categories:
    """Read once per engine: the category of a WHO on a movement's Source, with its basis."""

    def __init__(self, db):
        self.confirmed = confirmed(db)
        self.declared = {}
        for d in declarations(db):
            for source_id in d["source_ids"]:
                self.declared.setdefault((d["who_id"], source_id), d)

    def category_for(self, who_id, source_id) -> tuple[str | None, str | None]:
        """(category, basis): a confirmed category everywhere; otherwise a declaration only on its Sources."""
        if who_id in self.confirmed:
            return self.confirmed[who_id], "confirmed category"
        d = self.declared.get((who_id, source_id))
        if d:
            return d["category"], f"declaration «{d['text']}»"
        return None, None


def knowledge_signature(db) -> str:
    """Changes with every category decision or declaration (a confirmed category can change a WHY)."""
    ids = [a for a in db.scalars(select(m.BankFlowArtifact.id).where(
        m.BankFlowArtifact.kind.in_((KIND_CATEGORY, KIND_DECLARATION))).order_by(m.BankFlowArtifact.id))]
    return hashlib.sha256(json.dumps(ids).encode()).hexdigest()[:12]
