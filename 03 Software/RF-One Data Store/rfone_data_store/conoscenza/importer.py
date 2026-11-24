"""Initial heritage import for Conoscenza (first release).

Sources, all inside the authorized RF One folder:

- `Decisioni RF1.md` — the shared decision register. Each `## date | title`
  section is a Product Owner decision; its `### Esito …` subsections are
  work outcomes (RELEASED when they record a deploy/release, otherwise
  VERIFIED), with the section itself as evidence.
- `CLAUDE.md` — dated standing Product Owner instructions (sections that
  carry a date and name the Product Owner).
- any JSONL extract (`import-extract`), one record per line, for
  conversations or excerpts the other AIs make available. Each record keeps
  its own `source_ref`; `source_type` defaults to IMPORTED_EXTRACT.

Every import is idempotent: the request key is derived from the source
section, so running it again adds nothing. A section whose source
reference is already registered (for instance recorded live by a session)
is skipped, not duplicated.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from sqlalchemy import select

from . import models as k
from .api import Conoscenza
from .store import REPO_ROOT

DATE = re.compile(r"(20\d\d-\d\d-\d\d)")
LOG_HEADING = re.compile(r"^## (20\d\d-\d\d-\d\d) \| (.+?)\s*$")
SUB_HEADING = re.compile(r"^### (.+?)\s*$")
BULLET = re.compile(r"^- ([^:]{2,60}):\s*(.+)$")


def _key(source_ref: str) -> str:
    return "import:" + hashlib.sha256(source_ref.encode("utf-8")).hexdigest()[:40]


def _domain_for(text: str) -> str:
    t = text.lower()
    for needle, domain in (("conoscenza", "System/Conoscenza"), ("tips", "Restaurant/Tips"),
                           ("wines", "Restaurant/Wines"), ("registry", "Restaurant/Registry"),
                           ("clover", "Restaurant/Clover Acquisition"), ("bank", "Administration/Bank Reconciliation"),
                           ("how works", "System/Shared UI"), ("help", "System/Shared UI"), ("ui", "System/Shared UI"),
                           ("database", "System/Local Environment"), ("sign-in", "System/Local Environment"),
                           ("preview", "System/Local Environment"), ("registro", "System/Governance"),
                           ("accesso ai file", "System/Governance"), ("filesystem", "System/Governance")):
        if re.search(r"\b" + re.escape(needle) + r"\b", t):
            return domain
    return "System/Governance"


def _sections(lines: list[str], heading: re.Pattern):
    current, body = None, []
    for line in lines:
        m = heading.match(line)
        if m:
            if current:
                yield current, body
            current, body = m, []
        elif current:
            body.append(line)
    if current:
        yield current, body


def parse_decision_log(path: Path) -> tuple[list[dict], list[tuple[str, str, str]]]:
    """Records and (from_ref, to_title, relation) link hints."""
    records, links = [], []
    lines = path.read_text(encoding="utf-8").splitlines()
    name = path.name
    for m, body in _sections(lines, LOG_HEADING):
        day, title = m.group(1), m.group(2)
        ref = f"{name}#{day} | {title}"
        main, subs, sub = [], [], None
        for line in body:
            sm = SUB_HEADING.match(line)
            if sm:
                sub = [sm.group(1), []]
                subs.append(sub)
            elif sub is not None:
                sub[1].append(line)
            else:
                main.append(line)
        fields: dict[str, list[str]] = {}
        free = []
        for line in main:
            bm = BULLET.match(line.strip())
            if bm:
                fields.setdefault(bm.group(1).strip().lower(), []).append(bm.group(2).strip())
            elif line.strip():
                free.append(line.strip())
        decisions = [v for key, vals in fields.items() if key.startswith("decisione") for v in vals]
        rationale = [v for key, vals in fields.items() if key.startswith("motiv") for v in vals]
        opens = [v for key, vals in fields.items() if key.startswith("punt") for v in vals]
        relations = [v for key, vals in fields.items() if key.startswith("relazione") for v in vals]
        other = [f"{key.capitalize()}: {v}" for key, vals in fields.items()
                 if not key.startswith(("decisione", "motiv", "punt", "relazione")) for v in vals]
        statement = "\n".join(decisions + other + free) or title
        if opens:
            statement += "\nPunti aperti: " + " ".join(opens)
        excerpt = "\n".join(main).strip()
        records.append(dict(
            kind="CORRECTION" if relations else "DECISION", authority="PO_EXPLICIT", decided_by="Pino",
            decided_on=day, domain=_domain_for(title + " " + statement), title=title, statement=statement,
            rationale=" ".join(rationale) or None,
            exceptions=" ".join(relations) or None, source_type="DECISION_LOG", source_ref=ref,
            source_excerpt=excerpt, request_key=_key(ref)))
        for rel in relations:
            for quoted in re.findall(r"[\"«“]([^\"»”]{6,120})[\"»”]", rel):
                links.append((ref, quoted, "AMENDS"))
        if "sostituisce quella indicata all'avvio" in excerpt:
            links.append((ref, "Condivisione delle decisioni", "AMENDS"))
        for sub_title, sub_body in subs:
            sub_text = "\n".join(sub_body).strip()
            sub_ref = f"{ref} / {sub_title}"
            released = bool(re.search(r"rilascio|deploy|pubblicazione", sub_title, re.I))
            sub_day = (DATE.search(sub_title) or DATE.search(day)).group(1)
            records.append(dict(
                kind="WORK_UPDATE", authority="PO_EXPLICIT", decided_by="Pino", decided_on=sub_day,
                domain=_domain_for(title), title=f"{title} — {sub_title}", statement=sub_text or sub_title,
                rationale=None, work_ref=title, work_stage="RELEASED" if released else "VERIFIED",
                evidence=[{"kind": "RELEASE" if released else "TEST", "reference": sub_ref,
                           "description": "Esito documentato nel registro decisioni"}],
                source_type="DECISION_LOG", source_ref=sub_ref, request_key=_key(sub_ref)))
    return records, links


def parse_standing_instructions(path: Path) -> list[dict]:
    records = []
    lines = path.read_text(encoding="utf-8").splitlines()
    heading = re.compile(r"^#{1,2} (.+?)\s*$")
    for m, body in _sections(lines, heading):
        title = m.group(1)
        text = "\n".join(body).strip()
        probe = title + "\n" + text[:1500]
        day = DATE.search(probe)
        if not day or not re.search(r"Product Owner|Pino|user policy|User-provided", probe):
            continue
        verbatim = re.findall(r"(?:Verbatim[^:]*:|verbatim:)\s*(.+)", text)
        ref = f"{path.name}#{title}"
        records.append(dict(
            kind="DECISION", authority="PO_EXPLICIT", decided_by="Pino", decided_on=day.group(1),
            domain=_domain_for(title), title=title, statement=text[:6000],
            rationale=None, source_type="REPOSITORY_DOC", source_ref=ref,
            source_excerpt=" ".join(verbatim) or None, request_key=_key(ref)))
    return records


def _already_registered(api: Conoscenza, source_ref: str, own_key: str) -> bool:
    """True when a session already registered this source section live —
    same reference, or a reference naming the same section title."""
    section_title = source_ref.split("#", 1)[-1].split(" | ", 1)[-1].strip().lower()
    with api._session() as db:
        rows = db.scalars(select(k.KnowledgeItem).where(k.KnowledgeItem.request_key != own_key)).all()
        return any(r.source_ref == source_ref
                   or (len(section_title) > 12 and section_title in r.source_ref.lower()
                       and not r.request_key.startswith("import:"))
                   for r in rows)


def import_records(api: Conoscenza, records: list[dict]) -> dict:
    created, existing, skipped, failed = [], [], [], []
    for rec in records:
        # A section that says it is already in Conoscenza ("Registrata in Conoscenza come voce N") is not re-imported.
        if re.search(r"Registrat[ao] in Conoscenza come voce \d+", rec.get("source_excerpt") or "") or                 _already_registered(api, rec["source_ref"], rec["request_key"]):
            skipped.append(rec["source_ref"])
            continue
        out = api.record(**rec)
        if not out.get("ok"):
            failed.append({"fonte": rec["source_ref"], "errore": out.get("errore")})
        elif out["esito"] == "REGISTRATO":
            created.append(out["item"]["id"])
        else:
            existing.append(out["item"]["id"])
    return {"nuove": len(created), "gia_presenti": len(existing), "saltate_gia_registrate_da_altri": skipped,
            "fallite": failed, "ids": created}


def import_heritage(api: Conoscenza, repo_root: Path = REPO_ROOT) -> dict:
    log_records, link_hints = parse_decision_log(repo_root / "Decisioni RF1.md")
    standing = parse_standing_instructions(repo_root / "CLAUDE.md")
    report = {"Decisioni RF1.md": import_records(api, log_records), "CLAUDE.md": import_records(api, standing)}
    linked = []
    with api._session() as db:
        items = db.scalars(select(k.KnowledgeItem).where(k.KnowledgeItem.status == "CURRENT")).all()
        by_ref = {i.source_ref: i.id for i in items}
        by_title = {i.title.lower(): i.id for i in items if i.kind != "WORK_UPDATE"}
    for from_ref, to_title, relation in link_hints:
        from_id = by_ref.get(from_ref)
        to_id = next((i for t, i in by_title.items() if to_title.lower() in t), None)
        if from_id and to_id and from_id != to_id:
            out = api.link(from_id, to_id, relation, note="Relazione dichiarata nel registro decisioni")
            linked.append({"da": from_id, "a": to_id, "esito": out.get("esito") or out.get("errore")})
    report["collegamenti"] = linked
    return report


def import_extract(api: Conoscenza, path: Path) -> dict:
    records = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        rec = json.loads(line)
        rec.setdefault("source_type", "IMPORTED_EXTRACT")
        if not rec.get("source_ref"):
            raise ValueError(f"Riga {n}: source_ref obbligatorio (fonte della conversazione o dell'estratto).")
        rec.setdefault("request_key", _key(f"{rec['source_ref']}|{rec.get('title', '')}"))
        records.append(rec)
    return import_records(api, records)
