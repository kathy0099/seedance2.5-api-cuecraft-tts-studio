"""SQLite persistence. Submission reservations survive browser/server restarts."""
from contextlib import contextmanager
import json
import sqlite3


class Store:
    def __init__(self, root):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / 'cuecraft.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS cues (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, position INTEGER NOT NULL,
                    title TEXT NOT NULL, text TEXT NOT NULL, voice TEXT NOT NULL,
                    speed REAL NOT NULL, selected TEXT);
                CREATE TABLE IF NOT EXISTS takes (
                    id TEXT PRIMARY KEY, cue_id TEXT NOT NULL, token TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL, task_id TEXT, status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '', file TEXT, created TEXT NOT NULL,
                    base_url TEXT NOT NULL);
            ''')
            db.execute("UPDATE takes SET status='UNKNOWN', error='Server stopped during submission. Check RunningHub task history.' WHERE status='SUBMITTING'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def take(self, take_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM takes WHERE id=?', (take_id,)).fetchone()
        if row is None:
            raise KeyError('Take not found')
        value = dict(row)
        value['payload'] = json.loads(value['payload'])
        return value

    def update_take(self, take_id, **values):
        allowed = {'task_id', 'status', 'error', 'file'}
        assert values and set(values) <= allowed
        with self.connect() as db:
            db.execute('UPDATE takes SET ' + ','.join(k + '=?' for k in values) + ' WHERE id=?',
                       (*values.values(), take_id))

    def project(self, project_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
            if row is None:
                raise KeyError('Project not found')
            project = dict(row)
            cues = [dict(r) for r in db.execute('SELECT * FROM cues WHERE project_id=? ORDER BY position', (project_id,))]
            for cue in cues:
                cue['takes'] = [self.take(r['id']) for r in db.execute('SELECT id FROM takes WHERE cue_id=? ORDER BY created DESC', (cue['id'],))]
                for take in cue['takes']:
                    take['stale'] = any(take['payload'][key] != cue[field] for key, field in [('text','text'),('voice_id','voice'),('speed','speed')])
            project['cues'] = cues
        return project
