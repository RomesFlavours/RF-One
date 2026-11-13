"""Safe catalog registration of WHO names read by approved rules; never classifies movements."""
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from sqlalchemy import select
from .. import models as m
from . import manual_reconciliation, who_recognition as wr

@dataclass
class Assessment:
    state: str
    name: str
    occurrence_id: int | None = None
    candidates: list = field(default_factory=list)
    evidence: str = ""

def similar_keys(left, right):
    if not left or not right or left == right:
        return False
    a, b = set(left.split()), set(right.split())
    if min(len(left), len(right)) >= 4 and (a <= b or b <= a):
        return True  # added/removed words, including reordered words
    return min(len(left), len(right)) >= 6 and SequenceMatcher(None, left, right).ratio() >= .90

class NewWhoGuard:
    def __init__(self, db):
        self.resolver = wr.CanonicalWhoResolver(db)
        self.names = {o.id: o.canonical_name for o in self.resolver.by_id.values()}
        self.keys = [(wr.who_key(o.canonical_name), o.id) for o in self.resolver.by_id.values()]
        self.keys += [(key, oid) for oid, key in db.execute(select(m.BankOccurrenceAlias.occurrence_id, m.BankOccurrenceAlias.alias_key))]

    def assess(self, name):
        name = " ".join(str(name or "").split()).upper()
        if len(name) > 255 or sum(c.isalpha() for c in name) < 2:
            return Assessment("INVALID", name, evidence="The extracted WHO is not a valid catalog name.")
        existing, method, held = self.resolver.by_identity(name)
        if existing:
            return Assessment("EXISTING", existing.canonical_name, existing.id)
        if held:
            return Assessment("HELD", name, evidence=held)
        key = wr.who_key(name)
        ids = sorted({oid for other, oid in self.keys if key == other or similar_keys(key, other)})
        if ids:
            names = [self.names[i] for i in ids]
            return Assessment("SIMILAR", name, candidates=names,
                              evidence="Extracted WHO resembles a saved name or alias: " + " / ".join(names))
        return Assessment("NEW", name)

def register_candidates(db, names):
    """One transaction supplied by caller. Compare all candidates before creating any of them."""
    guard = NewWhoGuard(db)
    assessments = {wr.who_key(n): guard.assess(n) for n in names}
    held, created, reused = {}, [], []
    new = {k: a for k, a in assessments.items() if a.state == "NEW"}
    for key, a in assessments.items():
        peers = [other.name for k, other in new.items() if k != key and similar_keys(key, k)] if a.state == "NEW" else []
        if peers:
            held[key] = "Several new names from this run are similar: " + " / ".join([a.name] + sorted(peers))
        elif a.state in ("SIMILAR", "HELD", "INVALID"):
            held[key] = a.evidence
    for key, a in assessments.items():
        if key in held:
            continue
        if a.state == "EXISTING":
            reused.append(a.occurrence_id)
            continue
        result = manual_reconciliation.create_who(db, name=a.name)
        (reused if result.reused else created).append(result.occurrence.id)
    db.flush()
    return dict(created=created, reused=reused, held=held)
