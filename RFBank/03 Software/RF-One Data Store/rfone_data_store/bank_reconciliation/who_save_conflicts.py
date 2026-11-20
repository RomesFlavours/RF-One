"""Check proposed WHO identities against actual movements before saving."""
from types import SimpleNamespace
from sqlalchemy import select
from .. import models as m
from . import ai_rules, flow, rule_application_safety, who_recognition as wr


class Conflict(ai_rules.AiRuleError):
    pass


def _report(conflicts):
    if conflicts:
        examples = " | ".join(conflicts[:3])
        raise Conflict(f"Conflitto WHO su {len(conflicts)} movimenti. {examples}. "
                       "Correggi il nome, l’alias o la regola e riprova.")


def _identities(reader, result):
    names = result.candidates or ([result.who] if result.who else [])
    return {reader.catalog_name(n) or n for n in names}


def check_names(db, names, target, owner_id=None, absorbed=None):
    from . import who_search_text as search
    keys = {wr.who_key(name) for name in names if name}
    keys = {k for k in keys if len(k) >= search.MIN_KEY_LENGTH}
    if not keys:
        return
    from . import who_intermediaries
    if owner_id is not None and owner_id in who_intermediaries.ids(db):
        return          # an intermediary's texts never compete with a WHO (Product Owner, 2026-11-18)
    rule_application_safety.lock_writes(db)
    reader = search.WhoRecogniser(db)
    ignored = {owner_id, absorbed}
    allowed = {wr.who_key(target), *[wr.who_key(reader.names[i]) for i in ignored if i in reader.names]}
    conflicts = []
    for txn in db.scalars(select(m.FinancialTransaction)):
        description = txn.description_original or ""
        line = " " + wr.who_key(description) + " "
        if not any(" " + key + " " in line for key in keys):
            continue
        others = {reader.names[i] for i in search.recognise(description, reader.keys) if i not in ignored}
        result = reader.recognise(txn)
        others.update(name for name in _identities(reader, result) if wr.who_key(name) not in allowed)
        if others:
            conflicts.append(f"#{txn.id} {description} ({target} / {', '.join(sorted(others))})")
    _report(conflicts)


def check_rule(db, spec, rule_id=None):
    from . import who_search_text as search
    if not spec or (spec.get("engine") == flow.ENGINE and spec.get("kind") != "EXTRACTOR"):
        return
    rule_application_safety.lock_writes(db)
    entries = flow.entries(db, future=True)
    old = next((e for e in entries if e[0].id == rule_id), None)
    if old and old[2] == spec:
        return
    proposed = (SimpleNamespace(id=rule_id or 0, title="proposta", user_title=None), None, spec)
    before = search.WhoRecogniser(db, rules=entries)
    after = search.WhoRecogniser(db, rules=[e for e in entries if e[0].id != rule_id] + [proposed])
    def identities(reader, txn, row, text_names):
        found = reader.recognise(txn, row=row)
        return {wr.who_key(n) for n in _identities(reader, found) | text_names}
    conflicts = []
    for txn in db.scalars(select(m.FinancialTransaction)):
        desc = txn.description_original or ""
        row = None
        if spec.get("engine") == flow.ENGINE:
            if not flow.extract(spec, desc):
                continue
        else:
            row = before._row(txn)
            hit = ai_rules.execute(spec, row)
            if hit.outcome != "MATCH" or not hit.who or hit.who_verify:
                continue
        row = row or before._row(txn)
        names = {before.names[i] for i in search.recognise(desc, before.keys)}
        current = identities(after, txn, row, names)
        if len(current) > 1 and current - identities(before, txn, row, names):
            conflicts.append(f"#{txn.id} {desc} ({' / '.join(sorted(current))})")
    _report(conflicts)
