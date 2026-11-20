"""Read-only transaction category trial. Drafts are kept in the user's browser."""
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from datetime import date

from flask import jsonify, render_template, request
from sqlalchemy import select, text
from rfone_data_store import models as m
import sqlite3
from contextlib import ExitStack
import bank_trial_sources as source_lookup
import bank_work_research

TYPES = {"direct", "lookup", "check", "text", "employee", "adp", "restaurant", "fuel", "ev"}
WEB = {"restaurant", "fuel", "ev"}
ACTIONS = {"next", "manual", "why", "payroll", "dining"}
DEFAULTS = [
    ("Check", [("check", "", "manual")]),
    ("Dipendenti", [("employee", "", "next"), ("adp", "", "payroll")]),
    ("Ristorazione", [("restaurant", "", "dining")]),
    ("Distributori di benzina", [("fuel", "Vehicle - Fuel", "why")]),
    ("Ricarica EV", [("ev", "", "manual")]),
]


def defaults():
    return [dict(name=name, levels=[dict(test=t, value=v if t == "text" else "",
                 action=a, why=v if a == "why" else "", days=3 if t == "adp" else 0) for t, v, a in levels]) for name, levels in DEFAULTS]


def supplies_employee(step):
    return step.get("test") == "lookup" and step.get("action") == "next" and any(
        source.endswith(".employees") for source in step.get("sources", []))


def validate(categories, whys, *, partial=False, standalone=False):
    if not isinstance(categories, list) or not 1 <= len(categories) <= 50:
        raise ValueError("Definisci da 1 a 50 categorie.")
    for cat in categories:
        if not isinstance(cat, dict) or not isinstance(cat.get("name"), str) or not cat["name"].strip():
            raise ValueError("Dai un nome a ogni categoria.")
        levels = cat.get("levels")
        if not isinstance(levels, list) or not 1 <= len(levels) <= 20:
            raise ValueError("Ogni categoria richiede da 1 a 20 livelli.")
        seen = set()
        for index, item in enumerate(levels):
            if not isinstance(item, dict):
                raise ValueError("Livello non valido.")
            t, a = item.get("test"), item.get("action")
            if item.get("dirty"):
                raise ValueError(f'{cat["name"]}, passaggio {index+1}: interpreta prima i comandi modificati.')
            if t == "adp" and (type(item.get("days", 0)) is not int or not 0 <= item.get("days", 0) <= 366):
                raise ValueError("Indica per ADP una finestra tra 0 e 366 giorni.")
            if t not in TYPES or a not in ACTIONS:
                raise ValueError("Scegli una verifica e un esito disponibili.")
            if t == "text" and not str(item.get("value") or "").strip():
                raise ValueError("Indica il testo da cercare.")
            if not standalone and t == "adp" and "employee" not in seen:
                raise ValueError("Il confronto ADP richiede prima il riconoscimento del dipendente.")
            seen.add(t)
            if supplies_employee(item):
                seen.add("employee")
            if not standalone and ((a == "payroll" and "adp" not in seen) or (a == "dining" and "restaurant" not in seen)):
                raise ValueError("L’esito richiede il relativo riscontro ADP o ristorante.")
            if a == "why" and item.get("why") not in whys:
                raise ValueError("Scegli un WHY del catalogo.")


STAFF = "select id, display_name from employees where display_name is not null"
PAY = """select e.employee_id, f.payment_amount_minor, f.pay_date, r.restaurant_id
from payroll_payment_facts f join employee_payroll_results e on e.id=f.employee_payroll_result_id
join payroll_runs r on r.id=e.payroll_run_id join source_systems s on s.id=r.source_system_id
where upper(s.code) like '%ADP%' and r.status='COMPLETE' and r.superseded_by_payroll_run_id is null
and coalesce(e.review_status,'OK')='OK'"""
ROLE = """select a.employee_id, a.restaurant_id, a.valid_from, a.valid_to, o.code, r.name
from employee_assignments a join operational_areas o on o.id=a.operational_area_id
join restaurant_roles r on r.id=a.restaurant_role_id"""


def norm(value):
    return " ".join(re.findall(r"[^\W_]+", (value or "").casefold()))


def staff_data(db):
    path = os.environ.get("RFONE_DOMAIN_DATA")
    if path:
        conn = source_lookup.domain_connection()
        try:
            with conn.cursor() as cur:
                rows = []
                for sql in (STAFF, PAY, ROLE):
                    cur.execute(sql)
                    rows.append(cur.fetchall())
                return rows
        finally:
            conn.close()
    return [db.execute(text(sql)).all() for sql in (STAFF, PAY, ROLE)]


def employee_roles(roles, employee, day):
    found = defaultdict(set)
    for eid, rid, start, end, area, role in roles:
        if eid != employee or (start and str(start)[:10] > day) or (end and str(end)[:10] < day):
            continue
        found[rid].add("Management Payroll" if re.search("manager|management", norm(role)) else
                  {"foh": "Payroll - FOH - Regular Payroll", "boh": "Payroll - BOH - Regular Payroll"}.get(norm(area)))
    return found


def employee_ids(names, recognised, description):
    if recognised:
        target = " " + norm(recognised) + " "
        return {eid for eid, name in names if name == target}
    return {eid for eid, name in names if name in description}


def adp_matches(pay, employee, debit, day, days):
    if debit >= 0 or not day or day == "None":
        return []
    movement_date = date.fromisoformat(day)
    return [rid for pay_date, rid in pay.get((employee, -debit), ())
            if abs((pay_date - movement_date).days) <= days]


def simulate(db, categories, whys):
    validate(categories, whys)
    with ExitStack() as stack:
        lookups = {}
        catalog = None
        for ci, category in enumerate(categories):
            for li, level in enumerate(category["levels"]):
                if level["test"] == "lookup":
                    if catalog is None:
                        catalog = source_lookup.sources(db)
                    lookup = source_lookup.Lookup(db, level, catalog, populate=True)
                    stack.callback(lookup.conn.close)
                    lookups[ci, li] = lookup
        return simulate_levels(db, categories, whys, lookups)


def simulate_levels(db, categories, whys, lookups):
    warnings = []
    try:
        staff, payments, roles = staff_data(db)
    except Exception:
        staff, payments, roles = [], [], []
    if not staff:
        warnings.append("Anagrafica dipendenti assente o non raggiungibile.")
    names = [(eid, " " + norm(n) + " ") for eid,n in staff if len(norm(n).split()) >= 2]
    from rfone_data_store.bank_reconciliation import adp_reports
    uploaded_pay = adp_reports.Payments(adp_reports.reports(db))
    payroll_days = uploaded_pay.days | {date.fromisoformat(str(d)[:10]) for _, _, d, _ in payments}
    if not payroll_days:
        warnings.append("Nessun pagamento ADP verificabile disponibile.")
    staff_names = dict(staff)
    pay = defaultdict(list)
    for eid, amount, day, rid in payments:
        pay[eid, amount].append((date.fromisoformat(str(day)[:10]), rid))
    run = db.scalar(select(m.BankEngineRun.id).where(m.BankEngineRun.summary_json.is_not(None)).order_by(m.BankEngineRun.id.desc()).limit(1))
    proposals = {r.financial_transaction_id: json.loads(r.payload_json) for r in db.scalars(
        select(m.BankEngineResult).where(m.BankEngineResult.run_id == run))}
    research = (bank_work_research.latest_results(db) or {}).get("results", {})
    owner_types = {e.id:e.entity_type for e in db.scalars(select(m.ReportingEntity))}
    rows = db.execute(select(m.FinancialTransaction, m.BankTransactionExplanation).outerjoin(
        m.BankTransactionExplanation, m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id))
    stats = [[dict(entered=0, matched=0, solved=0, manual=0, onward=0) for _ in c["levels"]] for c in categories]
    total = excluded = 0
    pending, examples = [], []
    for txn, decision in rows:
        total += 1
        r = proposals.get(txn.id, {})
        if (txn.accounting_status == "DUPLICATE_SUPPRESSED" or txn.duplicate_status == "CONFIRMED_DUPLICATE"
                or decision and decision.decision_source == "HUMAN" or r.get("status") == "RECONCILED" or r.get("protected")):
            excluded += 1
            continue
        desc = txn.description_original or ""
        day = str(txn.posting_date or txn.transaction_date)[:10]
        normalized = " " + norm(desc) + " "
        evidence = research.get(str(txn.id), {})
        closed = needs_web = False
        for ci, cat in enumerate(categories):
            employee = matched_pay = None
            prior_result = {}
            roles_at_date = {}
            for li, level in enumerate(cat["levels"]):
                s = stats[ci][li]
                s["entered"] += 1
                t, a = level["test"], level["action"]
                reason = why = ""
                if t == "direct":
                    match = True
                elif t == "check":
                    match = bool(re.match(r"^\s*(?:CHECK|CHEQUE)\s*#?\s*\d+\b", desc, re.I))
                elif t == "lookup":
                    params = dict(transaction_id=txn.id, description=desc, who=r.get("who_name") or "",
                                  employee_id=employee, amount_minor=txn.amount_minor, day=day,
                                  source_id=txn.payment_instrument_id, prior_json=json.dumps(prior_result, default=str))
                    found = lookups[ci, li].find(params)
                    match = len(found) == 1
                    if match:
                        prior_result = found[0]
                        if supplies_employee(level):
                            identity = prior_result.get("employee_id")
                            if identity is None and len(level.get("sources", [])) == 1:
                                identity = prior_result.get("id")
                            candidates = [eid for eid in staff_names if str(eid) == str(identity)]
                            if len(candidates) == 1:
                                employee = candidates[0]
                                roles_at_date = employee_roles(roles, employee, day)
                                prior_result["employee_id"] = employee
                            else:
                                reason = "Il passaggio non restituisce un dipendente identificato: rigenera il passaggio chiedendo di conservarne l’identità."
                    elif found:
                        reason = "Più corrispondenze nelle fonti del passaggio"
                elif t == "text":
                    match = " "+norm(level["value"])+" " in normalized
                elif t == "employee":
                    ids = employee_ids(names, r.get("who_name"), normalized)
                    match = bool(ids)
                    if len(ids) == 1:
                        employee = next(iter(ids))
                        roles_at_date = employee_roles(roles, employee, day)
                    elif match:
                        reason = "Più dipendenti compatibili"
                elif t == "adp":
                    hits = adp_matches(pay, employee, txn.amount_minor, day, level.get("days", 0))
                    if not hits and day and day != "None":
                        report_hits = uploaded_pay.matches(staff_names.get(employee), txn.amount_minor,
                                                           date.fromisoformat(day), level.get("days", 0))
                        if report_hits:
                            # A Summary has no RF-One restaurant id. Use only an unambiguous assignment.
                            locations = list(roles_at_date) or [None]
                            hits = locations * len(report_hits)
                    match = len(hits) == 1
                    if employee is None:
                        match = False
                        reason = "Manca un dipendente identificato univocamente per il confronto ADP"
                    elif match:
                        matched_pay = hits[0]
                    elif employee and day and day != "None" and not any(abs((d - date.fromisoformat(day)).days) <= level.get("days", 0) for d in payroll_days):
                        reason = "Manca il report ADP per la data del movimento"
                    elif hits or li == len(cat["levels"]) - 1 or a == "next":
                        reason = "Payroll da verificare: nessun pagamento ADP univoco per persona, importo e data"
                else:
                    eligible = (txn.amount_minor < 0 and not r.get("who_id") and not r.get("match") and not r.get("split")
                                and not r.get("anomalies") and txn.duplicate_status != "CANDIDATE_DUPLICATE"
                                and not any(e.get("code") in bank_work_research.NOT_RESEARCHED for e in r.get("exceptions", [])))
                    supported = bool(evidence.get("sources")) and evidence.get("outcome") in ("WHO_IDENTIFIED","GENERIC")
                    nature = norm(evidence.get("nature"))
                    if t == "restaurant":
                        match = eligible and supported and (evidence.get("toast_verified") or evidence.get("why_basis") == "APPROVED DINING + SOURCE OWNER POLICY"
                            or bool(re.fullmatch(r"restaurant (?:dining )?(?:payment|purchase|meal)(?: at .+)?", nature)))
                    else:
                        pattern = r"(?:gasoline|gas|fuel|petrol) (?:purchase|payment|refuel)(?: at .+)?" if t=="fuel" else r"(?:ev|electric vehicle) charging(?: payment| session)?(?: at .+)?"
                        match = eligible and supported and bool(re.fullmatch(pattern, nature))
                    if eligible and not supported:
                        needs_web = True
                if not match and not reason:
                    s["onward"] += 1
                    if a == "next":
                        # This step supplies evidence required by the rest of the category.
                        break
                    # A classification applies only on a match. Try the next alternative.
                    continue
                if match:
                    s["matched"] += 1
                if match and a == "next" and not reason:
                    s["onward"] += 1
                    continue
                if a == "why":
                    why = level["why"]
                elif a == "payroll" and matched_pay is not None:
                    applicable = roles_at_date.get(matched_pay, set())
                    why = next(iter(applicable)) if len(applicable) == 1 else None
                elif a == "dining":
                    why = {"PERSONAL":"Owner Personal — Restaurant","LEGAL":"Business Meals & Entertainment"}.get(owner_types.get(r.get("payer_id")))
                if not reason and a != "manual" and why in whys:
                    s["solved"] += 1
                    result = ("Ristorazione → " if a == "dining" else "") + why
                else:
                    s["manual"] += 1
                    result = reason or ("Riconcilio manuale" if a == "manual" else "WHY o titolare da verificare")
                examples.append(dict(category=cat["name"],description=desc, result=result))
                closed = True
                break
            if closed:
                break
        if not closed and needs_web:
            pending.append(txn.id)
    return dict(total=total, excluded=excluded, stats=stats, examples=examples, web=len(pending),
                remaining=total-excluded-len(examples), warnings=warnings, employees=len(names), payments=len(payments))


def register(app, gate, sessions, csrf):
    from itsdangerous import BadSignature, URLSafeSerializer
    tickets = URLSafeSerializer(app.secret_key, salt="bank-category-review-v1")

    def catalog(db):
        return sorted(db.scalars(select(m.BankTransactionReason.name).where(m.BankTransactionReason.status=="ACTIVE")))

    @app.get("/bank/configuration/category-trial")
    @gate
    def bank_category_trial():
        with sessions() as db:
            return render_template("bank_category_trial.html", defaults=defaults(), whys=catalog(db))

    @app.post("/bank/configuration/category-trial/simulate")
    @gate
    def bank_category_trial_simulate():
        csrf()
        try:
            with sessions() as db:
                entries = json.loads(request.form.get("steps", "[]"))
                if not isinstance(entries, list) or not 1 <= len(entries) <= 20:
                    raise ValueError("Genera tutti i passaggi prima di simulare.")
                levels = []
                for entry in entries:
                    if not isinstance(entry, dict) or not isinstance(entry.get("ticket"), str):
                        raise ValueError("Passaggio generato mancante.")
                    step = tickets.loads(entry["ticket"])[0]["levels"][-1]
                    if step != entry.get("step"):
                        raise ValueError("Rigenera il passaggio modificato.")
                    levels.append(step)
                plan = [dict(name=request.form.get("name", ""), levels=levels)]
                return jsonify(simulate(db, plan, catalog(db)))
        except BadSignature:
            return jsonify(error="Controlla il processo con AI prima della simulazione."), 400
        except (ValueError, sqlite3.Error) as exc:
            return jsonify(error=str(exc)), 400

    @app.post("/bank/configuration/category-trial/chat")
    @gate
    def bank_category_trial_chat():
        csrf()
        import bank_chatgpt
        try:
            history = json.loads(request.form.get("history", "[]"))
            if not isinstance(history, list) or not history or any(
                not isinstance(turn, dict) or turn.get("role") not in ("user", "assistant")
                or not isinstance(turn.get("content"), str) or not turn["content"].strip()
                for turn in history
            ):
                raise ValueError("Scrivi il messaggio per il passaggio.")
            with sessions() as db:
                whys = catalog(db)
            context = dict(category=request.form.get("name", ""),
                           previous_steps=json.loads(request.form.get("context", "[]")),
                           current_step=request.form.get("current", ""), conversation=history,
                           allowed_whys=whys)
            prompt = """Discuss ONE Bank reconciliation step with its author in Italian.
You are understanding the requested purpose, NOT compiling or executing a rule.
Explain 'Ho capito questo' and describe the requested search, retained information and outcome.
Use previous_steps only as context. Never change other steps. Accept imperative commands without
inventing a condition. Preserve the author's dates, tolerances, branches and intended scope exactly.
Ask a focused question only when needed. Suggestions must be separate, optional and must not enter
the agreed summary unless the author accepts them. Do not silently add requirements or safeguards
to the author's logic. Data availability is not a reason to change the intended meaning.
Return JSON {reply: human conversational response, summary: complete current understanding of this
single step in plain Italian, ready: boolean}. ready means the intent is sufficiently specified to
compile if the user presses Save, not that the user has already approved. No SQL or executable code.
The author approves solely through Salva passaggio. Never claim to have saved or executed anything.
Keep summary within 4000 characters."""
            result = bank_chatgpt.generate_json(prompt + "\n" + json.dumps(context, ensure_ascii=False))
            if (not isinstance(result, dict) or not isinstance(result.get("reply"), str)
                    or not isinstance(result.get("summary"), str) or not result["summary"].strip()
                    or len(result["summary"]) > 4000 or not isinstance(result.get("ready"), bool)):
                raise ValueError("Risposta AI incompleta. Ripeti il messaggio.")
            return jsonify(result)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except Exception:
            return jsonify(error="Assistente AI non disponibile. La conversazione resta aperta."), 503

    @app.post("/bank/configuration/category-trial/assist")
    @gate
    def bank_category_trial_assist():
        csrf()
        import bank_chatgpt
        try:
            with sessions() as db:
                whys = catalog(db)
            name = request.form.get("name", "").strip()
            goal = request.form.get("goal", "").strip()
            if not name or not goal:
                raise ValueError("Indica la categoria e descrivi il risultato desiderato.")
            previous = json.loads(request.form.get("context", "[]"))
            if not isinstance(previous, list) or len(previous) >= 20 or len(goal) > 4000:
                raise ValueError("Massimo 20 passaggi e 4000 caratteri per passaggio.")
            dialogue = json.loads(request.form.get("dialogue", "[]"))
            if not isinstance(dialogue, list) or any(
                not isinstance(pair, dict) or any(not isinstance(pair.get(k), str) or not pair[k].strip()
                                                   for k in ("question", "answer")) for pair in dialogue
            ):
                raise ValueError("Chiarimento incompleto.")
            prompt = """Translate ONLY the current Italian step into one executable operator.
current_step is the final human-readable meaning explicitly approved by the user with Save.
Translate faithfully: never add conditions, change branches, tolerances or outcome, or incorporate
unaccepted suggestions. If the available operators cannot express that meaning, return a concrete
question in issues instead of silently substituting a different behavior.
Previous descriptions are context only. Compile this step independently, even if prerequisites
have not yet been compiled. The complete sequence is validated before execution. Preserve its
facts and carry evidence to the next step when the author requests it. A prefix ending in next
is valid and may be extended later. Do not invent the remaining process. Use web evidence tests
when AI research is requested for a supported merchant class. Ask one concrete question in Italian
if the step is ambiguous or unsupported. Return {issues:[question]} or
{issues:[],step:{test,value,action,why,days}}. Do not return other steps.
Use the author's answers in dialogue to clarify current_step. Never require a condition for an imperative.
For an unconditional action on movements reaching this step, use test direct with the requested action.
For extracting or calculating a value from the current movement alone return {issues:[],sources:[]}
to generate a SELECT expression; keep its value for later steps. Ask only for genuinely missing information.
Supported atomic tests:
check = numbered check at start; text = contains exact whole phrase (value);
employee = exact recognised WHO in personnel directory, or full name in description if no WHO.
A unique employee and dated roles are carried to later steps.
adp = unique verified outgoing ADP payment for that employee, exact net amount and date +/- days.
restaurant/fuel/ev = review available web evidence on unresolved merchant payments.
Actions: next (retain evidence and continue), manual, why (exact WHY catalog label),
payroll (use ADP restaurant and saved role to select payroll WHY), dining (owner-specific restaurant WHY).
The named payroll and dining actions already implement mappings. Do not demand the author restate them:
payroll maps FOH and BOH to Regular Payroll for that role, Manager to Management Payroll; ambiguous
role or ADP evidence routes to manual. Dining already reads the payer's owner type from the movement:
PERSONAL uses Owner Personal — Restaurant, LEGAL uses Business Meals & Entertainment, unknown goes
to manual. Both named actions can be requested in ordinary Italian by describing their behavior.
days for ADP is a whole number 0..366. For vague proximity without a number, ask how many days;
for exact date use zero. Never invent missing actions or alter the author's commands."""
            with sessions() as db:
                unavailable = []
                available = source_lookup.sources(db, warnings=unavailable)
            prompt += """
The built-ins are conveniences, not a closed set. For any request to look in tables or uploaded
files that is not exactly a built-in, select the relevant sources from the actual catalog.
Return {issues:[], sources:[exact source keys in order]}. Choose RF domain tables for consolidated
domain data and bank tables for bank imports. Include tables needed for identity joins and finalized
status, and prefer normalized consolidated facts to raw inputs when requested. A request to check
a match is itself sufficient: use next to retain a unique result if no final action was specified."""
            context = dict(category=name, previous_steps=previous, current_step=goal, dialogue=dialogue, allowed_whys=whys,
                           unavailable_sources=unavailable, source_catalog=list(available))
            result = bank_chatgpt.generate_json(prompt + "\n" + json.dumps(context, ensure_ascii=False))
            if isinstance(result, dict) and "sources" in result and not result.get("issues"):
                keys = result["sources"]
                if not isinstance(keys, list) or any(not isinstance(k,str) or k not in available for k in keys):
                    raise ValueError("L’AI ha indicato una fonte assente dal catalogo.")
                with sessions() as db:
                    for key in keys:
                        if key.startswith("file."):
                            available[key] = list(dict.fromkeys(k for row in source_lookup.uploaded(db,key) for k in row))
                schema = {f"s{i}":dict(source=k,columns=available[k]) for i,k in enumerate(keys,1)}
                query_prompt = """Compile only current_step into a read-only SQLite SELECT on the provided
aliases s1,s2,..., respecting the author’s clarifications in dialogue. With an empty schema, use a SELECT of movement parameters or expressions without FROM or WHERE for direct commands. With tables use their actual columns (joins allowed). Return one row per matching fact:
zero fails this test, one its named columns become :prior_json for the next step, multiple go to manual.
Do not use LIMIT 1 to hide ambiguity. Parameters are :description, :transaction_id, :who (recognized
name), :employee_id (from earlier employee lookup), :amount_minor (signed cents), :day (ISO),
:source_id, :prior_json. When checking an employee name without a previous employee lookup, join
employees and use the recognized WHO or full name in description.
When identifying an employee for later steps, return employees.id AS employee_id; retain the identity
with action next. ADP and subsequent steps use this exact identity and its dated role assignments.
Match exact minor units for outgoing payments, and use abs(julianday(...)-julianday(:day)) for tolerances. For consolidated tips use
the payable entitlement for the employee and business_date with its finalized run. No writes or SQL
functions with side effects. Return {issues:[],step:{test:"lookup",query,action,why},explanation:"..."}.
Write explanation in plain Italian for a bookkeeper. Describe the actual source, comparisons, tolerance
and outcome of this exact query in one or two short sentences, with no identifiers, SQL or JSON.
Action next for a check/retained result, manual or why when explicitly requested. WHY must be an exact
catalog entry. If evidence or columns cannot support the instruction, ask a focused question in issues."""
                context.pop("source_catalog")
                context["schema"] = schema
                result = bank_chatgpt.generate_json(query_prompt + "\n" + json.dumps(context,ensure_ascii=False))
                if isinstance(result, dict) and not result.get("issues") and isinstance(result.get("step"), dict):
                    step = result["step"]
                    if step.get("test") != "lookup":
                        raise ValueError("La verifica generata deve usare le fonti selezionate.")
                    step["sources"] = keys
                    with sessions() as db:
                        lookup = source_lookup.Lookup(db, step, available, populate=False)
                        lookup.conn.close()
            if not isinstance(result, dict) or not isinstance(result.get("issues"), list):
                raise ValueError("Risposta AI incompleta. Ripeti il controllo.")
            issues = result["issues"]
            if issues:
                if not all(isinstance(issue, str) and issue.strip() for issue in issues):
                    raise ValueError("Segnalazione AI incompleta. Ripeti il controllo.")
                return jsonify(issues=issues)
            step = result.get("step")
            if not isinstance(step, dict):
                raise ValueError("Passaggio non interpretabile. Precisa la verifica e il suo esito.")
            if step.get("test") == "adp" and step.get("days") is None:
                raise ValueError("Specifica la distanza massima in giorni per il confronto ADP.")
            plan = [dict(name=name, levels=[step])]
            validate(plan, whys, partial=True, standalone=True)
            return jsonify(issues=[], step=step, explanation=result.get("explanation", ""), ticket=tickets.dumps(plan))
        except BadSignature:
            return jsonify(error="Rigenera il passaggio precedente."), 400
        except (ValueError, sqlite3.Error) as exc:
            return jsonify(error=str(exc)),400
        except Exception:
            return jsonify(error="Assistente AI non disponibile. I comandi restano nella bozza."),503
