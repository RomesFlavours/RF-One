"""WHO Pattern Training (BANK_WHO_TRAINING_001): the person teaches, RF-One turns the examples into rules.

The person selects movements, gives their WHO (existing or new), highlights the part of the description
that is the WHO and marks the parts that vary. RF-One CODE (no AI) derives the WHO extraction rule those
examples imply — the text before the WHO is the anchor, the marked parts become {date}/{number}/{code},
the first element after the WHO ends it — tests it on the whole history and lists every movement it
intercepts, the person's examples apart from the additional ones. Wrong ones can be excluded: RF-One looks
for a literal that separates them. A rule becomes active only on the person's approval.

Examples marked "WHO needs external knowledge" or "single movement" are kept as identifications of that
movement only and never become a rule. Nothing here writes a WHO, WHY, WHAT or classification on a
movement; the examples are training data in their own record.
"""
import json
import re
from datetime import datetime, timezone

from flask import jsonify, render_template, request
from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import flow, rule_application_safety as safety

KIND = "WHO_TRAINING"


# ---------------------------------------------------------------------------
# Movements and the training record
# ---------------------------------------------------------------------------

def _movements(db):
    sources = {i.id: i.display_name for i in db.scalars(select(m.PaymentInstrument))}
    whos = {o.id: o.canonical_name for o in db.scalars(select(m.BankOccurrence))}
    out = []
    for t in db.scalars(select(m.FinancialTransaction)):
        ex = db.get(m.BankTransactionExplanation, t.explanation_id) if t.explanation_id else None
        out.append(dict(id=t.id, source=sources.get(t.payment_instrument_id) or "—", source_id=t.payment_instrument_id,
                        date=str(t.posting_date or t.transaction_date or ""), amount_minor=t.amount_minor or 0,
                        description=t.description_original or "",
                        human_who=whos.get(ex.occurrence_id) if ex is not None and ex.decision_source == "HUMAN" and ex.occurrence_id else None))
    out.sort(key=lambda r: (r["description"].strip().casefold(), r["date"], r["id"]))
    return out


def _approved(db):
    """{movement id: WHO} read by the approved WHO extraction rules, as the engine reads them."""
    known = [e for e in flow.entries(db) if flow.kind(e) == "EXTRACTOR"]
    out = {}
    for txn in db.scalars(select(m.FinancialTransaction)) if known else []:
        who, _rules, ambiguous = flow.identity(db, txn, known)
        if who and not ambiguous:
            out[txn.id] = who
    return out, known


def _record(db, account_id, create=False):
    rec = db.scalars(select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind == KIND,
                                                      m.BankFlowArtifact.account_id == account_id)
                     .order_by(m.BankFlowArtifact.id).limit(1)).first()
    if rec is None and create:
        rec = m.BankFlowArtifact(kind=KIND, account_id=account_id, payload=json.dumps(dict(examples={}, proposals=[])))
        db.add(rec)
        db.flush()
    return rec


def _data(rec):
    return json.loads(rec.payload) if rec is not None else dict(examples={}, proposals=[])


def _save(rec, data):
    rec.payload = json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------------------
# From examples to a rule (code only)
# ---------------------------------------------------------------------------

def _placeholder(text):
    """A variable part as the rule writes it: every run of letters+digits containing a digit becomes its class;
    the other characters stay literal. None when the part is letters only (it cannot be described without
    guessing)."""
    out, found = [], False
    for piece in re.split(r"([A-Za-z0-9/]+)", text):
        if not piece:
            continue
        if re.fullmatch(r"\d{1,2}/\d{1,2}(?:/\d{2,4})?", piece):
            out.append("{date}"); found = True
        elif re.fullmatch(r"\d+", piece):
            out.append("{number}"); found = True
        elif re.fullmatch(r"[A-Za-z0-9]*\d[A-Za-z0-9]*", piece):
            out.append("{code}"); found = True
        else:
            out.append(piece)
    return "".join(out) if found else None


def _with_placeholders(text, offset, variables):
    """`text` (starting at `offset` in the description) with the marked variable parts as placeholders."""
    out, pos = [], 0
    for vs, ve in sorted(variables):
        a, b = max(vs - offset, 0), min(ve - offset, len(text))
        if a >= b or a < pos:
            continue
        holder = _placeholder(text[a:b])
        if holder is None:
            raise ValueError(f"“{text[a:b]}” is marked as variable but has no digits: it cannot be described "
                             "without guessing. Mark it as fixed, or end the WHO before it.")
        out.append(text[pos:a]); out.append(holder); pos = b
    out.append(text[pos:])
    return "".join(out)


def derive(description, span, variables):
    """The WHO extraction rule one example implies. `span` = [start, end] of the WHO in the description;
    `variables` = [[start, end], …] of the parts that vary."""
    original = description or ""
    lead = len(original) - len(original.lstrip())
    text = original.strip()
    s, e = span[0] - lead, span[1] - lead
    variables = [(a - lead, b - lead) for a, b in variables or []]
    if not (0 <= s < e <= len(text)) or not text[s:e].strip():
        raise ValueError("Highlight the part of the description that is the WHO.")
    while s < e and text[s].isspace():
        s += 1
    while e > s and text[e - 1].isspace():
        e -= 1
    who = text[s:e]
    spec = dict(engine=flow.ENGINE, kind="EXTRACTOR", suffix_policy="none")
    before = text[:s]
    if before.strip():
        spec["start"] = _with_placeholders(before, 0, variables)
        first = before.split()[0]
        if not any(a <= 0 < b for a, b in variables) and first.isalpha() and len(first) >= 3:
            spec["prefix"] = first          # anchored: an approved specific rule, never a general one
    else:
        spec.update(start="", from_beginning=True)
    after = text[e:]
    rest = after.lstrip()
    if not rest:
        spec["end_mode"] = "end"
    else:
        at = e + (len(after) - len(rest))
        token = rest.split()[0]
        variable = any(a <= at < b for a, b in variables)
        if variable and rest.strip() == token and re.fullmatch(r"[A-Za-z0-9]*\d[A-Za-z0-9]*", token):
            spec["end_mode"] = "last_code"
        else:
            if variable and _placeholder(token) is None:
                raise ValueError(f"“{token}” is marked as variable but has no digits: it cannot be described without "
                                 "guessing. Mark it as fixed, or end the WHO before it.")
            marker = (" " + _placeholder(token)) if variable else token
            if not variable and token.casefold() in who.casefold():
                marker = " " + token
            spec.update(end_mode="marker", end_markers=[marker])
    flow.validate(None, spec)
    got = flow.extract(spec, original)
    if flow.clean(got) != flow.clean(who):
        raise ValueError(f"The rule built from this example reads “{got or '—'}” instead of “{who}”. "
                         "Mark the parts that vary, or highlight the WHO again.")
    return spec, who.upper()


def describe(spec):
    """The rule in plain words."""
    start = "the beginning of the description" if spec.get("from_beginning") else f"“{spec.get('start', '')}”"
    if spec.get("end_mode") == "end":
        end = "the end of the description"
    elif spec.get("end_mode") == "last_code":
        end = "the final reference code"
    else:
        end = " or ".join(f"“{x}”" for x in spec.get("end_markers") or [spec.get("end", "")])
    text = f"WHO = the text after {start} and before {end}"
    if spec.get("exclude"):
        text += "; not when the description contains " + ", ".join(f"“{x}”" for x in spec["exclude"])
    if any(flow.has_placeholder(x) for x in [spec.get("start", ""), spec.get("end", "")] + list(spec.get("end_markers") or [])):
        text += " ({date}, {number}, {code} = parts that vary)"
    return text


def verify(spec, movements, examples, approved):
    """Every movement the rule intercepts: the person's examples apart from the additional ones."""
    rows, agree = [], 0
    for mv in movements:
        who = flow.extract(spec, mv["description"])
        if not who:
            continue
        ex = examples.get(str(mv["id"]))
        expected = ex.get("who") if ex else None
        ok = expected is None or flow.clean(expected) == flow.clean(who)
        agree += bool(ex) and ok
        rows.append(dict(id=mv["id"], source=mv["source"], date=mv["date"], description=mv["description"],
                         amount=f"{mv['amount_minor'] / 100:,.2f}", who=who, example=bool(ex), expected=expected,
                         disagrees=not ok, approved_who=approved.get(mv["id"])))
    rows.sort(key=lambda r: (not r["example"], r["description"].casefold()))
    return dict(rows=rows, selected=len(rows), examples=sum(r["example"] for r in rows),
                additional=sum(not r["example"] for r in rows), examples_agree=agree,
                examples_disagree=sum(r["example"] and r["disagrees"] for r in rows),
                approved_conflicts=sum(1 for r in rows if r["approved_who"] and flow.clean(r["approved_who"]) != flow.clean(r["who"])))


def separating_literals(excluded, kept):
    """Literal words found in the excluded movements and in none of the kept ones (greedy, at most three)."""
    left, chosen = list(excluded), []
    kept_text = [k.casefold() for k in kept]
    while left and len(chosen) < 3:
        counts = {}
        for d in left:
            for word in set(re.findall(r"[A-Za-z][A-Za-z0-9&'.*-]{2,}", d)):
                if not any(word.casefold() in k for k in kept_text):
                    counts[word] = counts.get(word, 0) + 1
        if not counts:
            break
        best = max(counts, key=lambda w: (counts[w], len(w)))
        chosen.append(best)
        left = [d for d in left if best.casefold() not in d.casefold()]
    return chosen, left


def totals(check):
    """What the training record keeps of a verification: the counts (the rows are recomputed when shown)."""
    return {k: v for k, v in check.items() if k != "rows"}


def summary(movements, examples, approved, proposals):
    confirmed = {int(k) for k in examples}
    single = {int(k) for k, v in examples.items() if v.get("single") or v.get("external")}
    human = {mv["id"] for mv in movements if mv["human_who"]}
    covered = set(approved)
    known = confirmed | human | covered
    return dict(movements=len(movements), confirmed=len(confirmed), single=len(single),
                human=len(human - confirmed), covered=len(covered), known=len(known),
                to_examine=len(movements) - len(known),
                proposals_pending=sum(1 for p in proposals if p["status"] == "PROPOSED"))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def register(app, *, gate, SessionFactory, require_csrf, owner, endpoint):
    def form_ids(name="ids"):
        return sorted({int(x) for x in str(request.form.get(name) or "").split(",") if x.strip().isdigit()})

    @app.route("/bank/who-training")
    @gate
    def bank_who_training_page():
        return render_template("bank_who_training.html")

    @app.route("/bank/who-training/data")
    @gate
    @endpoint
    def bank_who_training_data():
        with SessionFactory() as db:
            data = _data(_record(db, owner(db)))
            movements = _movements(db)
            approved, known = _approved(db)
            for mv in movements:
                mv["rule_who"] = approved.get(mv["id"])
                mv["example"] = data["examples"].get(str(mv["id"]))
                mv["amount"] = f"{mv['amount_minor'] / 100:,.2f}"
            whos = sorted(o.canonical_name for o in db.scalars(select(m.BankOccurrence)) if o.status == "ACTIVE")
            sources = sorted({(mv["source_id"], mv["source"]) for mv in movements}, key=lambda x: x[1])
            return jsonify(ok=True, movements=movements, whos=whos, sources=[dict(id=i, name=n) for i, n in sources],
                           proposals=data["proposals"],
                           approved_rules=len(known), summary=summary(movements, data["examples"], approved, data["proposals"]))

    @app.route("/bank/who-training/examples", methods=["POST"])
    @gate
    @endpoint
    def bank_who_training_examples():
        require_csrf()
        ids = form_ids()
        if not ids:
            raise ValueError("Select at least one movement.")
        who = " ".join(str(request.form.get("who") or "").split())[:200]
        external = request.form.get("external") == "yes"
        single = request.form.get("single") == "yes"
        if not who and not external:
            raise ValueError("Give the WHO, or say that the description does not contain it.")
        focus = request.form.get("focus", type=int)
        span = json.loads(request.form.get("span") or "null")
        variables = json.loads(request.form.get("variables") or "[]")
        with SessionFactory() as db:
            rec = _record(db, owner(db), create=True)
            data = _data(rec)
            known = {o.canonical_name.casefold(): o.canonical_name for o in db.scalars(select(m.BankOccurrence)) if o.status == "ACTIVE"}
            if who and who.casefold() not in known:
                raise ValueError(f"“{who}” is not a WHO yet: create it first (Create WHO).")
            for tid in ids:
                txn = db.get(m.FinancialTransaction, tid)
                if txn is None:
                    continue
                item = dict(who=known.get(who.casefold()) if who else None, external=external, single=single or external,
                            at=datetime.now(timezone.utc).isoformat())
                if tid == focus and span and not external:
                    item.update(span=span, variables=variables)
                    item["spec"], item["read"] = derive(txn.description_original, span, variables)
                data["examples"][str(tid)] = item
            _save(rec, data)
            db.commit()
            return jsonify(ok=True, saved=len(ids))

    @app.route("/bank/who-training/examples/remove", methods=["POST"])
    @gate
    @endpoint
    def bank_who_training_examples_remove():
        require_csrf()
        with SessionFactory() as db:
            rec = _record(db, owner(db))
            data = _data(rec)
            for tid in form_ids():
                data["examples"].pop(str(tid), None)
            if rec is not None:
                _save(rec, data)
                db.commit()
            return jsonify(ok=True)

    @app.route("/bank/who-training/who", methods=["POST"])
    @gate
    @endpoint
    def bank_who_training_create_who():
        require_csrf()
        from rfone_data_store.bank_reconciliation import manual_reconciliation
        with SessionFactory() as db:
            safety.lock_writes(db)
            created = manual_reconciliation.create_who(db, name=request.form.get("name"))
            db.commit()
            return jsonify(ok=True, who=created.occurrence.canonical_name, reused=not getattr(created, "created", True))

    @app.route("/bank/who-training/propose", methods=["POST"])
    @gate
    @endpoint
    def bank_who_training_propose():
        """Rules from the examples with a highlighted WHO (single-movement identifications never)."""
        require_csrf()
        from bank_flow_routes import extractor_key
        with SessionFactory() as db:
            rec = _record(db, owner(db), create=True)
            data = _data(rec)
            movements = _movements(db)
            approved, _known = _approved(db)
            groups = {}
            for tid, ex in data["examples"].items():
                if ex.get("spec") and not ex.get("single"):
                    groups.setdefault(extractor_key(ex["spec"]), dict(spec=ex["spec"], examples=[]))["examples"].append(int(tid))
            existing = {extractor_key(p["spec"]) for p in data["proposals"] if p["status"] in ("PROPOSED", "APPROVED")}
            added = 0
            for key, g in groups.items():
                if key in existing:
                    continue
                check = verify(g["spec"], movements, data["examples"], approved)
                data["proposals"].append(dict(id=len(data["proposals"]) + 1, status="PROPOSED", spec=g["spec"],
                                              text=describe(g["spec"]), from_examples=g["examples"], check=totals(check),
                                              at=datetime.now(timezone.utc).isoformat()))
                added += 1
            _save(rec, data)
            db.commit()
            return jsonify(ok=True, added=added)

    def proposal_of(data, pid):
        p = next((x for x in data["proposals"] if x["id"] == pid), None)
        if p is None:
            raise ValueError("Proposal unavailable.")
        if p["status"] != "PROPOSED":
            raise ValueError(f"This proposal is already {p['status'].lower()}.")
        return p

    @app.route("/bank/who-training/proposals/<int:pid>")
    @gate
    @endpoint
    def bank_who_training_proposal(pid):
        with SessionFactory() as db:
            data = _data(_record(db, owner(db)))
            p = next((x for x in data["proposals"] if x["id"] == pid), None)
            if p is None:
                raise ValueError("Proposal unavailable.")
            approved, _known = _approved(db)
            return jsonify(ok=True, proposal=dict(p, check=verify(p["spec"], _movements(db), data["examples"], approved)))

    @app.route("/bank/who-training/proposals/<int:pid>/exclude", methods=["POST"])
    @gate
    @endpoint
    def bank_who_training_exclude(pid):
        """The person excludes wrong interceptions; RF-One looks for literals that separate them."""
        require_csrf()
        excluded = form_ids()
        with SessionFactory() as db:
            rec = _record(db, owner(db))
            data = _data(rec)
            p = proposal_of(data, pid)
            movements = _movements(db)
            by_id = {mv["id"]: mv for mv in movements}
            selected = [mv for mv in movements if flow.extract(p["spec"], mv["description"])]
            if not set(excluded) & {mv["id"] for mv in selected}:
                raise ValueError("Tick the intercepted movements that are wrong.")
            if any(str(i) in data["examples"] and not data["examples"][str(i)].get("single") for i in excluded):
                raise ValueError("One of the ticked movements is one of your examples: remove the example first.")
            words, unseparated = separating_literals([by_id[i]["description"] for i in excluded],
                                                     [mv["description"] for mv in selected if mv["id"] not in set(excluded)])
            if not words:
                raise ValueError("No word in the ticked descriptions is absent from the others: they cannot be "
                                 "excluded by the description alone. Leave them out of this rule and give their WHO one by one.")
            new = dict(p["spec"], exclude=sorted(set(p["spec"].get("exclude", [])) | set(words)))
            flow.validate(None, new)
            approved, _known = _approved(db)
            before = p["check"]["selected"]
            p.setdefault("history", []).append(dict(spec=p["spec"], excluded=excluded, at=datetime.now(timezone.utc).isoformat()))
            p.update(spec=new, text=describe(new), check=totals(verify(new, movements, data["examples"], approved)))
            _save(rec, data)
            db.commit()
            return jsonify(ok=True, words=words, still_intercepted=len(unseparated), before=before, after=p["check"]["selected"])

    @app.route("/bank/who-training/proposals/<int:pid>/<action>", methods=["POST"])
    @gate
    @endpoint
    def bank_who_training_decide(pid, action):
        require_csrf()
        if action not in ("approve", "reject"):
            raise ValueError("Unknown action.")
        with SessionFactory() as db:
            safety.lock_writes(db)
            rec = _record(db, owner(db))
            data = _data(rec)
            p = proposal_of(data, pid)
            if action == "approve":
                if request.form.get("confirm") != "yes":
                    raise ValueError("Confirm the approval after reading every movement it intercepts.")
                flow.validate(db, p["spec"])
                rule = m.BankAiRule(title=p["text"][:200], organization_kind="GENERAL", status="ACTIVE", apply_future=True,
                                    created_by_account_id=owner(db))
                db.add(rule)
                db.flush()
                db.add(m.BankAiRuleVersion(rule_id=rule.id, version_no=1, rule_text=p["text"], spec=json.dumps(p["spec"], ensure_ascii=False),
                                           method="CODE", create_missing_who=False, override_protected=False,
                                           created_by_account_id=owner(db)))
                p.update(status="APPROVED", rule_id=rule.id)
            else:
                p["status"] = "REJECTED"
            _save(rec, data)
            db.commit()
        if action == "approve":
            from bank_why_pattern_routes import _start_engine_run
            _start_engine_run()
        return jsonify(ok=True, status=p["status"])
