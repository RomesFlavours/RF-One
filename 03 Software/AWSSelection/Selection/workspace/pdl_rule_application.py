"""Apply active, role-scoped rules to existing CV facts; no writes or AI calls."""
from sqlalchemy import select
from rfone_data_store.selection import persistence
from rfone_data_store.selection.analysis import analyze_candidate
from .pdl_rule_store import PDLRule
from . import pdl_rule_engine as engine, pdl_cv_fields as cv


def facts(profile, role_code):
    result = cv.profile_facts(profile)
    view = analyze_candidate(profile, target_role=role_code)
    dated = any(w.start_date and (w.end_date or w.is_current) for w in profile.work_history)
    result['direct_months'] = view.breakdown.direct_role_months if view.role_config and dated else None
    result['propedeutic_months'] = view.breakdown.relevant_propedeutic_months if view.role_config and dated else None
    stability = next((i.state for i in view.indicators if i.name == 'Stability'), None)
    result['stability'] = stability if stability in ('Strong', 'Moderate', 'Weak') else None
    # Absence of a declared coordination duty is not evidence of inability.
    result['coordination'] = True if view.coordination_evidence else None
    return result


def assess(rules, candidate_facts):
    details = []
    for rule in rules:
        condition = engine.validate_condition(rule.condition)
        outcome = engine.evaluate(condition, candidate_facts)
        details.append({'id': rule.id, 'title': rule.title, 'section': rule.section,
                        'condition': engine.describe(condition), 'outcome': outcome,
                        'weight': rule.weight})
    unfit = any(d['outcome'] is True and d['section'] == 'requirements' for d in details)
    unknown = any(d['outcome'] is None for d in details)
    return {'active': bool(rules), 'unfit': unfit, 'unknown': unknown,
            'status': 'UnFit' if unfit else 'Da chiarire' if unknown else 'Compatibile',
            'priority': sum(d['weight'] for d in details if d['section'] == 'priorities' and d['outcome'] is True),
            'details': details}


def order(rows):
    """Stable ties retain prior/manual order; confirmed UnFit always remains last."""
    from .old_screening import enabled
    if enabled():
        return rows
    if not any(r.get('pdl_result', {}).get('active') for r in rows):
        return rows
    return sorted(rows, key=lambda r: (r['pdl_result']['unfit'], -r['pdl_result']['priority']))


def apply(db, position, rows):
    from . import conversational_rules as conversation,position_settings
    natural=conversation.active(db,position.role_code)
    if natural:
        saved=position_settings.context(position).get('pdl_filter_run',{})
        results=saved.get('results',{}) if saved.get('mode')=='natural_language' else {}
        for row in rows:
            row['pdl_result']=results.get(str(row['pc'].id),{'active':True,'unfit':False,'unknown':True,'priority':0,'status':'Da valutare con AI','details':[]})
        return order(rows)
    from . import old_screening
    if old_screening.enabled():
        return old_screening.decorate(db, position, rows)
    rules = list(db.scalars(select(PDLRule).where(PDLRule.role_code == position.role_code,
                                                PDLRule.is_active.is_(True)).order_by(PDLRule.id)))
    for row in rows:
        if not rules:
            row['pdl_result'] = assess([], {})
            continue
        pc = row['pc']
        candidate = persistence.get_candidate(db, pc.candidate_id)
        data = facts(persistence.to_profile(candidate), position.role_code) if candidate else {}
        row['pdl_result'] = assess(rules, data)
    return order(rows)
