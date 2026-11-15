"""Exercise configuration and interview snapshots on a disposable local DB copy."""
import json
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import local_runtime


def main():
    source = local_runtime.existing_database()
    with tempfile.TemporaryDirectory(prefix='rfone-observations-') as directory:
        dbpath = Path(directory) / 'test.db'
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(dbpath)) as dst:
            src.backup(dst)
        with patch.object(local_runtime, 'existing_database', return_value=dbpath), patch.object(local_runtime, 'DATA', Path(directory)):
            app = local_runtime.create_application()
            client = app.test_client()
            host = {'base_url': 'http://127.0.0.1:5096'}
            page = client.get('/selection/configurazioni', **host)
            assert page.status_code == 200
            csrf = re.search(rb'name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
            with closing(sqlite3.connect(dbpath)) as db:
                position, role, location = db.execute('SELECT id,role_code,location_label FROM selection_workspace_positions WHERE id=3').fetchone()
                ids = [r[0] for r in db.execute('SELECT id FROM selection_workspace_position_candidates WHERE position_id=? ORDER BY id', (position,))]
                db.execute('DELETE FROM selection_workspace_proposals WHERE source="INTERVIEW" AND position_candidate_id IN (?,?)', ids[:2])
                db.execute('DELETE FROM selection_workspace_observation_templates')
                db.commit()
            endpoint = '/selection/configurazioni/osservazioni'
            scope = {'role_code': role, 'location': location}
            items = [dict(id='observe', title='Priorità operative', description='Spiega come gestisce richieste simultanee.', question='Due tavoli chiedono aiuto: come procedi?', active=True),
                     dict(id='disabled', title='Voce disattivata', description='Descrizione', question='Domanda da non mostrare?', active=False)]
            def post(operation, **values):
                return client.post(endpoint, data={'csrf_token': csrf, 'payload': json.dumps(dict(scope, operation=operation, **values))}, **host)
            with patch('workspace.rule_ai.generate', return_value={'items': items}) as ai:
                response = post('propose', items=[])
                assert response.status_code == 200, response.data
                assert ai.call_count == 1
            assert client.get(endpoint, query_string=scope, **host).json['items'] == []  # AI never saves
            assert post('save', items=items, version=0).status_code == 200
            assert post('save', items=items, version=0).status_code == 409
            assert post('save', items=[dict(items[0], question='')], version=1).status_code == 422
            assert client.get(endpoint, query_string=dict(scope, location='Winter Park'), **host).json['items'] == []
            interview = f'/selection/posizioni/{position}/interviews?pc={ids[0]}'
            response = client.get(interview, **host)
            assert response.status_code == 200, response.data
            assert items[0]['question'].encode() in response.data
            assert b'Voce disattivata' not in response.data
            assert b'InterviewConfig' not in response.data
            token = re.search(rb'name="observation_snapshot" value="([^"]+)"', response.data).group(1).decode()
            changed = [dict(items[0], title='Modello aggiornato', question='Domanda aggiornata?')]
            assert post('save', items=changed, version=1).status_code == 200
            # A form opened before the model changed saves the observations it actually displayed.
            response = client.post(f'/selection/posizioni/{position}/interviews/{ids[0]}/save', data={
                'csrf_token': csrf, 'autosave': '1', 'observation_snapshot': token,
                'dim_observe_evidence': 'Evidenza conservata', 'dim_observe_rating': 'DEMONSTRATED'}, **host)
            assert response.status_code == 200, response.data
            response = client.get(interview, **host)
            assert items[0]['question'].encode() in response.data
            assert b'Evidenza conservata' in response.data
            assert b'Domanda aggiornata?' not in response.data
            response = client.get(f'/selection/posizioni/{position}/interviews?pc={ids[1]}', **host)
            assert b'Domanda aggiornata?' in response.data
            response = client.post(f'/selection/posizioni/{position}/interviews/{ids[1]}/save', data={
                'csrf_token': csrf, 'autosave': '1', 'observation_snapshot': token}, **host)
            assert response.status_code == 400
            from workspace.routes import _cfg
            _cfg.SessionFactory.kw['bind'].dispose()
    print('PASS: AI proposal without save, explicit save, stale edit protection, validation, site isolation, selected observations/questions, immutable interview snapshot, evidence preservation, cross-candidate token rejection.')


if __name__ == '__main__':
    main()
