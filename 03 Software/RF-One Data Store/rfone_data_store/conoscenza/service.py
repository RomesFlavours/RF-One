"""Conoscenza rules (`10 System/Conoscenza/README.md`).

Everything that decides what may be written or read lives here; the HTTP
service, the MCP servers and the command line only translate requests.
Every operation, successful or refused, is written to
`conoscenza_access_log` with the PERSON and the TOOL of the credential, so
the register itself shows who consulted or wrote what, through which AI,
and when.

Three distinct attributions on every entry:
- `contributed_by_person_id` — the person who provided the contribution
  (NULL = unknown, kept unknown for undocumented history);
- `recorded_by` — the tool (CLAUDE, CODEX, CHATGPT, IMPORTER) that wrote it,
  always taken from the credential, never declared;
- `decided_by_person_id` / `decided_by` — for a decision, who took or
  approved it.

Invariants:
- exactly one CURRENT row per series; a change is a new version, the
  replaced one becomes SUPERSEDED and stays readable;
- only the register owner (Pino) creates PO_EXPLICIT decisions; another
  person's decision is a PROPOSAL until the owner approves it — the approval
  adds a new PO_EXPLICIT version and keeps the proposal;
- an AI hypothesis or a proposal never replaces an owner decision;
- a non-owner reads, contributes and approves only where an access rule
  allows it (no rule = no access); the owner needs no rule;
- the same request key never creates a second row (safe repetition);
- a work update in stage IMPLEMENTED / VERIFIED / RELEASED carries evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import models as k
from .search import rank
from .store import utcnow

KIND_LABELS = {"DECISION": "Decisione", "CORRECTION": "Correzione motivata", "WORK_UPDATE": "Stato del lavoro"}
AUTHORITY_LABELS = {"PO_EXPLICIT": "Decisione esplicita di Pino", "PROPOSAL": "Proposta non ancora approvata",
                    "AI_HYPOTHESIS": "Ipotesi dell'AI, non confermata",
                    "EVIDENCE": "Esito tecnico documentato da evidenze"}
STATUS_LABELS = {"CURRENT": "vigente", "SUPERSEDED": "sostituita", "WITHDRAWN": "ritirata"}
STAGE_LABELS = {"DESIGNED": "progettato", "IMPLEMENTED": "implementato", "VERIFIED": "verificato",
                "RELEASED": "rilasciato"}
UNKNOWN = "sconosciuto"

TEXT_FIELDS = ("domain", "title", "statement", "rationale", "validity_conditions", "exceptions", "keywords",
               "decided_by", "session_ref", "source_ref", "source_excerpt", "work_ref")


class ConoscenzaError(ValueError):
    """A refused operation, with a message meant for the person."""


@dataclass
class Principal:
    """The authenticated caller: one person using one tool."""

    client: str
    credential_id: int | None = None
    person_id: int | None = None
    person_name: str | None = None
    is_owner: bool = False
    rules: list[tuple[str, str]] = field(default_factory=list)  # (permission, domain_pattern)

    def can(self, permission: str, domain: str | None) -> bool:
        if self.is_owner:
            return True
        d = (domain or "").strip().lower()
        return any(p == permission and (pat == "*" or d.startswith(pat.strip().lower()))
                   for p, pat in self.rules)

    def readable(self, items):
        return [i for i in items if self.can("READ", i.domain)]


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _choice(value: Any, allowed: tuple[str, ...], label: str) -> str:
    text = (_clean(value) or "").upper()
    if text not in allowed:
        raise ConoscenzaError(f"{label} non valido: {value!r}. Valori ammessi: {', '.join(allowed)}.")
    return text


def _log(db: Session, who: Principal, operation: str, *, session_ref=None, query=None, ids=None,
         outcome="OK", detail=None) -> None:
    db.add(k.KnowledgeAccess(client=who.client, person_id=who.person_id, session_ref=_clean(session_ref),
                             operation=operation, query=query,
                             result_item_ids=",".join(str(i) for i in ids) if ids else None,
                             outcome=outcome, detail=detail, occurred_at=utcnow()))


def log_failure(session_factory, who: Principal, operation: str, detail: str, *, session_ref=None,
                query=None) -> None:
    """Record a refused/failed operation in its own transaction."""
    try:
        with session_factory() as db:
            _log(db, who, operation, session_ref=session_ref, query=query, outcome="REFUSED", detail=detail)
            db.commit()
    except Exception:  # the register itself may be the failure
        pass


def _content_hash(data: dict) -> str:
    payload = {f: data.get(f) for f in ("kind", "authority", "domain", "title", "statement", "rationale",
                                         "validity_conditions", "exceptions", "work_stage", "source_ref")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _person_by_name(db: Session, name: str | None) -> k.KnowledgePerson | None:
    if not name:
        return None
    return db.scalar(select(k.KnowledgePerson).where(func.lower(k.KnowledgePerson.name) == name.strip().lower()))


def _normalize(db: Session, raw: dict, *, who: Principal, salt: str = "") -> dict:
    data: dict[str, Any] = {f: _clean(raw.get(f)) for f in TEXT_FIELDS}
    data["kind"] = _choice(raw.get("kind"), k.KINDS, "Tipo")
    if data["kind"] == "WORK_UPDATE":
        data["authority"] = "EVIDENCE"  # a work outcome is a fact with evidence, not a decision
    else:
        data["authority"] = _choice(raw.get("authority") or "AI_HYPOTHESIS",
                                    ("PO_EXPLICIT", "PROPOSAL", "AI_HYPOTHESIS"), "Autorità")
    data["source_type"] = _choice(raw.get("source_type") or "CHAT_SESSION", k.SOURCE_TYPES, "Tipo di fonte")
    for required, label in (("domain", "Dominio"), ("title", "Titolo"), ("statement", "Contenuto"),
                            ("source_ref", "Riferimento alla fonte")):
        if not data[required]:
            raise ConoscenzaError(f"{label} obbligatorio.")
    if not who.can("CONTRIBUTE", data["domain"]):
        raise ConoscenzaError(f"{who.person_name or 'Questa persona'} non può contribuire al dominio "
                              f"{data['domain']}.")

    # Who provided it: the credential's person; undocumented history stays unknown.
    data["contributed_by_person_id"] = None if who.client == "IMPORTER" else who.person_id
    data["decided_by_person_id"] = None
    if data["authority"] == "PO_EXPLICIT":
        if who.client == "IMPORTER":
            # Historical import: keep the documented decider; it must be the owner.
            person = _person_by_name(db, data["decided_by"])
            if not data["decided_by"]:
                raise ConoscenzaError("Una decisione esplicita storica richiede chi ha deciso (decided_by).")
            data["decided_by_person_id"] = person.id if person and person.is_owner else None
        elif who.is_owner:
            data["decided_by_person_id"] = who.person_id
            data["decided_by"] = data["decided_by"] or who.person_name
        else:
            raise ConoscenzaError("Solo Pino prende decisioni esplicite: registrare il contributo come "
                                  "PROPOSAL; diventerà decisione con la sua approvazione.")
    elif data["authority"] == "PROPOSAL":
        data["decided_by"] = None
    decided_on = _clean(raw.get("decided_on"))
    try:
        data["decided_on"] = date.fromisoformat(decided_on) if decided_on else None
    except ValueError as exc:
        raise ConoscenzaError(f"Data della decisione non valida: {decided_on!r} (formato AAAA-MM-GG).") from exc
    if data["kind"] == "WORK_UPDATE":
        data["work_stage"] = _choice(raw.get("work_stage"), k.WORK_STAGES, "Stadio del lavoro")
        if not data["work_ref"]:
            raise ConoscenzaError("Uno stato del lavoro richiede il riferimento al lavoro (work_ref).")
    else:
        if _clean(raw.get("work_stage")):
            raise ConoscenzaError("Lo stadio del lavoro vale solo per gli aggiornamenti sul lavoro.")
        data["work_stage"] = None
    data["rationale_status"] = "KNOWN" if data["rationale"] else "UNKNOWN"
    evidence = []
    for ev in raw.get("evidence") or []:
        reference = _clean(ev.get("reference"))
        if not reference:
            raise ConoscenzaError("Ogni evidenza richiede un riferimento.")
        evidence.append({"kind": _choice(ev.get("kind"), k.EVIDENCE_KINDS, "Tipo di evidenza"),
                         "reference": reference, "description": _clean(ev.get("description"))})
    stage = data["work_stage"]
    kinds = {e["kind"] for e in evidence}
    if stage in ("IMPLEMENTED", "VERIFIED", "RELEASED") and not evidence:
        raise ConoscenzaError(f"Lo stadio '{STAGE_LABELS[stage]}' richiede almeno un'evidenza.")
    if stage == "VERIFIED" and not kinds & {"TEST", "RELEASE"}:
        raise ConoscenzaError("Lo stadio 'verificato' richiede un'evidenza di test o di rilascio.")
    if stage == "RELEASED" and "RELEASE" not in kinds:
        raise ConoscenzaError("Lo stadio 'rilasciato' richiede un'evidenza di rilascio.")
    data["evidence"] = evidence
    data["content_sha256"] = _content_hash(data)
    key = _clean(raw.get("request_key"))
    data["request_key"] = (key[:128] if key else
                           hashlib.sha256(f"{who.client}|{data['content_sha256']}|{salt}".encode()).hexdigest())
    return data


def _existing(db: Session, data: dict) -> k.KnowledgeItem | None:
    found = db.scalar(select(k.KnowledgeItem).where(k.KnowledgeItem.request_key == data["request_key"]))
    if found:
        return found
    # Same content from the same source already registered (by any client).
    return db.scalar(select(k.KnowledgeItem).where(k.KnowledgeItem.content_sha256 == data["content_sha256"]))


def _insert(db: Session, data: dict, *, who: Principal, series_id=None, version=1, supersedes_id=None):
    columns = {f: data[f] for f in TEXT_FIELDS}
    item = k.KnowledgeItem(**columns, kind=data["kind"], authority=data["authority"],
                           source_type=data["source_type"], decided_on=data["decided_on"],
                           work_stage=data["work_stage"], rationale_status=data["rationale_status"],
                           contributed_by_person_id=data["contributed_by_person_id"],
                           decided_by_person_id=data["decided_by_person_id"],
                           request_key=data["request_key"], content_sha256=data["content_sha256"],
                           status="CURRENT", version=version, series_id=series_id,
                           supersedes_id=supersedes_id, recorded_by=who.client, recorded_at=utcnow())
    db.add(item)
    db.flush()
    if item.series_id is None:
        item.series_id = item.id
    for ev in data["evidence"]:
        db.add(k.KnowledgeEvidence(item_id=item.id, **ev))
    db.flush()
    return item


def record(db: Session, who: Principal, raw: dict) -> dict:
    """Register a new decision, correction, proposal or work update. Returns
    the stored entry read back from the register, or the existing one."""
    data = _normalize(db, raw, who=who)
    existing = _existing(db, data)
    if existing:
        _log(db, who, "WRITE", session_ref=data["session_ref"], ids=[existing.id], outcome="DUPLICATE",
             detail="già registrato: nessuna nuova riga")
        db.commit()
        return {"esito": "GIA_REGISTRATO", "item": read_item(db, existing.id)}
    item = _insert(db, data, who=who)
    _log(db, who, "WORK" if data["kind"] == "WORK_UPDATE" else "WRITE", session_ref=data["session_ref"],
         ids=[item.id], detail=data["title"])
    db.commit()
    return {"esito": "REGISTRATO", "item": read_item(db, item.id)}


def _merged_from(db: Session, old: k.KnowledgeItem, raw: dict) -> dict:
    merged = {f: getattr(old, f) for f in TEXT_FIELDS}
    merged.update(kind=old.kind, authority=old.authority, source_type=old.source_type,
                  decided_on=old.decided_on.isoformat() if old.decided_on else None, work_stage=old.work_stage)
    merged.update({key: value for key, value in raw.items() if value is not None})
    if "evidence" not in raw:
        merged["evidence"] = [{"kind": e.kind, "reference": e.reference, "description": e.description}
                              for e in db.scalars(select(k.KnowledgeEvidence)
                                                  .where(k.KnowledgeEvidence.item_id == old.id))]
    return merged


def _replace(db: Session, who: Principal, old: k.KnowledgeItem, data: dict, operation: str) -> k.KnowledgeItem:
    old.status = "SUPERSEDED"
    db.flush()
    new = _insert(db, data, who=who, series_id=old.series_id, version=old.version + 1, supersedes_id=old.id)
    _log(db, who, operation, session_ref=data["session_ref"], ids=[old.id, new.id],
         detail=f"voce {old.id} sostituita da {new.id}")
    return new


def _current_or_error(db: Session, old: k.KnowledgeItem, old_id) -> None:
    if old.status != "CURRENT":
        current = db.scalar(select(k.KnowledgeItem).where(k.KnowledgeItem.series_id == old.series_id,
                                                          k.KnowledgeItem.status == "CURRENT"))
        hint = f" La versione vigente è la voce {current.id}." if current else ""
        raise ConoscenzaError(f"La voce {old_id} non è vigente ({STATUS_LABELS[old.status]}).{hint}")


def supersede(db: Session, who: Principal, old_id: int, raw: dict) -> dict:
    """Replace the CURRENT entry `old_id` with a new version of the same series."""
    old = db.get(k.KnowledgeItem, int(old_id))
    if old is None or not who.can("READ", old.domain):
        raise ConoscenzaError(f"Voce {old_id} inesistente.")
    data = _normalize(db, _merged_from(db, old, raw), who=who, salt=f"supersedes:{old.id}")
    retry = db.scalar(select(k.KnowledgeItem).where(k.KnowledgeItem.request_key == data["request_key"]))
    if retry is not None:
        _log(db, who, "SUPERSEDE", session_ref=data["session_ref"], ids=[retry.id], outcome="DUPLICATE")
        db.commit()
        return {"esito": "GIA_REGISTRATO", "item": read_item(db, retry.id)}
    _current_or_error(db, old, old_id)
    if old.authority == "PO_EXPLICIT" and data["authority"] != "PO_EXPLICIT":
        raise ConoscenzaError("Una decisione esplicita di Pino può essere sostituita solo da un'altra "
                              "decisione esplicita di Pino; registrare l'ipotesi o la proposta come voce separata.")
    new = _replace(db, who, old, data, "SUPERSEDE")
    db.commit()
    return {"esito": "SOSTITUITA", "item": read_item(db, new.id)}


def approve(db: Session, who: Principal, proposal_id: int, note: str | None = None,
            session_ref: str | None = None) -> dict:
    """The owner approves a PROPOSAL: a new PO_EXPLICIT version is created,
    still attributed to the proposer as contributor; the proposal is kept."""
    if not who.is_owner:
        raise ConoscenzaError("Solo Pino può approvare una proposta in questo rilascio.")
    proposal = db.get(k.KnowledgeItem, int(proposal_id))
    if proposal is None:
        raise ConoscenzaError(f"Voce {proposal_id} inesistente.")
    done = db.scalar(select(k.KnowledgeApproval).where(k.KnowledgeApproval.proposal_item_id == proposal.id))
    if done:
        _log(db, who, "APPROVE", session_ref=session_ref, ids=[proposal.id, done.approved_item_id],
             outcome="DUPLICATE")
        db.commit()
        return {"esito": "GIA_REGISTRATO", "item": read_item(db, done.approved_item_id)}
    if proposal.authority != "PROPOSAL":
        raise ConoscenzaError(f"La voce {proposal_id} non è una proposta.")
    _current_or_error(db, proposal, proposal_id)
    raw = _merged_from(db, proposal, {"authority": "PO_EXPLICIT", "session_ref": session_ref})
    data = _normalize(db, raw, who=who, salt=f"approves:{proposal.id}")
    data["contributed_by_person_id"] = proposal.contributed_by_person_id
    new = _replace(db, who, proposal, data, "APPROVE")
    db.add(k.KnowledgeApproval(proposal_item_id=proposal.id, approved_item_id=new.id,
                               approved_by_person_id=who.person_id, via_client=who.client, note=_clean(note),
                               approved_at=utcnow()))
    db.commit()
    return {"esito": "APPROVATA", "item": read_item(db, new.id)}


def link(db: Session, who: Principal, from_id: int, to_id: int, relation: str, note: str | None = None,
         session_ref: str | None = None) -> dict:
    relation = _choice(relation, k.LINK_RELATIONS, "Relazione")
    a, b = db.get(k.KnowledgeItem, int(from_id)), db.get(k.KnowledgeItem, int(to_id))
    if not a or not b or not who.can("CONTRIBUTE", a.domain) or not who.can("READ", b.domain):
        raise ConoscenzaError("Voce da collegare inesistente o non accessibile.")
    exists = db.scalar(select(k.KnowledgeLink).where(k.KnowledgeLink.from_series_id == a.series_id,
                                                     k.KnowledgeLink.to_series_id == b.series_id,
                                                     k.KnowledgeLink.relation == relation))
    if not exists:
        db.add(k.KnowledgeLink(from_series_id=a.series_id, to_series_id=b.series_id, relation=relation,
                               note=_clean(note), recorded_by=who.client, recorded_at=utcnow()))
    _log(db, who, "LINK", session_ref=session_ref, ids=[a.id, b.id], outcome="DUPLICATE" if exists else "OK")
    db.commit()
    return {"esito": "GIA_REGISTRATO" if exists else "COLLEGATE", "da": a.id, "a": b.id, "relazione": relation}


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _people(db: Session) -> dict[int, str]:
    return {p.id: p.name for p in db.scalars(select(k.KnowledgePerson))}


def _summary(item: k.KnowledgeItem, people: dict[int, str]) -> dict:
    out = {
        "id": item.id, "serie": item.series_id, "versione": item.version,
        "stato": STATUS_LABELS[item.status], "tipo": KIND_LABELS[item.kind],
        "autorita": AUTHORITY_LABELS[item.authority], "dominio": item.domain, "titolo": item.title,
        "contenuto": item.statement,
        "motivazione": item.rationale or "MOTIVAZIONE SCONOSCIUTA",
        "condizioni_di_validita": item.validity_conditions, "eccezioni": item.exceptions,
        "fornito_da": people.get(item.contributed_by_person_id, UNKNOWN),
        "registrato_tramite": item.recorded_by,
        "deciso_o_approvato_da": (people.get(item.decided_by_person_id) or item.decided_by
                                  if item.kind != "WORK_UPDATE" and item.authority == "PO_EXPLICIT" else None),
        "data_decisione": item.decided_on.isoformat() if item.decided_on else None,
        "registrato_il": item.recorded_at.isoformat(),
        "fonte": f"{item.source_type}: {item.source_ref}",
    }
    if item.kind == "WORK_UPDATE":
        out["lavoro"] = item.work_ref
        out["stadio"] = STAGE_LABELS[item.work_stage]
    return {key: value for key, value in out.items() if value is not None}


def read_item(db: Session, item_id: int) -> dict:
    item = db.get(k.KnowledgeItem, int(item_id))
    if item is None:
        raise ConoscenzaError(f"Voce {item_id} inesistente.")
    people = _people(db)
    out = _summary(item, people)
    out["parole_chiave"] = item.keywords
    out["estratto_fonte"] = item.source_excerpt
    out["sessione"] = item.session_ref
    out["evidenze"] = [{"tipo": e.kind, "riferimento": e.reference, "descrizione": e.description}
                       for e in db.scalars(select(k.KnowledgeEvidence).where(k.KnowledgeEvidence.item_id == item.id))]
    versions = db.scalars(select(k.KnowledgeItem).where(k.KnowledgeItem.series_id == item.series_id)
                          .order_by(k.KnowledgeItem.version)).all()
    out["versioni"] = [{"id": v.id, "versione": v.version, "stato": STATUS_LABELS[v.status],
                        "autorita": AUTHORITY_LABELS[v.authority], "titolo": v.title,
                        "fornito_da": people.get(v.contributed_by_person_id, UNKNOWN),
                        "registrato_il": v.recorded_at.isoformat()} for v in versions]
    approvals = db.scalars(select(k.KnowledgeApproval).where(or_(
        k.KnowledgeApproval.proposal_item_id.in_([v.id for v in versions]),
        k.KnowledgeApproval.approved_item_id.in_([v.id for v in versions])))).all()
    out["approvazioni"] = [{"proposta": a.proposal_item_id, "approvata_come": a.approved_item_id,
                            "approvata_da": people.get(a.approved_by_person_id), "tramite": a.via_client,
                            "il": a.approved_at.isoformat(), "nota": a.note} for a in approvals]
    links = db.scalars(select(k.KnowledgeLink).where(or_(k.KnowledgeLink.from_series_id == item.series_id,
                                                         k.KnowledgeLink.to_series_id == item.series_id))).all()
    out["collegamenti"] = []
    for ln in links:
        other = ln.to_series_id if ln.from_series_id == item.series_id else ln.from_series_id
        current = db.scalar(select(k.KnowledgeItem).where(k.KnowledgeItem.series_id == other)
                            .order_by(k.KnowledgeItem.version.desc()))
        direction = "modifica" if ln.from_series_id == item.series_id else "è modificata da"
        if ln.relation == "RELATES":
            direction = "correlata a"
        out["collegamenti"].append({"relazione": direction, "voce": current.id if current else other,
                                    "titolo": current.title if current else None, "nota": ln.note})
    return {key: value for key, value in out.items() if value not in (None, [])}


def read(db: Session, who: Principal, item_id: int, session_ref: str | None = None) -> dict:
    item = db.get(k.KnowledgeItem, int(item_id))
    if item is None or not who.can("READ", item.domain):
        raise ConoscenzaError(f"Voce {item_id} inesistente.")
    out = read_item(db, item_id)
    _log(db, who, "READ", session_ref=session_ref, ids=[int(item_id)])
    db.commit()
    return out


def search(db: Session, who: Principal, query: str, *, session_ref: str | None = None, domain: str | None = None,
           kind: str | None = None, include_history: bool = False, limit: int = 8) -> dict:
    stmt = select(k.KnowledgeItem)
    if not include_history:
        stmt = stmt.where(k.KnowledgeItem.status == "CURRENT")
    if domain:
        stmt = stmt.where(func.lower(k.KnowledgeItem.domain).contains(domain.strip().lower()))
    if kind:
        stmt = stmt.where(k.KnowledgeItem.kind == _choice(kind, k.KINDS, "Tipo"))
    items = who.readable(db.scalars(stmt).all())
    ranked = rank(items, query, limit=max(1, min(int(limit), 25)))
    people = _people(db)
    results = []
    for r in ranked:
        entry = _summary(r.item, people)
        entry["pertinenza"] = r.score
        amended_by = db.scalars(select(k.KnowledgeLink).where(k.KnowledgeLink.to_series_id == r.item.series_id,
                                                               k.KnowledgeLink.relation == "AMENDS")).all()
        if amended_by:
            entry["attenzione"] = ("Modificata in parte dalle voci (serie) "
                                   + ", ".join(str(a.from_series_id) for a in amended_by) + ": leggerle.")
        results.append(entry)
    _log(db, who, "SEARCH", session_ref=session_ref, query=query, ids=[r.item.id for r in ranked],
         detail=f"{len(results)} risultati su {len(items)} voci")
    db.commit()
    return {"domanda": query, "voci_esaminate": len(items), "risultati": results,
            "nota": ("Nessuna voce pertinente: riformulare con altre parole o consultare il contesto."
                     if not results else "Applicare le voci vigenti; una 'Ipotesi dell'AI' o una 'Proposta' "
                                         "non è una decisione.")}


def brief(db: Session, who: Principal, *, session_ref: str | None = None, domain: str | None = None,
          limit: int = 40) -> dict:
    """Start-of-session context: register state, the most recent CURRENT
    decisions and corrections (titles), and the latest work updates."""
    base = select(k.KnowledgeItem).where(k.KnowledgeItem.status == "CURRENT")
    if domain:
        base = base.where(func.lower(k.KnowledgeItem.domain).contains(domain.strip().lower()))
    rules = who.readable(db.scalars(base.where(k.KnowledgeItem.kind != "WORK_UPDATE")
                                    .order_by(k.KnowledgeItem.decided_on.desc().nullslast(),
                                              k.KnowledgeItem.id.desc())).all())[:limit]
    work = who.readable(db.scalars(base.where(k.KnowledgeItem.kind == "WORK_UPDATE")
                                   .order_by(k.KnowledgeItem.recorded_at.desc())).all())[:15]
    readable = who.readable(db.scalars(select(k.KnowledgeItem)).all())
    out = {
        "registro": "raggiungibile",
        "utente": f"{who.person_name or UNKNOWN} tramite {who.client}",
        "voci_vigenti": sum(1 for i in readable if i.status == "CURRENT"),
        "voci_sostituite": sum(1 for i in readable if i.status == "SUPERSEDED"),
        "decisioni_e_correzioni_recenti": [
            f"[{i.id}] {i.decided_on or '-'} · {i.domain} · {i.title}"
            + {"AI_HYPOTHESIS": " (ipotesi AI)", "PROPOSAL": " (proposta)"}.get(i.authority, "")
            + (" (motivazione sconosciuta)" if i.rationale_status == "UNKNOWN" else "") for i in rules],
        "stato_lavori": [f"[{i.id}] {i.recorded_at:%Y-%m-%d} · {i.work_ref} · {STAGE_LABELS[i.work_stage]} · "
                         f"{i.title}" for i in work],
    }
    _log(db, who, "BRIEF", session_ref=session_ref, query=domain, ids=[i.id for i in rules + work])
    db.commit()
    return out


def access_log(db: Session, who: Principal, *, session_ref: str | None = None, client: str | None = None,
               limit: int = 50):
    if not who.is_owner:
        raise ConoscenzaError("Lo storico delle consultazioni è riservato a Pino.")
    people = _people(db)
    stmt = select(k.KnowledgeAccess).order_by(k.KnowledgeAccess.id.desc()).limit(limit)
    if session_ref:
        stmt = stmt.where(k.KnowledgeAccess.session_ref == session_ref)
    if client:
        stmt = stmt.where(k.KnowledgeAccess.client == client.upper())
    return [{"id": a.id, "persona": people.get(a.person_id, UNKNOWN), "strumento": a.client,
             "sessione": a.session_ref, "operazione": a.operation, "domanda": a.query, "voci": a.result_item_ids,
             "esito": a.outcome, "dettaglio": a.detail, "quando": a.occurred_at.isoformat()}
            for a in reversed(db.scalars(stmt).all())]
