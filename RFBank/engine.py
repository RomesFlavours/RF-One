"""Validated deterministic procedures; source SELECTs use the existing read-only sandbox."""
import hashlib
import json
import sqlite3
from pathlib import Path


def connect(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def load_data(path):
    db = connect(path)
    try:
        db.execute('BEGIN')
        who = [dict(r) for r in db.execute('SELECT id,canonical_name,default_transaction_reason_id FROM bank_occurrences')]
        why = [dict(r) for r in db.execute('SELECT id,code,name,accounting_classification_id FROM bank_transaction_reasons')]
        what = [dict(r) for r in db.execute('SELECT id,code,name FROM bank_accounting_classifications')]
        rows = [dict(r) for r in db.execute('''SELECT t.id,t.posting_date,t.description_original AS description,
            t.amount_minor,t.payment_instrument_id AS source_id,t.source_memo AS memo,
            w.canonical_name AS who,i.display_name AS source FROM financial_transactions t
            JOIN payment_instruments i ON i.id=t.payment_instrument_id
            LEFT JOIN bank_transaction_explanations e ON e.id=t.explanation_id
            LEFT JOIN bank_occurrences w ON w.id=e.occurrence_id ORDER BY t.posting_date DESC,t.id DESC''')]
        return dict(who=who, why=why, what=what, rows=rows)
    finally:
        db.close()


def signature(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def actions_valid(actions, depth=0, budget=None):
    budget = budget if budget is not None else [0]
    if depth > 8 or not isinstance(actions, list) or len(actions) > 12:
        raise ValueError('Troppi passaggi o livelli nella regola.')
    for a in actions:
        budget[0] += 1
        if budget[0] > 120 or not isinstance(a, dict):
            raise ValueError('Procedimento troppo esteso o non valido.')
        op = a.get('op')
        target = a.get('target') in ('who', 'why', 'memo')
        if op == 'set':
            valid = set(a) == {'op', 'target', 'value'} and target and isinstance(a['value'], str) and 0 < len(a['value']) <= 500
        elif op == 'extract':
            valid = set(a) in ({'op', 'target', 'after', 'before'}, {'op', 'target', 'after', 'before', 'field'}) and target and all(isinstance(a[k], str) and len(a[k]) <= 500 for k in ('after', 'before')) and bool(a['after'] or a['before']) and a.get('field', 'description') in ('description', 'memo')
        elif op == 'default_why':
            valid = set(a) == {'op'}
        elif op == 'require_source':
            valid = set(a) == {'op', 'note'} and isinstance(a['note'], str) and 0 < len(a['note']) <= 1000
        elif op == 'lookup':
            valid = set(a) == {'op', 'sources', 'query', 'label'} and isinstance(a['sources'], list) and 1 <= len(a['sources']) <= 8 and all(isinstance(x, str) for x in a['sources']) and isinstance(a['query'], str) and 0 < len(a['query']) <= 12000 and isinstance(a['label'], str) and 0 < len(a['label']) <= 1000
        elif op == 'from_result':
            valid = set(a) == {'op', 'target', 'column'} and target and isinstance(a['column'], str) and 0 < len(a['column']) <= 200
        elif op == 'branch':
            valid = set(a) == {'op', 'when', 'then', 'else'}
            if valid:
                condition(a['when'])
                actions_valid(a['then'], depth+1, budget)
                actions_valid(a['else'], depth+1, budget)
        else:
            valid = False
        if not valid:
            raise ValueError('Passaggio non supportato: chiariscilo nella chat.')


def execute_actions(actions, context, values, notes, data, sources):
    for a in actions:
        op = a['op']
        if op == 'branch':
            selected = matches(a['when'], context)
            notes.append('Condizione del passaggio: ' + ('sì' if selected else 'no'))
            execute_actions(a['then'] if selected else a['else'], context, values, notes, data, sources)
            continue
        if op == 'lookup':
            if sources is None:
                raise ValueError('Fonti non disponibili per la ricerca.')
            prior = {k[7:]: v for k, v in context.items() if k.startswith('result.')}
            found = sources.find(a, dict(who=context.get('who') or '', employee_id=prior.get('employee_id'),
                description=context.get('description') or '', amount_minor=context['amount_minor'],
                day=context['day'], transaction_id=context['id'], source_id=context.get('source_id'),
                prior_json=json.dumps(prior, default=str)))
            if len(found) != 1:
                raise ValueError(a['label'] + ': ' + ('nessuna corrispondenza' if not found else 'più corrispondenze'))
            for k in list(context):
                if k.startswith('result.'):
                    del context[k]
            context.update({'result.'+k: v for k, v in found[0].items()})
            notes.append(a['label'] + ': corrispondenza unica (' + ', '.join(a['sources']) + ')')
            continue
        if op == 'require_source':
            raise ValueError('Fonte necessaria: ' + a['note'])
        if op == 'set':
            target, value = a['target'], a['value'].strip()
        elif op == 'extract':
            target, value = a['target'], extract(str(context.get(a.get('field', 'description')) or ''), a['after'], a['before'])
        elif op == 'from_result':
            target, value = a['target'], context.get('result.' + a['column'])
            if value is None or not str(value).strip():
                raise ValueError('Il risultato non contiene ' + a['column'])
            value = str(value).strip()
        elif op == 'default_why':
            names = [w for w in data['who'] if w['canonical_name'].casefold() == str(context.get('who') or '').casefold()]
            reasons = [w for w in data['why'] if len(names) == 1 and w['id'] == names[0]['default_transaction_reason_id']]
            if len(reasons) != 1:
                raise ValueError('WHO senza WHY predefinito univoco.')
            target, value = 'why', reasons[0]['name']
        else:
            raise ValueError('Passaggio non supportato.')
        context[target] = values[target] = value
        notes.append(target.upper() + ': ' + value)


def condition(c, depth=0):
    if depth > 8 or not isinstance(c, dict):
        raise ValueError('Condizione non valida o troppo annidata.')
    if len(c) == 1 and next(iter(c)) in ('all', 'any', 'not'):
        key = next(iter(c))
        children = c[key] if key != 'not' else [c[key]]
        if not isinstance(children, list) or not 1 <= len(children) <= 30:
            raise ValueError('Condizione vuota o troppo estesa.')
        for child in children:
            condition(child, depth + 1)
        return
    if set(c) != {'field', 'op', 'value'} or (c['field'] not in ('description', 'source', 'direction', 'who', 'why', 'memo', 'amount_minor', 'day') and not (isinstance(c['field'], str) and c['field'].startswith('result.'))):
        raise ValueError('Campo della condizione non supportato.')
    if c['op'] not in ('contains', 'starts_with', 'ends_with', 'equals') or not isinstance(c['value'], str) or not c['value'].strip() or len(c['value']) > 500:
        raise ValueError('Operatore o valore della condizione non supportato.')

def validate(plan):
    if not isinstance(plan, dict) or set(plan) != {'title', 'summary', 'rules'}:
        raise ValueError('Il procedimento deve avere titolo, riepilogo e regole supportate.')
    if not all(isinstance(plan[k], str) and 0 < len(plan[k]) <= 6000 for k in ('title', 'summary')):
        raise ValueError('Titolo o riepilogo non valido.')
    if not isinstance(plan['rules'], list) or not 1 <= len(plan['rules']) <= 40:
        raise ValueError('Servono da 1 a 40 casi espliciti.')
    for rule in plan['rules']:
        if not isinstance(rule, dict) or set(rule) != {'label', 'when', 'actions'} or not isinstance(rule['label'], str):
            raise ValueError('Un caso deve avere nome, condizioni e azioni.')
        condition(rule['when'])
        if not rule['actions']:
            raise ValueError('Il caso deve avere almeno un passaggio.')
        actions_valid(rule['actions'])
    return plan


def matches(c, row):
    if 'all' in c:
        return all(matches(x, row) for x in c['all'])
    if 'any' in c:
        return any(matches(x, row) for x in c['any'])
    if 'not' in c:
        return not matches(c['not'], row)
    value = ('OUT' if row['amount_minor'] < 0 else 'IN' if row['amount_minor'] > 0 else 'ZERO') if c['field'] == 'direction' else row.get(c['field']) or ''
    text, needle = str(value).casefold(), c['value'].casefold()
    return {'contains': lambda: needle in text, 'starts_with': lambda: text.startswith(needle),
            'ends_with': lambda: text.endswith(needle), 'equals': lambda: text == needle}[c['op']]()


def extract(text, after, before):
    start = 0
    if after:
        at = text.casefold().find(after.casefold())
        if at < 0:
            raise ValueError('Delimitatore iniziale assente.')
        start = at + len(after)
    end = len(text)
    if before:
        end = text.casefold().find(before.casefold(), start)
        if end < 0:
            raise ValueError('Delimitatore finale assente.')
    value = text[start:end].strip().upper()
    if not value:
        raise ValueError('L’estrazione è vuota.')
    return value


def execute_plan(plan, data, sources=None):
    """Simulator: only executes the instructions of this plan on every movement, cases in their order, each case
    reading what the previous ones produced. No other rules, no WHO/WHY catalogue check, no reconciliation.
    A case whose step fails leaves no partial value and is reported; the following cases still run."""
    validate(plan)
    results, unmatched = [], 0
    for row in data['rows']:
        context = dict(row, day=str(row.get('posting_date') or '')[:10], who=None, why=None, memo=None)
        values, steps, issues, applied = {}, [], [], 0
        for number, rule in enumerate(plan['rules'], 1):
            if not matches(rule['when'], context):
                continue
            applied += 1
            trial_context, trial_values, notes = dict(context), {}, []
            try:
                execute_actions(rule['actions'], trial_context, trial_values, notes, data, sources)
            except ValueError as exc:
                steps.append(f"{number}. {rule['label']}: non eseguito")
                issues.append(f"{number}. {rule['label']}: {exc}")
                continue
            context, values = trial_context, dict(values, **trial_values)
            steps.append(f"{number}. {rule['label']}" + (': ' + '; '.join(notes) if notes else ''))
        if not applied:
            unmatched += 1
            continue
        results.append(dict(row, who=values.get('who'), why=values.get('why'), memo=values.get('memo'), what=None,
            status='DOUBT' if issues else 'MATCH', steps=steps, issues=issues))
    return dict(total=len(data['rows']), matched=sum(r['status'] == 'MATCH' for r in results),
                doubtful=sum(r['status'] == 'DOUBT' for r in results), conflicts=0, unmatched=unmatched,
                rows=results, plan_signature=signature(plan))


def simulate(plan, data, sources=None):
    validate(plan)
    def find(items, value, fields):
        found = [x for x in items if any(str(x.get(k, '')).casefold() == value.casefold() for k in fields)]
        return found[0] if len(found) == 1 else None
    whys = {x['id']: x for x in data['why']}
    whats = {x['id']: x for x in data['what']}
    results = []
    unmatched = 0
    for row in data['rows']:
        applicable = [r for r in plan['rules'] if matches(r['when'], row)]
        if not applicable:
            unmatched += 1
            continue
        proposals = []
        for rule in applicable:
            values, notes, errors = {}, [rule['label']], []
            context = dict(row, day=str(row.get('posting_date') or '')[:10])
            try:
                execute_actions(rule['actions'], context, values, notes, data, sources)
            except ValueError as exc:
                errors.append(str(exc))
            w = find(data['who'], values.get('who', ''), ('canonical_name',))
            reason = find(data['why'], values.get('why', ''), ('name', 'code'))
            if values.get('who') and not w:
                errors.append('WHO proposto non presente univocamente nel catalogo; non creato.')
            if values.get('why') and not reason:
                errors.append('WHY non presente univocamente nel catalogo; non creato.')
            proposals.append(dict(who=values.get('who'), memo=values.get('memo'), why=reason['name'] if reason else values.get('why'),
                what=whats.get(reason['accounting_classification_id'], {}).get('name') if reason else None,
                notes=notes, errors=errors))
        conflicts = any(len({p[k].casefold() for p in proposals if p.get(k)}) > 1 for k in ('who', 'why', 'memo'))
        merged = {k: next((p[k] for p in proposals if p.get(k)), None) for k in ('who', 'why', 'what', 'memo')}
        notes = [n for p in proposals for n in p['notes']]
        errors = list(dict.fromkeys(e for p in proposals for e in p['errors']))
        status = 'CONFLICT' if conflicts else 'DOUBT' if errors or not (merged['who'] or merged['why']) else 'MATCH'
        if conflicts:
            errors.append('Casi applicabili propongono valori diversi. Nessuna scelta automatica.')
            merged = dict.fromkeys(('who', 'why', 'what', 'memo'))
        results.append(dict(row, **merged, status=status, steps=notes, issues=errors, alternatives=proposals if conflicts else []))
    return dict(total=len(data['rows']), matched=sum(x['status'] == 'MATCH' for x in results),
                doubtful=sum(x['status'] == 'DOUBT' for x in results), conflicts=sum(x['status'] == 'CONFLICT' for x in results),
                unmatched=unmatched, rows=results, plan_signature=signature(plan))
