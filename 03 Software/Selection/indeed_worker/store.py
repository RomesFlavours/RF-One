"""Durable checkpoints, not a résumé archive. Single worker instance per volume."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ACTIVE = ('STARTING', 'WAITING_LOGIN', 'RUNNING', 'STOPPING')


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS items (job TEXT, candidate TEXT, status TEXT, detail TEXT, '
                       'PRIMARY KEY(job,candidate))')
            for row in db.execute('SELECT id,data FROM jobs').fetchall():
                job = json.loads(row[1])
                if job['state'] in ACTIVE:
                    job.update(state='PAUSED', message='Worker restarted; reopen browser and sign in again.')
                    db.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(job), row[0]))

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT data FROM jobs WHERE id=?', (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            job = json.loads(row[0])
            job['items'] = [dict(candidate_id=r[0], status=r[1], detail=r[2]) for r in
                            db.execute('SELECT candidate,status,detail FROM items WHERE job=?', (job_id,))]
            return job

    def jobs(self):
        with self.connect() as db:
            ids = [row[0] for row in db.execute('SELECT id FROM jobs ORDER BY rowid DESC')]
        return [self.get(i) for i in ids]

    def create(self, url, position_id, actor_id):
        job = dict(id=uuid.uuid4().hex, url=url, position_id=position_id, actor_id=actor_id,
                   state='STARTING', message='', created_at=time.time(), generation=uuid.uuid4().hex)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if any(json.loads(r[0])['state'] in ACTIVE for r in db.execute('SELECT data FROM jobs')):
                raise ValueError('Another browser is active; stop it before starting a new request.')
            db.execute('INSERT INTO jobs VALUES (?,?)', (job['id'], json.dumps(job)))
        return job

    def update(self, job_id, **values):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data FROM jobs WHERE id=?', (job_id,)).fetchone()
            job = json.loads(row[0])
            job.update(values)
            db.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(job), job_id))

    def checkpoint(self, job_id, candidate_id, status, detail=''):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO items VALUES (?,?,?,?)',
                       (job_id, candidate_id, status, detail[:500]))
