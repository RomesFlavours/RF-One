"""Internet research inside "Start automatic reconciliation" (BANK_UPLOAD_AND_RECONCILE_001, 2026-11-03).

The third stage of C-Bank's recognition (`cbank/three_stages.py`: Rules -> WHO text -> internet) runs on the
movements the engine left open, with everything it already has — the one ChatGPT adapter (`legacy.generate_json`
-> `bank_chatgpt`, web search on), its prompt, and its validation, which never trusts the AI:

* WHO not recognised        -> researched; WHO_IDENTIFIED only when certain with a public source, GENERIC WHO
                                (never registered) only with a WHY the evidence supports, otherwise UNRESOLVED;
* WHO recognised, WHY open  -> researched with the WHO FIXED (only the WHY may come from the evidence);
* WHY rules in conflict, incomplete split, missing document, card payments, owners' relationships, personal
  Source with a business WHAT, catalog gaps -> NOT researched: they stay for a person, with their reason;
* WHAT always from the WHY; the dining policy (personal Source -> Owner Personal — Restaurant, company Source ->
  Business Meals & Entertainment, by the Source owner at the movement date) is the one of `three_stages`.

Analogous movements (same masked description pattern, direction, Source type, Source owner at the date, recognised
WHO, WHO mode and rule state) are researched ONCE, three per request (the recorded consent's limit), and the answer
is validated for each movement. Every answer is kept (`WORK_RESEARCH_ANSWER`) under the fingerprint of exactly what
was sent (the movement facts, the WHY catalog, the candidate and known WHOs, the instructions) and of the local
context that decides its use (`_context`: the Source owner at the date, the WHO mode, the applicable rules' state):
a resumed or repeated run never calls again for an answer it has, and never reuses one whose facts, catalog, owner or
rules changed — an answer given for a person's Source is never reused for a company's. The validation runs again each time with the current
rules, so an answer never outlives them. A provider error is recorded as such (not as "unresolved"), not cached,
and retried by the next run.

What is sent goes beyond the consent recorded on 2026-10-17 (date, direction, Source type and owner kind, and
web search), so the stage runs only with its own authorization (`consent`), asked for on the page with the exact
list below. Without it the stage does not run, and the page says so.

Results are proposals: nothing is written to the Bank decisions here.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from rfone_data_store import models as m

ANSWER, RESULTS = "WORK_RESEARCH_ANSWER", "WORK_RESEARCH"
CONSENT_KEY = "web_research"
SENT = ('descrizione bancaria con i numeri lunghi mascherati', 'data del movimento', 'direzione: entrata o uscita',
        'tipo di origine: conto bancario o carta', 'titolarità del conto o carta: azienda o persona',
        'WHO già riconosciuto oppure fino a sei nomi WHO candidati', 'catalogo WHY con nomi e relativo WHAT',
        'fino a tre movimenti per richiesta, usati da ChatGPT per la ricerca web')
NOT_SENT = 'importi, numeri di conto, nomi dei conti e delle carte e il resto del database restano sul PC'
# Open reasons a person settles: never researched (the AI never overrides rules or documents).
NOT_RESEARCHED = {"WHY_RULES_CONFLICT", "WHY_SPLIT_INCOMPLETE", "WHY_DOCUMENT_MISSING", "CARD_PAYMENT_UNMATCHED",
                  "CARD_PAYMENT_AMBIGUOUS", "RELATIONSHIP_TO_DECIDE", "PERSONAL_SOURCE_BUSINESS_WHAT",
                  "CATEGORY_MISSING"}
MAX_CONSECUTIVE_ERRORS = 3
PROVIDER_ERROR, NOT_AUTHORIZED, KEPT_FOR_PERSON = "PROVIDER_ERROR", "NOT_AUTHORIZED", "KEPT_FOR_PERSON"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- consent

def _consent_path() -> Path | None:
    url = os.environ.get("RFONE_DATABASE_URL", "")
    if not url.startswith("sqlite:///"):
        return None
    return Path(url[len("sqlite:///"):]).parent / "bank-chat-provider-consent.json"


def consent(app) -> dict | None:
    """The recorded authorization for the internet stage, or None."""
    if app.config.get("BANK_WEB_RESEARCH_APPROVED") is True:
        return dict(authorized_at="configured", authorized_by=None)
    path = _consent_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path else {}
    except (OSError, ValueError):
        return None
    granted = data.get(CONSENT_KEY)
    return granted if isinstance(granted, dict) and granted.get("allowed") is True else None


def record_consent(app, *, account_id: int, account_name: str) -> dict:
    """The person's explicit authorization, kept with the existing provider consent (local to this database)."""
    path = _consent_path()
    if path is None:
        raise ValueError("This environment keeps no local consent file: the authorization cannot be recorded here.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data[CONSENT_KEY] = dict(allowed=True, provider="OPENAI_CHATGPT_CODEX", authorized_at=_now(),
                             authorized_by=account_id, authorized_by_name=account_name,
                             scope="; ".join(SENT) + ". Not sent: " + NOT_SENT + ".")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data[CONSENT_KEY]


# ---------------------------------------------------------------- the stage

def _pattern(text: str) -> str:
    return " ".join(re.sub(r"[0-9#*]+", " ", (text or "").upper()).split())


def _fingerprint(three_stages, facts: dict, catalog: list, context: dict) -> str:
    """What an answer depends on. What was sent (the facts minus id and date, the WHY catalog, the known WHO names,
    the instructions) and the local context that decides how it is used: the Source owner at the movement date
    (company, never a person's answer for a company), the WHO mode and the state of the rules applicable to the
    WHO. Any change -> a new fingerprint -> the answer is not reused."""
    sent = {k: v for k, v in facts.items() if k not in ("id", "date")}
    raw = json.dumps(dict(i=three_stages.INSTRUCTIONS, f=sent, c=catalog, x=context), sort_keys=True,
                     ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _context(three_stages, sim, txn, cls: dict | None) -> dict:
    owner = sim.engine.owner(txn)
    return dict(owner_id=owner.id if owner else None, owner_kind=owner.entity_type if owner else None,
                known_whos=three_stages._known_whos(sim.engine, [txn.description_original or ""]),
                rules={k: (cls or {}).get(k) for k in ("why_mode", "who_source_pair", "why_open_reason", "why_missing")})


def cached_answers(db) -> dict:
    out = {}
    for a in db.scalars(select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind == ANSWER)
                        .order_by(m.BankFlowArtifact.id)):
        data = json.loads(a.payload)
        out[data["fingerprint"]] = data["item"]
    return out


def latest_results(db, engine_run_id: int | None = None) -> dict | None:
    for a in db.scalars(select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind == RESULTS)
                        .order_by(m.BankFlowArtifact.id.desc())):
        data = json.loads(a.payload)
        if engine_run_id is None or data.get("engine_run_id") == engine_run_id:
            return dict(data, id=a.id)
    return None


def _compact(r: dict) -> dict:
    keep = ("outcome", "who", "who_id", "catalog", "certainty", "why_id", "why", "why_basis", "what", "whom",
            "sources", "missing_information", "notes", "why_open_reason", "why_open_label", "nature", "who_kept")
    out = {k: r.get(k) for k in keep if r.get(k) not in (None, [], "")}
    if r.get("reasoning"):
        out["reasoning"] = r["reasoning"][:800]
    return out


def run_stage(app, SessionFactory, *, engine_run_id: int, window: tuple, progress, generate=None) -> dict:
    """Research the engine's open movements of the work period. Returns the counts; keeps answers and results."""
    import bank_guided_reconciliation as guided
    con = guided._cbank_app().config["CON"]          # first: puts the engine code on the path
    from cbank import legacy, service, three_stages
    generate = generate or legacy.generate_json
    authorized = consent(app) is not None
    with SessionFactory() as db:
        results = {r["txn_id"]: r for r in _engine_results(db, engine_run_id)}
        human = {t for (t,) in db.execute(select(m.FinancialTransaction.id).join(
            m.BankTransactionExplanation, m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id)
            .where(m.BankTransactionExplanation.decision_source == "HUMAN"))}
        cache = cached_answers(db)
    eng = service.new_engine(con)
    sim = three_stages.Simulation(eng)
    catalog = [dict(id=r.id, name=r.name, what=eng.c.class_label(r.accounting_classification_id))
               for r in eng.c.whys.values() if r.id not in eng.provisional]
    start, end = window
    out, groups = {}, defaultdict(list)
    for tid, r in results.items():
        day = (r.get("date") or "")[:10]
        if r["status"] != "EXCEPTION" or r.get("protected") or tid in human or not (start <= day <= end):
            continue
        if (r.get("match") or {}).get("state") in ("MATCHED", "WAITING", "AMBIGUOUS"):
            continue
        codes = {e["code"] for e in r.get("exceptions", [])}
        txn = eng.by_id.get(tid)
        if txn is None:
            continue
        if codes & NOT_RESEARCHED:
            out[tid] = dict(outcome=KEPT_FOR_PERSON, notes=[next(iter(codes & NOT_RESEARCHED))])
            continue
        hint = three_stages.recognise(sim, txn)
        cls = None
        if hint["resolved"]:
            who_id = sim.catalog_who(hint["who"])[0]
            cls = sim.classification(txn, who_id=who_id)
            if cls["why_id"] or cls["split_complete"]:
                continue
            if cls["why_open_reason"] in (legacy.who_why_rules.CONFLICT, legacy.who_why_rules.SPLIT_INCOMPLETE,
                                          legacy.who_why_rules.NEEDS_DOCUMENT):
                out[tid] = dict(outcome=KEPT_FOR_PERSON, who=hint["who"], who_id=who_id,
                                notes=[cls["why_open_label"] or cls["why_open_reason"]])
                continue
            hint = dict(hint, who_id=who_id)
        facts = sim.facts(txn, hint)
        context = _context(three_stages, sim, txn, cls)
        key = (_pattern(txn.description_original), facts["direction"], facts["source_type"],
               facts["source_owner_kind"], facts.get("recognised_who"), facts["dining_why_id"],
               json.dumps(context, sort_keys=True, default=str))
        groups[key].append((txn, hint, facts, context))
    reps = {key: members[0] for key, members in groups.items()}
    fps = {key: _fingerprint(three_stages, facts, catalog, context) for key, (_t, _h, facts, context) in reps.items()}
    to_ask = [key for key in reps if fps[key] not in cache]
    errors, errored, asked, last_error = 0, set(), 0, None
    if authorized and to_ask:
        batches = [to_ask[i:i + three_stages.GROUP_SIZE] for i in range(0, len(to_ask), three_stages.GROUP_SIZE)]
        for n, batch in enumerate(batches, 1):
            progress(step=f"Internet research: request {n} of {len(batches)} ({len(to_ask)} distinct descriptions)")
            if errors >= MAX_CONSECUTIVE_ERRORS:
                errored.update(batch)
                continue
            group = [(reps[k][0], reps[k][1]) for k in batch]
            try:
                answer = generate(sim.prompt(group), web_research=True)
                items = {i.get("id"): i for i in (answer or {}).get("movements", []) if isinstance(i, dict)}
                errors = 0
            except Exception as exc:  # noqa: BLE001 — a provider failure is recorded, never guessed
                errors += 1
                errored.update(batch)
                last_error = f"{type(exc).__name__}: {exc}"[:300]
                continue
            asked += 1
            with SessionFactory() as db:
                for k in batch:
                    item = items.get(reps[k][0].id)
                    if item is None:
                        errored.add(k)          # no answer for it: retried next time, never cached
                        continue
                    item = {x: y for x, y in item.items() if x != "id"}
                    cache[fps[k]] = item
                    db.add(m.BankFlowArtifact(kind=ANSWER, account_id=None, payload=json.dumps(dict(
                        fingerprint=fps[k], item=item, at=_now(), description_pattern=k[0]), ensure_ascii=False)))
                db.commit()
    for key, members in groups.items():
        item = cache.get(fps[key])
        for txn, hint, _facts, _context_ in members:
            if item is None:
                out[txn.id] = dict(outcome=PROVIDER_ERROR if key in errored else NOT_AUTHORIZED,
                                   who=hint.get("who") if hint.get("resolved") else None,
                                   who_id=hint.get("who_id"))
                continue
            item_for = dict(item, id=txn.id)
            validated = (sim.validate_known(txn, item_for, hint["who_id"]) if hint.get("resolved")
                         else sim.validate(txn, item_for))
            out[txn.id] = _compact(validated)
    counts = defaultdict(int)
    for r in out.values():
        counts[r["outcome"]] += 1
    data = dict(engine_run_id=engine_run_id, at=_now(), authorized=authorized, requests=asked,
                distinct=len(groups), reused=len(groups) - len(to_ask), counts=dict(counts),
                results={str(k): v for k, v in out.items()},
                error=last_error if errored else None)
    with SessionFactory() as db:
        db.add(m.BankFlowArtifact(kind=RESULTS, account_id=None, payload=json.dumps(data, ensure_ascii=False, default=str)))
        db.commit()
    return data


def _engine_results(db, run_id: int) -> list[dict]:
    from sqlalchemy import text
    return [json.loads(p) for (p,) in db.execute(text(
        "select payload_json from bank_engine_results where run_id = :r"), dict(r=run_id))]
