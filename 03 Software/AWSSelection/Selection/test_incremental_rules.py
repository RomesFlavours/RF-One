"""Disposable SQLite: exact AI call sets, durable cache and incremental ranking."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace as NS
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'RF-One Data Store')]
os.environ['RFONE_SELECTION_ENGINE'] = 'conversation'
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from flask import Flask
from rfone_data_store import models as m
from rfone_data_store.selection import workspace_models as ps
from workspace import incremental_rules as inc, conversational_rules as conversation, position_settings
from workspace.pdl_rule_store import PDLRule
from workspace.schema import REQUIRED_TABLES


with tempfile.TemporaryDirectory(prefix='selection_incremental_') as tmp:
    engine = create_engine('sqlite:///' + str(Path(tmp) / 'test.db'), poolclass=NullPool)
    tables = [t for name, t in m.Base.metadata.tables.items()
        if name in REQUIRED_TABLES or name.startswith('selection_workspace_')]
    m.Base.metadata.create_all(engine, tables=tables)
    factory = sessionmaker(engine, expire_on_commit=False)
    calls, summaries, reports = [], [], []
    fail_summary = False
    fail_report = False

    def ai(prompt):
        marker = '{"task": "cv_observations"'
        if marker in prompt:
            data = json.loads(prompt[prompt.index(marker):]); reports.append(data)
            if fail_report:raise RuntimeError('Synthetic report failure')
            quote = data['CV'].splitlines()[0] if 'CV' in data else data['previous_summary'][0]['bullets'][0]['quotes'][0]
            return {'sections':[{'key':key,'bullets':[{'text':'Osservazione sintetica '+key,'quotes':[quote],'uncertain':False}]} for key in ('profile','strengths','limits','clarifications','conclusion')]}
        data = json.loads(prompt[prompt.index('{"PDL":'):])
        if 'CV' not in data:
            summaries.append(data)
            assert 'CV' not in data
            if fail_summary:
                raise RuntimeError('Synthetic summary failure')
            outcomes = [d.get('ai_outcome') for d in data['validated_results'] if d['section'] == 'priorities']
            return {'priority': 'HIGH' if 'ALTA' in outcomes else 'LOW' if 'BASSA' in outcomes else 'UNCLEAR', 'reason': 'Sintesi degli esiti validi.'}
        calls.append((data['CV'].splitlines()[0], [r['id'] for r in data['rules']]))
        rows = []
        for rule in data['rules']:
            outcome = ('NON_IN_LINEA' if 'reject' in rule['instruction'] else 'IN_LINEA') if rule['section'] == 'requirements' else ('ALTA' if data['CV'].startswith('Second') else 'BASSA') if rule['instruction'] == 'prefer_second' else ('BASSA' if 'low' in rule['instruction'] else 'ALTA')
            rows.append({'id': rule['id'], 'outcome': outcome, 'reason': 'Evidenza sintetica.', 'quotes': [data['CV'].splitlines()[0]]})
        return {'priority': 'HIGH' if any(r['outcome'] == 'ALTA' for r in rows) else 'LOW' if any(r['outcome'] == 'BASSA' for r in rows) else 'UNCLEAR', 'reason': 'Valutazione sintetica.', 'rules': rows}

    with factory() as db:
        position = ps.Position(title='Synthetic research', role_code='TEST', location_label='Synthetic', timezone='America/New_York', manager_account_id=1, created_by_account_id=1, requirement_set_id=1)
        db.add(position); db.flush(); pid = position.id

        def add_rule(title, section='requirements', instruction='accept', role=None, overrides=None):
            rule = PDLRule(role_code=role, overrides_rule_id=overrides, title=title, section=section,
                condition={'op': 'natural_language', 'need': 'Synthetic need', 'instruction': instruction},
                weight=1, conversation=[], proposal_key=title, created_by=1)
            db.add(rule); db.flush(); return rule.id

        r1 = add_rule('General requirement')
        r2 = add_rule('Local priority', 'priorities', 'high', 'TEST')
        pcs, raws = [], []

        def add_cv(name):
            raw = m.RawResume(source_type='LOCAL_UPLOAD', raw_text=name + '\nSynthetic CV evidence.'); db.add(raw); db.flush()
            candidate = m.Candidate(full_name=name, raw_resume_id=raw.id); db.add(candidate); db.flush()
            person = m.CandidatePerson(full_name=name); db.add(person); db.flush()
            application = m.Application(person_id=person.id, candidate_id=candidate.id, target_role='TEST'); db.add(application); db.flush()
            pc = ps.PositionCandidate(position_id=pid, application_id=application.id, candidate_id=candidate.id, channel='MANUAL_UPLOAD'); db.add(pc); db.flush()
            pcs.append(pc.id); raws.append(raw.id)

        add_cv('First synthetic'); add_cv('Second synthetic'); db.commit()

    def apply():
        with factory() as db:
            run = inc.prepare(db, db.get(ps.Position, pid), NS(name='Synthetic owner'))
            db.commit(); run_id = run['run_id']
        conversation._worker(factory, pid, run_id)
        with factory() as db:
            return position_settings.context(db.get(ps.Position, pid))['pdl_filter_run']

    with patch.object(conversation.rule_ai, 'generate', side_effect=ai):
        run = apply(); assert run['state'] == 'COMPLETED'
        assert calls == [('First synthetic', [r1, r2]), ('Second synthetic', [r1, r2])]
        assert len(reports)==2
        reports.clear();calls.clear(); run = apply(); assert not calls and not summaries and not reports
        assert len(run['results']) == 2
        # Missing extended synthesis is its own task: never reevaluate valid rules.
        with factory() as db:
            position=db.get(ps.Position,pid);context=position_settings.context(position)
            context['pdl_filter_run']['rule_cache'][str(pcs[0])].pop('cv_observations')
            position.organization_context_json=json.dumps(context);db.commit()
        fail_report=True;run=apply()
        assert run['state']=='PARTIAL' and len(run['results'])==2 and not calls and not summaries
        fail_report=False;reports.clear();run=apply()
        assert run['state']=='COMPLETED' and not calls and not summaries and len(reports)==1
        reports.clear()

        with factory() as db:
            r3 = add_rule('New requirement'); db.commit()
        run = apply(); assert all(ids == [r3] for _, ids in calls) and len(calls) == 2
        assert len(summaries) == 2
        assert len(reports)==2 and all('CV' not in request for request in reports)
        reports.clear()
        calls.clear(); summaries.clear()

        with factory() as db:
            rule = db.get(PDLRule, r1); rule.condition = dict(rule.condition, instruction='reject'); db.commit()
        run = apply(); assert len(calls) == 2 and all(ids == [r1] for _, ids in calls)
        assert all(result['unfit'] for result in run['results'].values())
        calls.clear(); summaries.clear()

        with factory() as db: db.get(PDLRule, r1).is_active = False; db.commit()
        run = apply(); assert not calls and all(not r['unfit'] for r in run['results'].values())
        assert all(r1 not in [d['id'] for d in r['details']] for r in run['results'].values())
        summaries.clear()
        with factory() as db: db.get(PDLRule, r1).is_active = True; db.commit()
        run = apply(); assert not calls, 'Unchanged reactivated judgment was reread'
        summaries.clear()

        with factory() as db: db.get(m.RawResume, raws[0]).raw_text = 'First updated\nNew CV evidence.'; db.commit()
        run = apply(); assert calls == [('First updated', [r1, r3, r2])], calls
        calls.clear()
        with factory() as db: add_cv('Third synthetic'); db.commit()
        run = apply(); assert calls == [('Third synthetic', [r1, r3, r2])], calls
        calls.clear()

        # A local override replaces just the general pair; retained rules survive.
        with factory() as db:
            override = add_rule('Override', instruction='accept', role='TEST', overrides=r1); db.commit()
        run = apply(); assert len(calls) == 3 and all(ids == [override] for _, ids in calls)
        calls.clear(); summaries.clear()
        with factory() as db: db.get(PDLRule, override).is_active = False; db.commit()
        run = apply(); assert not calls and all(r['unfit'] for r in run['results'].values())

        # Synthesis failure does not discard newly validated rule judgments.
        with factory() as db:
            r4 = add_rule('Another priority', 'priorities', 'low'); db.commit()
        fail_summary = True
        run = apply(); assert run['state'] == 'PARTIAL' and len(calls) == 3
        assert all(ids == [r4] for _, ids in calls)
        calls.clear(); fail_summary = False
        run = apply(); assert run['state'] == 'COMPLETED' and not calls

        # Actual ranking uses combined current judgments (no decisions modified).
        from workspace.candidate_board import board_rows
        web = Flask(__name__)
        with factory() as db:
            rule = db.get(PDLRule, r1); rule.is_active = False
            rule = db.get(PDLRule, r2); rule.condition = dict(rule.condition, instruction='prefer_second')
            db.commit()
        apply()
        assert len(calls) == 3 and all(ids == [r2] for _, ids in calls)
        calls.clear()
        with web.test_request_context('/selection/'):
            with factory() as db:
                rows = board_rows(db, db.get(ps.Position, pid))
                assert len(rows) == 3 and all(not r['result']['unfit'] for r in rows)
                assert [r['pc'].id for r in rows] == [pcs[1], pcs[0], pcs[2]], 'Ranking did not incorporate the changed preference'
                assert not list(db.scalars(select(ps.Decision)))

        # A replacement snapshot during an in-flight call is drained by the
        # same worker; the obsolete call must not overwrite the new snapshot.
        with factory() as db:
            r5 = add_rule('In-flight rule'); db.commit()
            run = inc.prepare(db, db.get(ps.Position, pid), NS(name='Synthetic owner')); db.commit()
            old_run_id = run['run_id']
        entered, release = threading.Event(), threading.Event()
        def delayed_ai(prompt):
            if not entered.is_set():
                entered.set()
                assert release.wait(10)
            return ai(prompt)
        with patch.object(conversation.rule_ai, 'generate', side_effect=delayed_ai):
            conversation.dispatch(factory, pid, old_run_id)
            assert entered.wait(10)
            with factory() as db:
                rule = db.get(PDLRule, r5); rule.condition = dict(rule.condition, instruction='reject')
                db.commit()
                replacement = inc.prepare(db, db.get(ps.Position, pid), NS(name='Synthetic owner')); db.commit()
            assert replacement['run_id'] != old_run_id
            conversation.dispatch(factory, pid, replacement['run_id'])
            release.set()
            thread = conversation._jobs.get(pid)
            if thread: thread.join(15); assert not thread.is_alive()
        with factory() as db:
            current = position_settings.context(db.get(ps.Position, pid))['pdl_filter_run']
        assert current['run_id'] == replacement['run_id'] and current['state'] == 'COMPLETED'
        assert all(result['unfit'] for result in current['results'].values())
        calls.clear(); summaries.clear()

        # Changed text while AI is running cannot be cached as the current CV.
        with factory() as db:
            db.get(m.RawResume, raws[0]).raw_text = 'First before race\nSynthetic'; db.commit()
        def changed_cv_ai(prompt):
            with factory() as db:
                db.get(m.RawResume, raws[0]).raw_text = 'First after race\nSynthetic'; db.commit()
            return ai(prompt)
        with patch.object(conversation.rule_ai, 'generate', side_effect=changed_cv_ai):
            run = apply()
        assert run['state'] == 'PARTIAL' and str(pcs[0]) in run['errors']
        calls.clear(); run = apply()
        assert run['state'] == 'COMPLETED' and len(calls) == 1 and calls[0][0] == 'First after race'
        calls.clear()

        # Missing text is a cached unknown, not zero experience or a rejection.
        with factory() as db:
            add_cv('Empty synthetic'); db.get(m.RawResume, raws[-1]).raw_text = ''; db.commit()
        run = apply(); assert not calls
        assert run['results'][str(pcs[-1])]['unknown'] and not run['results'][str(pcs[-1])]['unfit']
        run = apply(); assert not calls
        with factory() as db: db.get(m.RawResume, raws[-1]).raw_text = 'Completed synthetic\nReadable CV'; db.commit()
        run = apply(); assert len(calls) == 1 and calls[0][0] == 'Completed synthetic'
        calls.clear()

        # A first narrative failure must not hide valid new-candidate ranking.
        with factory() as db: add_cv('Report retry synthetic'); db.commit()
        fail_report=True;run=apply()
        assert run['state']=='PARTIAL' and str(pcs[-1]) in run['results'] and len(calls)==1
        calls.clear();fail_report=False;run=apply()
        assert run['state']=='COMPLETED' and not calls

        # No rules requires no provider and removes previous classifications.
        with factory() as db:
            for rule in db.scalars(select(PDLRule)): rule.is_active = False
            db.commit()
        summaries.clear(); run = apply(); assert not calls and not summaries
        assert all(not r['active'] and not r['unfit'] for r in run['results'].values())
    engine.dispose()
print('PASS: persisted CV observations, report-only recovery with no rule reevaluation, cached report updates without CV rereading; exact candidate/rule calls; no-op repeat; added/edited/deactivated/reactivated/overridden rules; new/changed CV; durable synthesis retry; current ranking; no human decisions or AWS changes')
