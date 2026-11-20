"""One WHY configuration per WHO (BANK_WHO_WHY_CONFIG_001, BANK-2026-11-04, Product Owner, 2026-11-06).

A WHO has ONE configuration, independent of the account or card, so a new card inherits the behaviour meant for
its owner:

  SINGLE      one WHY whatever the Source;
  BY_SUBJECT  a Personal WHY and a Company WHY. Personal / Company is read from the owner entity of the Source at
              the movement date (`card_configuration.owner_entity_for`, the same owner that gives WHOM); no
              classification is added to the Sources and the company's identity is kept. An unknown owner is not
              Company: the movement stays open;
  RULE        "Da regola": the existing MULTIPLE mode (`who_why_rules`), only WHO WHY rules decide.

After WHO recognition (`who_why_rules.Resolver.determine`):
  1. an approved exception for that WHO and that specific company applies when the movement's owner at the date
     is that company and the exception replaces the WHO's current behaviour (`replaces`);
  2. otherwise the configured behaviour (SINGLE, BY_SUBJECT, or the rules);
  3. WHOM is the Source owner, unless the exception names another entity explicitly;
  4. WHAT always derives from the WHY;
  5. insufficient data or conflicting rules leave the movement open.

A WHO without a configuration row keeps the former WHO + Source classifications (`bank_who_source_classifications`),
which are never deleted here. `convert_pairs` turns only the coherent pairs of a WHO into its configuration and
reports, without deciding, the WHOs whose pairs cannot be reduced to it unambiguously.

Nothing here writes a movement classification; saving is a person's action after a simulation.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import inspect, select

from .. import models as m
from . import card_configuration

SINGLE, BY_SUBJECT, RULE = "SINGLE", "BY_SUBJECT", "RULE"
BEHAVIOURS = (SINGLE, BY_SUBJECT, RULE)
REPLACES = {SINGLE: "SINGLE", BY_SUBJECT: "COMPANY", RULE: "RULE"}     # what a company exception replaces
REPLACES_LABEL = {"SINGLE": "WHY unico", "COMPANY": "WHY aziendale", "RULE": "Da regola"}
ORIGIN_CONVERTED, ORIGIN_PERSON = "CONVERTED_FROM_PAIRS", "PERSON"

# Results of the pair analysis
COHERENT_SINGLE, COHERENT_SUBJECT = "SINGLE", "BY_SUBJECT"
NO_WHY = "NO_WHY"
CONFLICT_SAME_SUBJECT = "CONFLICT_SAME_SUBJECT"          # different WHYs for the same owner / subject
CONFLICT_COMPANIES = "CONFLICT_BETWEEN_COMPANIES"         # companies with different WHYs: no general company WHY
OWNER_UNCERTAIN = "OWNER_UNCERTAIN"                       # a classified Source has no single owner
CONFLICTS = (CONFLICT_SAME_SUBJECT, CONFLICT_COMPANIES, OWNER_UNCERTAIN)
CONFLICT_LABELS = {CONFLICT_SAME_SUBJECT: "WHY diversi per lo stesso titolare (Personale o stessa azienda)",
                   CONFLICT_COMPANIES: "WHY diversi tra aziende: nessun WHY aziendale univoco",
                   OWNER_UNCERTAIN: "conto/carta senza un unico titolare"}


def has_tables(db) -> bool:
    insp = inspect(db.get_bind())
    return insp.has_table("bank_who_why_configs") and insp.has_table("bank_who_why_exceptions")


def is_personal(entity) -> bool:
    return entity is not None and entity.entity_type == m.REPORTING_ENTITY_PERSONAL


@dataclass
class Config:
    who_id: int
    behaviour: str                    # SINGLE | BY_SUBJECT (RULE comes from the mode)
    why_id: int | None = None
    personal_why_id: int | None = None
    company_why_id: int | None = None
    origin: str | None = None
    exceptions: dict = field(default_factory=dict)      # reporting entity id -> m.BankWhoWhyException-like dict


def load(db) -> tuple[dict, dict]:
    """(configs by WHO, exceptions by WHO -> {entity id: dict}). Empty on a database without the tables."""
    if not has_tables(db):
        return {}, {}
    configs = {c.occurrence_id: Config(c.occurrence_id, c.behaviour, c.why_id, c.personal_why_id, c.company_why_id,
                                       c.origin) for c in db.scalars(select(m.BankWhoWhyConfig))}
    exceptions = defaultdict(dict)
    for x in db.scalars(select(m.BankWhoWhyException)):
        exceptions[x.occurrence_id][x.reporting_entity_id] = dict(
            id=x.id, entity_id=x.reporting_entity_id, replaces=x.replaces, why_id=x.why_id, whom_id=x.whom_entity_id)
    return configs, dict(exceptions)


def signature(db) -> str:
    """Changes with every configuration / exception (part of the engine's knowledge signature)."""
    configs, exceptions = load(db)
    return json.dumps([sorted((k, v.behaviour, v.why_id, v.personal_why_id, v.company_why_id) for k, v in configs.items()),
                       sorted((k, sorted((e, x["replaces"], x["why_id"], x["whom_id"]) for e, x in v.items()))
                              for k, v in exceptions.items())])


# ---------------------------------------------------------------- existing WHO + Source pairs

def source_owners(db) -> dict:
    """Owner entity ids of each Source over the dates of its movements (today when it has none)."""
    dates = defaultdict(set)
    for iid, posting, txn_date in db.execute(select(m.FinancialTransaction.payment_instrument_id,
                                                    m.FinancialTransaction.posting_date,
                                                    m.FinancialTransaction.transaction_date)):
        dates[iid].add(posting or txn_date)
    out = {}
    for inst in db.scalars(select(m.PaymentInstrument)):
        owners = set()
        for day in dates.get(inst.id) or {date.today()}:
            e = card_configuration.owner_entity_for(db, instrument=inst, on_date=day)
            owners.add(e.id if e else None)
        out[inst.id] = owners
    return out


def analyse_pairs(db) -> dict:
    """Per WHO: how its WHO + Source pairs reduce to one configuration, or why they cannot. Read-only.

    dict(who_id -> dict(kind, why_id | personal_why_id | company_why_id, pairs=[...], reason)). Pairs without a WHY
    carry no choice and are only listed. No criterion is invented: a WHO with WHYs on Personal Sources only gets a
    Personal WHY only (and the reverse); companies with different WHYs, or the same subject with different WHYs,
    are conflicts left to a person."""
    entities = {e.id: e for e in db.scalars(select(m.ReportingEntity))}
    instruments = {i.id: i for i in db.scalars(select(m.PaymentInstrument))}
    owners = source_owners(db)
    by_who = defaultdict(list)
    for p in db.scalars(select(m.BankWhoSourceClassification)):
        own = owners.get(p.payment_instrument_id) or {None}
        owner_id = next(iter(own)) if len(own) == 1 else None
        by_who[p.occurrence_id].append(dict(
            source_id=p.payment_instrument_id,
            source=instruments[p.payment_instrument_id].display_name if p.payment_instrument_id in instruments else None,
            owner_id=owner_id, owner=entities[owner_id].name if owner_id in entities else None,
            subject=None if owner_id not in entities else ("PERSONAL" if is_personal(entities[owner_id]) else "COMPANY"),
            why_id=p.transaction_reason_id, uncertain=len(own) != 1))
    out = {}
    for who_id, pairs in by_who.items():
        chosen = [p for p in pairs if p["why_id"]]
        personal = {p["why_id"] for p in chosen if p["subject"] == "PERSONAL"}
        company_by_entity = defaultdict(set)
        for p in chosen:
            if p["subject"] == "COMPANY":
                company_by_entity[p["owner_id"]].add(p["why_id"])
        company = set().union(*company_by_entity.values()) if company_by_entity else set()
        res = dict(pairs=pairs)
        if not chosen:
            res.update(kind=NO_WHY)
        elif any(p["uncertain"] or p["subject"] is None for p in chosen):
            res.update(kind=OWNER_UNCERTAIN)
        elif len(personal) > 1 or any(len(v) > 1 for v in company_by_entity.values()):
            res.update(kind=CONFLICT_SAME_SUBJECT)
        elif len(company) > 1:
            res.update(kind=CONFLICT_COMPANIES)
        elif personal and company and personal == company:
            res.update(kind=COHERENT_SINGLE, why_id=next(iter(personal)))
        else:
            res.update(kind=COHERENT_SUBJECT, personal_why_id=next(iter(personal), None),
                       company_why_id=next(iter(company), None))
        res["reason"] = CONFLICT_LABELS.get(res["kind"])
        out[who_id] = res
    return out


def convert_pairs(db, *, account_id: int | None = None, dry_run: bool = True) -> dict:
    """Creates the configuration of every WHO whose pairs are coherent and that has no configuration and is not
    MULTIPLE. Pairs are kept unchanged. Conflicts are reported, never resolved."""
    from . import who_why_rules
    configs, _exceptions = load(db) if has_tables(db) else ({}, {})
    modes = who_why_rules.modes(db)
    analysis = analyse_pairs(db)
    report = dict(created=[], conflicts=[], no_why=[], skipped=[], counts=Counter())
    for who_id, res in sorted(analysis.items()):
        kind = res["kind"]
        report["counts"][kind] += 1
        if who_id in configs or modes.get(who_id) == who_why_rules.MULTIPLE:
            report["skipped"].append(dict(who_id=who_id, kind=kind))
            continue
        if kind in CONFLICTS:
            report["conflicts"].append(dict(who_id=who_id, kind=kind, reason=res["reason"], pairs=res["pairs"]))
            continue
        if kind == NO_WHY:
            report["no_why"].append(who_id)
            continue
        row = dict(who_id=who_id, behaviour=kind, why_id=res.get("why_id"),
                   personal_why_id=res.get("personal_why_id"), company_why_id=res.get("company_why_id"),
                   pairs_without_why=[p["source"] for p in res["pairs"] if not p["why_id"]])
        report["created"].append(row)
        if not dry_run:
            db.add(m.BankWhoWhyConfig(occurrence_id=who_id, behaviour=kind, why_id=row["why_id"],
                                      personal_why_id=row["personal_why_id"], company_why_id=row["company_why_id"],
                                      origin=ORIGIN_CONVERTED, updated_by_account_id=account_id))
    if not dry_run:
        db.flush()
    report["counts"] = dict(report["counts"])
    return report


# ---------------------------------------------------------------- a person's configuration

def _usable_why(db, why_id, label):
    from . import why_what
    if why_id is None:
        return None
    if type(why_id) is not int:
        raise ValueError(f"{label}: invalid WHY.")
    reason = db.get(m.BankTransactionReason, why_id)
    if reason is None or reason.status != "ACTIVE":
        raise ValueError(f"{label}: the WHY is missing or inactive.")
    if why_what.is_provisional(db, reason):
        raise ValueError(f"{label}: a provisional WHY cannot be configured.")
    return why_id


def validate(db, draft: dict) -> dict:
    """The draft as RF-One will use it; raises ValueError with a readable reason."""
    who_id = draft.get("who_id")
    who = db.get(m.BankOccurrence, who_id) if type(who_id) is int else None
    if who is None or who.status != "ACTIVE":
        raise ValueError("WHO not found or inactive.")
    behaviour = draft.get("behaviour")
    if behaviour not in BEHAVIOURS:
        raise ValueError("Choose single WHY, Personal/Company or From rule.")
    out = dict(who_id=who_id, behaviour=behaviour, why_id=None, personal_why_id=None, company_why_id=None, exceptions=[])
    if behaviour == SINGLE:
        out["why_id"] = _usable_why(db, draft.get("why_id"), "Single WHY")
        if out["why_id"] is None:
            raise ValueError("Choose the single WHY.")
    elif behaviour == BY_SUBJECT:
        out["personal_why_id"] = _usable_why(db, draft.get("personal_why_id"), "Personal WHY")
        out["company_why_id"] = _usable_why(db, draft.get("company_why_id"), "Company WHY")
        if out["personal_why_id"] is None and out["company_why_id"] is None:
            raise ValueError("Choose at least the Personal or the Company WHY.")
    seen = set()
    for x in draft.get("exceptions") or []:
        entity = db.get(m.ReportingEntity, x.get("entity_id")) if type(x.get("entity_id")) is int else None
        if entity is None or is_personal(entity):
            raise ValueError("An exception names a specific company.")
        if entity.id in seen:
            raise ValueError(f"Two exceptions for {entity.name}.")
        seen.add(entity.id)
        why_id = _usable_why(db, x.get("why_id"), f"Exception {entity.name}")
        if why_id is None:
            raise ValueError(f"Exception {entity.name}: choose its WHY.")
        whom = x.get("whom_id")
        if whom is not None and (type(whom) is not int or db.get(m.ReportingEntity, whom) is None):
            raise ValueError(f"Exception {entity.name}: unknown WHOM.")
        out["exceptions"].append(dict(entity_id=entity.id, why_id=why_id, whom_id=whom, replaces=REPLACES[behaviour]))
    return out


def save(db, draft: dict, *, account_id: int | None) -> dict:
    """A person saves the WHO's configuration after its simulation. The mode follows the behaviour (RULE =
    MULTIPLE, otherwise UNIQUE); the exceptions are replaced by the ones submitted, each naming the behaviour it
    replaces. The WHO + Source pairs and every movement are left as they are."""
    from . import who_why_rules
    if not has_tables(db):
        raise ValueError("The database needs the migration e2c620261106.")
    spec = validate(db, draft)
    who_id = spec["who_id"]
    row = db.get(m.BankWhoWhyConfig, who_id)
    if spec["behaviour"] == RULE:
        who_why_rules.set_mode(db, who_id, who_why_rules.MULTIPLE, account_id=account_id)
    else:
        who_why_rules.set_mode(db, who_id, who_why_rules.UNIQUE, account_id=account_id)
        if row is None:
            row = m.BankWhoWhyConfig(occurrence_id=who_id, behaviour=spec["behaviour"])
            db.add(row)
        row.behaviour = spec["behaviour"]
        row.why_id, row.personal_why_id, row.company_why_id = spec["why_id"], spec["personal_why_id"], spec["company_why_id"]
        row.origin, row.updated_by_account_id = ORIGIN_PERSON, account_id
    for old in db.scalars(select(m.BankWhoWhyException).where(m.BankWhoWhyException.occurrence_id == who_id)):
        db.delete(old)
    db.flush()
    for x in spec["exceptions"]:
        db.add(m.BankWhoWhyException(occurrence_id=who_id, reporting_entity_id=x["entity_id"], replaces=x["replaces"],
                                     why_id=x["why_id"], whom_entity_id=x["whom_id"], approved_by_account_id=account_id))
    db.flush()
    return spec


# ---------------------------------------------------------------- determination helper (engine)

@dataclass
class Choice:
    """What the configuration says for one movement: a WHY (and optional WHOM), 'rules', or open."""
    why_id: int | None = None
    whom_id: int | None = None
    method: str | None = None
    reference: str = ""
    use_rules: bool = False
    open_message: str | None = None


def choose(config: Config | None, exceptions: dict, *, behaviour: str, owner) -> Choice | None:
    """None when the WHO has no configuration and is not RULE (the former WHO + Source pair decides)."""
    if config is None and behaviour != RULE:
        return None
    replaced = REPLACES[behaviour]
    applicable = {e: x for e, x in (exceptions or {}).items() if x["replaces"] == replaced}
    if applicable and owner is None:
        return Choice(open_message="the owner of the account/card at the movement date is unknown: the company "
                                   "exceptions of this WHO cannot be checked")
    if owner is not None and owner.id in applicable:
        x = applicable[owner.id]
        return Choice(why_id=x["why_id"], whom_id=x["whom_id"], method="WHO EXCEPTION",
                      reference=f"exception #{x['id']} for {owner.name} (replaces {REPLACES_LABEL[replaced]})")
    if behaviour == RULE:
        return Choice(use_rules=True)
    if behaviour == SINGLE:
        return Choice(why_id=config.why_id, method="WHO SINGLE WHY", reference="single WHY of the WHO") \
            if config.why_id else Choice(use_rules=True, open_message="the single WHY of the WHO is not set")
    if owner is None:
        return Choice(open_message="the owner of the account/card at the movement date is unknown: Personal or "
                                   "Company cannot be determined")
    if is_personal(owner):
        why, label = config.personal_why_id, "Personal"
    else:
        why, label = config.company_why_id, "Company"
    if why:
        return Choice(why_id=why, method=f"WHO {label.upper()} WHY", reference=f"{label} WHY of the WHO (owner {owner.name})")
    return Choice(use_rules=True, open_message=f"the {label} WHY of the WHO is not set")
