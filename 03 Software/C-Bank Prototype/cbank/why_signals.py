"""WHY signals and WHO WHY rule simulation (BANK_WHO_WHY_MODE_001), read-only.

`signals` evaluates every movement with the one engine and groups the movements whose WHO is recognised but
whose WHY is not determinable, by WHO, Source and reason (pair missing, rule missing, document or
clarification missing, rules in conflict), with the action that resolves each group.
`simulate` shows what a draft WHO WHY rule would change before it is saved or activated: the engine is
evaluated on the WHO's movements without and with the draft. Nothing is written anywhere.
"""
from __future__ import annotations

from types import SimpleNamespace

from .legacy import who_why_rules as wr

# BANK_WHO_WHY_CONFIG_001: a WHY missing for a recognised WHO is set in the WHO's one configuration (WHY page, Edit).
ACTIONS = {wr.NEEDS_PAIR: "CONFIGURE_WHO", wr.NEEDS_RULE: "DEFINE_RULE", wr.NEEDS_DOCUMENT: "PROVIDE_DOCUMENT",
           wr.CONFLICT: "REVIEW_RULES", wr.SPLIT_INCOMPLETE: "OPEN_SPLIT"}


def _decided(r):
    """The WHY outcome of a result: its WHY, or SPLIT for a complete split (BANK_SPLIT_ALLOCATION_001)."""
    return r["why_id"] or ("SPLIT" if (r.get("split") or {}).get("complete") else None)


def _movement(engine, txn, r) -> dict:
    return dict(id=txn.id, date=str(txn.posting_date or ""), description=txn.description_original or "",
                amount_minor=txn.amount_minor, why=r.get("why"), status=r.get("status"),
                detail=next((x.get("message") for x in r["exceptions"] if x["code"] in wr.OPEN_REASONS), None))


def signals(engine) -> dict:
    groups, counts = {}, dict.fromkeys(wr.OPEN_REASONS, 0)
    for txn in engine.txns:
        r = engine.evaluate(txn)
        open_ = [x for x in r["exceptions"] if x["code"] in wr.OPEN_REASONS]
        if not open_ or not r.get("who_id"):
            continue
        code = open_[0]["code"]
        counts[code] += 1
        key = (r["who_id"], txn.payment_instrument_id, code)
        g = groups.get(key)
        if g is None:
            source = engine.c.instruments.get(txn.payment_instrument_id)
            owner = engine.owner(txn)
            g = groups[key] = dict(who_id=r["who_id"], who=r["who_name"], source_id=txn.payment_instrument_id,
                                   source=source.display_name if source else None, owner=owner.name if owner else None,
                                   owner_kind=owner.entity_type if owner else None, reason=code, label=wr.LABELS[code],
                                   action=ACTIONS[code], mode=engine.why_resolver.mode(r["who_id"]), movements=[],
                                   missing=set())
        g["movements"].append(_movement(engine, txn, r))
        g["missing"].update(open_[0].get("missing") or [])
    out = []
    for g in groups.values():
        g["count"] = len(g["movements"])
        g["total_minor"] = sum(mv["amount_minor"] for mv in g["movements"])
        g["missing"] = sorted(g["missing"])
        out.append(g)
    out.sort(key=lambda g: (-g["count"], g["who"] or "", g["source"] or ""))
    return dict(groups=out, counts=counts, movements=sum(counts.values()))


def simulate(engine, spec: dict) -> dict:
    """What the draft rule changes on the movements of its WHOs (the draft counts as active)."""
    spec = wr.validate(engine.db, dict(spec, scope=wr.SCOPE))
    who_ids = set(spec["who_ids"])
    resolver = engine.why_resolver
    before = {}
    for txn in engine.txns:
        r = engine.evaluate(txn)
        if r.get("who_id") in who_ids:
            before[txn.id] = r
    draft = (SimpleNamespace(id="draft"), SimpleNamespace(version_no=0), spec)
    saved = {w: list(resolver.by_who.get(w, [])) for w in who_ids}
    try:
        for w in who_ids:
            resolver.by_who.setdefault(w, []).append(draft)
        rows, summary = [], dict(new_why=0, changed_why=0, unchanged=0, still_open=0, protected=0)
        for tid, old in before.items():
            txn = engine.by_id[tid]
            new = engine.evaluate(txn)
            info = resolver.info_builder.info(txn, who=new.get("who_name"), row=engine.c.rule_row(txn))
            outcome, why_id, missing, detail = resolver.evaluate_rule(spec, txn, info)
            if new.get("protected"):
                effect = "protected"
            elif _decided(new) and not _decided(old):
                effect = "new_why"
            elif _decided(new) and _decided(new) != _decided(old):
                effect = "changed_why"
            elif not _decided(new):
                effect = "still_open"
            else:
                effect = "unchanged"
            summary[effect] += 1
            open_ = next((x for x in new["exceptions"] if x["code"] in wr.OPEN_REASONS), None)
            rows.append(dict(_movement(engine, txn, new), source=new.get("source"), rule=outcome, effect=effect,
                             before=old.get("why"), after=new.get("why"), mode=new.get("why_mode"),
                             open_label=open_["label"] if open_ else None, missing=missing,
                             rule_detail=detail or (engine._why_name(why_id) if why_id else "")))
    finally:
        for w, entries in saved.items():
            resolver.by_who[w] = entries
    rows.sort(key=lambda x: (x["effect"] != "new_why", x["effect"] != "changed_why", x["date"]))
    return dict(rows=rows, summary=summary, movements=len(rows),
                text=wr.describe(spec, engine.c.whys, engine.c.whos))


def simulate_config(engine, draft: dict) -> dict:
    """BANK_WHO_WHY_CONFIG_001: what a draft WHO configuration (single WHY, Personal/Company WHY or From rule, and its
    company exceptions) changes on the movements of that WHO, before it is saved. Same evaluation and summary as
    `simulate`; WHOM before/after is shown because an exception may attribute it explicitly. Nothing is written."""
    from rfone_data_store.bank_reconciliation import who_why_config as wc   # path set by .legacy
    spec = wc.validate(engine.db, draft)
    who_id = spec["who_id"]
    resolver = engine.why_resolver
    before = {txn.id: r for txn in engine.txns for r in [engine.evaluate(txn)] if r.get("who_id") == who_id}
    rows, summary = [], dict(new_why=0, changed_why=0, unchanged=0, still_open=0, protected=0)
    with resolver.config_variant(who_id, spec):
        for tid, old in before.items():
            txn = engine.by_id[tid]
            new = engine.evaluate(txn)
            if new.get("protected"):
                effect = "protected"
            elif _decided(new) and not _decided(old):
                effect = "new_why"
            elif _decided(new) and (_decided(new) != _decided(old) or new.get("beneficiary_id") != old.get("beneficiary_id")):
                effect = "changed_why"
            elif not _decided(new):
                effect = "still_open"
            else:
                effect = "unchanged"
            summary[effect] += 1
            open_ = next((x for x in new["exceptions"] if x["code"] in wr.OPEN_REASONS), None)
            rows.append(dict(_movement(engine, txn, new), source=new.get("source"), owner=new.get("payer"),
                             effect=effect, before=old.get("why"), after=new.get("why"),
                             whom_before=old.get("beneficiary"), whom_after=new.get("beneficiary"),
                             method=new.get("why_method"), open_label=open_["label"] if open_ else None,
                             open_detail=open_["message"] if open_ else None))
    rows.sort(key=lambda x: (x["effect"] != "new_why", x["effect"] != "changed_why", x["date"]))
    return dict(rows=rows, summary=summary, movements=len(rows), spec=spec)


# ---------------------------------------------------------------- check after an upload (BANK_WHO_WHY_UPLOAD_CHECK_001)

CHECK_APPLICABLE, CHECK_MISSING = "APPLICABLE", "WHY_MISSING"
CHECK_COMPANIES, CHECK_SAME_OWNER, CHECK_INFO = "COMPANY_DIFFERENCES", "SAME_OWNER_DIFFERENCES", "INFORMATION_MISSING"
CHECK_ORDER = (CHECK_MISSING, CHECK_COMPANIES, CHECK_SAME_OWNER, CHECK_INFO)
CHECK_ACTION = {CHECK_MISSING: "CONFIG", CHECK_COMPANIES: "EXCEPTIONS", CHECK_SAME_OWNER: "RULE", CHECK_INFO: "INFO"}
MAX_CHECK_MOVEMENTS = 150


def _open_reason(r):
    return next((x for x in r["exceptions"] if x["code"] in wr.OPEN_REASONS), None)


def who_why_check(engine, scope_ids) -> dict:
    """BANK_WHO_WHY_UPLOAD_CHECK_001 (Product Owner, 2026-11-06): after an upload, which recognised WHO of the NEW
    movements (`scope_ids`) need a WHO -> WHY configuration or a disambiguation, judged on the whole history of each
    WHO and on the existing configurations — read-only, one issue per WHO (the first open question; the next one
    appears once it is solved):

      APPLICABLE              every new movement of the WHO gets its WHY (configuration, pair, rule or split): nothing
      WHY_MISSING             no WHY for the movement's owner (Personal / Company) and no conflicting evidence
      COMPANY_DIFFERENCES     companies carry different WHYs: one Company WHY cannot hold, company exceptions are proposed
      SAME_OWNER_DIFFERENCES  different WHYs for the same owner (Personal, or one company), MULTIPLE WHO without an
                              applicable rule, or rules in conflict: a disambiguation rule, with the movements
      INFORMATION_MISSING     owner of the account/card unknown at the date, document or split detail missing

    Evidence of WHYs = the former WHO + Source classifications and the WHYs confirmed by a person on the WHO's
    movements, per owner entity. A difference between cards is never turned into a rule here."""
    from rfone_data_store import models as m
    from rfone_data_store.bank_reconciliation import who_why_config as wc
    scope = set(scope_ids)
    results = {txn.id: engine.evaluate(txn) for txn in engine.txns}
    by_who = {}
    for txn in engine.txns:
        r = results[txn.id]
        if r.get("who_id"):
            by_who.setdefault(r["who_id"], []).append((txn, r))
    affected = sorted({results[t]["who_id"] for t in scope if t in results and results[t].get("who_id")})
    entities = engine.c.entities
    whys = {k: v.name for k, v in engine.c.whys.items()}
    analysis = wc.analyse_pairs(engine.db)

    def subject(entity_id):
        e = entities.get(entity_id)
        return None if e is None else ("PERSONAL" if e.entity_type == m.REPORTING_ENTITY_PERSONAL else "COMPANY")

    issues, applicable = [], 0
    for who_id in affected:
        rows = by_who.get(who_id, [])
        new = [(t, r) for t, r in rows if t.id in scope]
        open_new = [(t, r, _open_reason(r)) for t, r in new if _open_reason(r)]
        if not open_new:
            applicable += 1
            continue
        # evidence of WHYs per owner entity: former pairs + WHYs confirmed by a person
        evidence = {}
        for p in (analysis.get(who_id) or {}).get("pairs", []):
            if p["why_id"] and p["owner_id"]:
                evidence.setdefault(p["owner_id"], {}).setdefault(p["why_id"], set()).add(p["source"])
        for t, r in rows:
            if r.get("protected") and r.get("why_id") and r.get("payer_id"):
                evidence.setdefault(r["payer_id"], {}).setdefault(r["why_id"], set()).add(r.get("source"))
        personal = {w for e, ws in evidence.items() if subject(e) == "PERSONAL" for w in ws}
        companies = {e: ws for e, ws in evidence.items() if subject(e) == "COMPANY"}
        company_whys = {w for ws in companies.values() for w in ws}
        found, info = {}, []
        for t, r, x in open_new:
            owner = r.get("payer_id")
            if x["code"] in (wr.NEEDS_DOCUMENT, wr.SPLIT_INCOMPLETE):
                info.append(", ".join(x.get("missing") or []) or x.get("label") or x["code"])
            elif x["code"] in (wr.NEEDS_RULE, wr.CONFLICT):
                found.setdefault(CHECK_SAME_OWNER, []).append((t, r, x["code"]))
            elif owner is None:
                info.append(f"titolare del conto/carta «{r.get('source') or '—'}» sconosciuto al {t.posting_date}")
            elif subject(owner) == "PERSONAL":
                found.setdefault(CHECK_SAME_OWNER if len(personal) > 1 else CHECK_MISSING, []).append((t, r, "PERSONAL"))
            elif len(companies.get(owner, {})) > 1:
                found.setdefault(CHECK_SAME_OWNER, []).append((t, r, owner))
            elif len(company_whys) > 1:
                found.setdefault(CHECK_COMPANIES, []).append((t, r, owner))
            else:
                found.setdefault(CHECK_MISSING, []).append((t, r, "COMPANY"))
        if info:
            found[CHECK_INFO] = info
        case = next(c for c in CHECK_ORDER if c in found)
        who = rows[0][1]["who_name"]
        open_all = sum(1 for _t, r in rows if _open_reason(r))
        issue = dict(who_id=who_id, who=who, case=case, action=CHECK_ACTION[case], count=open_all,
                     count_new=len(open_new), other_cases=[c for c in CHECK_ORDER if c in found and c != case])
        if case == CHECK_MISSING:
            subjects = [k for k in ("PERSONAL", "COMPANY") if k in {k for _t, _r, k in found[case]}]
            label = " e ".join({"PERSONAL": "personale", "COMPANY": "aziendale"}[s] for s in subjects)
            issue["reason"] = f"Manca il WHY {label} del WHO: nessuna configurazione lo determina."
        elif case == CHECK_COMPANIES:
            issue["differences"] = [dict(owner=entities[e].name if e in entities else f"#{e}",
                                         whys=[whys.get(w, f"#{w}") for w in ws],
                                         sources=sorted({s for v in ws.values() for s in v if s}))
                                    for e, ws in sorted(companies.items(), key=lambda kv: entities[kv[0]].name if kv[0] in entities else "")]
            issue["reason"] = ("WHY diversi tra aziende: " + "; ".join(
                f"{d['owner']} → {', '.join(d['whys'])}" for d in issue["differences"])
                + ". Un solo WHY aziendale non basta: gestisci le eccezioni per azienda.")
        elif case == CHECK_SAME_OWNER:
            keys = {k for _t, _r, k in found[case]}
            if keys & {wr.NEEDS_RULE}:
                issue["reason"] = "Il WHY di questo WHO dipende dal movimento (Da regola) e nessuna regola attiva lo determina."
            elif keys & {wr.CONFLICT}:
                issue["reason"] = "Regole in conflitto: indicano WHY diversi per gli stessi movimenti."
            else:
                names = ["Personale" if k == "PERSONAL" else (entities[k].name if k in entities else f"#{k}") for k in keys]
                diffs = [(n, sorted(whys.get(w, f"#{w}") for w in (personal if k == "PERSONAL" else companies.get(k, {}))))
                         for n, k in zip(names, keys)]
                issue["reason"] = ("WHY diversi per lo stesso titolare: " + "; ".join(f"{n} → {', '.join(ws)}" for n, ws in diffs)
                                   + ". Serve una regola di disambiguazione: la sola differenza tra carte non basta.")
            owners = {r.get("payer_id") for _t, r, _k in found[case]}
            personal_ids = {e for e in entities if subject(e) == "PERSONAL"}
            if "PERSONAL" in keys:
                owners |= personal_ids
            relevant = [(t, r) for t, r in rows if r.get("payer_id") in owners or t.id in scope]
            relevant.sort(key=lambda tr: (not _open_reason(tr[1]), str(tr[0].posting_date)), reverse=False)
            issue["movements"] = [dict(id=t.id, date=str(t.posting_date or ""), description=t.description_original or "",
                                       amount_minor=t.amount_minor, source=r.get("source"), owner=r.get("payer"),
                                       why=r.get("why"), open=bool(_open_reason(r)), new=t.id in scope)
                                  for t, r in relevant[:MAX_CHECK_MOVEMENTS]]
            issue["movements_total"] = len(relevant)
        else:
            missing = sorted(set(found[CHECK_INFO]))
            issue["reason"] = "Informazioni insufficienti: " + "; ".join(missing[:4]) + ("…" if len(missing) > 4 else "") + "."
            issue["link"] = ("/bank/sources" if any(s.startswith("titolare") for s in missing) else
                             "/bank/amazon" if any("Amazon" in s for s in missing) else f"/bank/split?who={who_id}")
        issues.append(issue)
    issues.sort(key=lambda i: (CHECK_ORDER.index(i["case"]), -i["count_new"], i["who"] or ""))
    return dict(issues=issues, affected=len(affected), applicable=applicable, scope=len(scope),
                scope_recognised=sum(1 for t in scope if t in results and results[t].get("who_id")))
