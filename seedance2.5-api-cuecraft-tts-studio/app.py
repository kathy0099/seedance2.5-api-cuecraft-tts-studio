"""Local-only HTTP application. Run: python app.py."""
from datetime import datetime, timezone
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import threading
import uuid
import zipfile

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file
from werkzeug.exceptions import HTTPException
from cuecraft.provider import RunningHub, ProviderError, VOICES
from cuecraft.store import Store

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')


def identifier():
    return uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


def narration(text, voice, speed):
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
        raise ValueError('Each cue needs 1–2000 characters of text.')
    if voice not in VOICES:
        raise ValueError('Choose a documented voice from the list.')
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed) or not 0.5 <= speed <= 2 or abs(speed * 100 - round(speed * 100)) > 0.00001:
        raise ValueError('Speed must be 0.50–2.00 in steps of 0.01.')
    return {'text': text.strip(), 'voice_id': voice, 'speed': speed, 'volume': 1,
            'pitch': 0, 'emotion': 'neutral', 'enable_base64_output': False,
            'english_normalization': False}


def create_app(data_dir=None, provider=None):
    app = Flask(__name__, static_folder='static', static_url_path='/static')
    app.config['MAX_CONTENT_LENGTH'] = 128 * 1024
    root = Path(data_dir or os.getenv('CUECRAFT_DATA_DIR') or ROOT / 'data')
    store = Store(root)
    provider = provider or RunningHub(os.getenv('RUNNINGHUB_API_KEY', ''), os.getenv('RUNNINGHUB_BASE_URL', 'https://www.runninghub.cn').rstrip('/'))
    app.extensions.update(store=store, provider=provider)
    query_lock = threading.Lock()

    @app.before_request
    def local_guard():
        if request.host.split(':')[0] not in ('127.0.0.1', 'localhost', '[::1]'):
            return jsonify(error='Local host only.'), 403
        if request.method != 'GET':
            origin = request.headers.get('Origin')
            if origin and origin != request.host_url.rstrip('/'):
                return jsonify(error='Cross-origin write rejected.'), 403
            if not request.is_json:
                return jsonify(error='Send application/json.'), 415

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(Exception)
    def error(exception):
        if isinstance(exception, HTTPException):
            return jsonify(error=exception.description), exception.code
        if isinstance(exception, (ValueError, KeyError, ProviderError)):
            return jsonify(error=str(exception)), 400
        # Do not log request bodies, upstream responses, URLs or credentials.
        return jsonify(error='Local operation failed. Check data directory permissions and restart.'), 500

    def body():
        value = request.get_json()
        if not isinstance(value, dict):
            raise ValueError('JSON object required.')
        return value

    @app.get('/')
    def index():
        return send_file(ROOT / 'static/index.html')

    @app.get('/api/config')
    def config():
        return jsonify(configured=bool(provider.key), voices=VOICES, model='speech-02-hd')

    @app.get('/api/projects')
    def projects():
        with store.connect() as db:
            return jsonify([dict(r) for r in db.execute('SELECT * FROM projects ORDER BY created DESC')])

    @app.post('/api/projects')
    def new_project():
        data = body()
        title = data.get('title', '')
        script = data.get('script', '')
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
            raise ValueError('Project title needs 1–100 characters.')
        if not isinstance(script, str) or len(script) > 40000:
            raise ValueError('Script must be text, at most 40,000 characters.')
        parts = [part.strip() for part in re.split(r'\n\s*\n', script.strip()) if part.strip()]
        if not 1 <= len(parts) <= 30:
            raise ValueError('Use 1–30 paragraphs separated by blank lines.')
        for part in parts:
            narration(part, 'Wise_Woman', 1)
        pid = identifier()
        with store.connect() as db:
            db.execute('INSERT INTO projects VALUES (?,?,?)', (pid, title.strip(), now()))
            for i, part in enumerate(parts):
                db.execute('INSERT INTO cues VALUES (?,?,?,?,?,?,?,?)',
                           (identifier(), pid, i, f'Cue {i+1:02}', part, 'Wise_Woman', 1, None))
        return jsonify(store.project(pid)), 201

    @app.get('/api/projects/<pid>')
    def project(pid):
        return jsonify(store.project(pid))

    @app.patch('/api/cues/<cid>')
    def edit_cue(cid):
        data = body()
        payload = narration(data.get('text'), data.get('voice'), data.get('speed'))
        title = data.get('title')
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
            raise ValueError('Cue title needs 1–100 characters.')
        with store.connect() as db:
            result = db.execute('UPDATE cues SET title=?,text=?,voice=?,speed=? WHERE id=?',
                                (title.strip(), payload['text'], payload['voice_id'], payload['speed'], cid))
            if not result.rowcount:
                raise KeyError('Cue not found')
        return jsonify(ok=True)

    @app.post('/api/cues/<cid>/takes')
    def submit(cid):
        data = body()
        token = data.get('token', '')
        if not isinstance(token, str) or not re.fullmatch(r'[a-f0-9-]{32,36}', token):
            raise ValueError('A UUID submission token is required.')
        if not provider.key:
            raise ProviderError('Missing RUNNINGHUB_API_KEY. Configure .env and restart.')
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT id,cue_id FROM takes WHERE token=?', (token,)).fetchone()
            if existing:
                if existing['cue_id'] != cid:
                    raise ValueError('Submission token belongs to another cue.')
                return jsonify(store.take(existing['id']))
            cue = db.execute('SELECT * FROM cues WHERE id=?', (cid,)).fetchone()
            if cue is None:
                raise KeyError('Cue not found')
            active = db.execute("SELECT id FROM takes WHERE cue_id=? AND status IN ('SUBMITTING','UNKNOWN','RUNNING','QUEUED')", (cid,)).fetchone()
            if active:
                raise ValueError('This cue has an unresolved take. Query or attach its task ID first.')
            payload = narration(cue['text'], cue['voice'], cue['speed'])
            tid = identifier()
            db.execute('INSERT INTO takes (id,cue_id,token,payload,status,created,base_url) VALUES (?,?,?,?,?,?,?)',
                       (tid, cid, token, json.dumps(payload, ensure_ascii=False), 'SUBMITTING', now(), provider.base_url))
        try:
            result = provider.submit(payload)
            task_id = result.get('taskId')
            if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', task_id):
                raise ProviderError('No valid task ID received. Check RunningHub history before generating again.', True)
            status = result.get('status')
            if status not in ('QUEUED', 'RUNNING', 'SUCCESS', 'FAILED'):
                status = 'RUNNING'
            # SUCCESS still needs query/download; the task ID is durable first.
            store.update_take(tid, task_id=task_id, status='RUNNING' if status == 'SUCCESS' else status,
                              error='Remote generation failed. Inspect the task in RunningHub.' if status == 'FAILED' else '')
        except ProviderError as exc:
            store.update_take(tid, status='UNKNOWN' if exc.uncertain else 'FAILED', error=str(exc))
        return jsonify(store.take(tid)), 201

    @app.post('/api/takes/<tid>/query')
    def query(tid):
        # Prevent duplicate downloads and selection races across tabs.
        with query_lock:
            take = store.take(tid)
            if take['status'] == 'SUCCESS' and take['file'] and (root / take['file']).is_file():
                return jsonify(take)
            if not take['task_id']:
                raise ValueError('No task ID. Check RunningHub history and attach the matching ID.')
            if take['base_url'] != provider.base_url:
                raise ValueError('Restore the original RUNNINGHUB_BASE_URL before querying this take.')
            try:
                result = provider.query(take['task_id'])
                status = result.get('status')
                if status not in ('QUEUED', 'RUNNING', 'SUCCESS', 'FAILED'):
                    raise ProviderError('Unexpected query response. Retry query later.')
                if status == 'SUCCESS':
                    results = result.get('results')
                    if not isinstance(results, list) or not results or not isinstance(results[0], dict) or not isinstance(results[0].get('url'), str):
                        raise ProviderError('Task succeeded but has no audio URL. Retry query later.')
                    filename = tid + '.mp3'
                    temporary = root / (filename + '.part')
                    try:
                        provider.download(results[0]['url'], temporary)
                        temporary.replace(root / filename)
                    finally:
                        temporary.unlink(missing_ok=True)
                    store.update_take(tid, status='SUCCESS', file=filename, error='')
                    with store.connect() as db:
                        # Select first success automatically; later takes require explicit selection.
                        db.execute('UPDATE cues SET selected=? WHERE id=? AND selected IS NULL', (tid, take['cue_id']))
                else:
                    store.update_take(tid, status=status, error='Remote generation failed. Inspect the task in RunningHub.' if status == 'FAILED' else '')
            except ProviderError as exc:
                store.update_take(tid, error=str(exc))
                return jsonify(take=store.take(tid), error=str(exc)), 502
        return jsonify(store.take(tid))

    @app.post('/api/takes/<tid>/attach')
    def attach(tid):
        take = store.take(tid)
        if take['status'] != 'UNKNOWN' or take['task_id']:
            raise ValueError('Only an unknown submission without a task ID can be recovered this way.')
        task_id = body().get('task_id', '')
        if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', task_id):
            raise ValueError('Enter a valid task ID from RunningHub.')
        store.update_take(tid, task_id=task_id, status='RUNNING', error='')
        return jsonify(store.take(tid))

    @app.post('/api/takes/<tid>/resolve')
    def resolve(tid):
        take = store.take(tid)
        if take['status'] != 'UNKNOWN' or body().get('confirmed_no_task') is not True:
            raise ValueError('First verify in RunningHub that no task exists.')
        store.update_take(tid, status='FAILED', error='User confirmed no remote task. A new take requires a new explicit submission.')
        return jsonify(store.take(tid))

    @app.post('/api/takes/<tid>/select')
    def select(tid):
        take = store.take(tid)
        if take['status'] != 'SUCCESS' or not take['file'] or not (root / take['file']).is_file():
            raise ValueError('Only a locally saved successful take can be selected.')
        with store.connect() as db:
            db.execute('UPDATE cues SET selected=? WHERE id=?', (tid, take['cue_id']))
        return jsonify(ok=True)

    @app.get('/api/takes/<tid>/audio')
    def audio(tid):
        take = store.take(tid)
        if take['status'] != 'SUCCESS' or not take['file']:
            raise ValueError('Audio is not saved yet.')
        return send_file(root / take['file'], mimetype='audio/mpeg', as_attachment=request.args.get('download') == '1', download_name=f'cuecraft-{tid[:8]}.mp3', conditional=True)

    @app.get('/api/projects/<pid>/export')
    def export(pid):
        project = store.project(pid)
        manifest = {'title': project['title'], 'model': 'speech-02-hd', 'cues': []}
        output = BytesIO()
        script = ['# ' + project['title'], '']
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for i, cue in enumerate(project['cues'], 1):
                take = next((t for t in cue['takes'] if t['id'] == cue['selected']), None)
                if not take or take['status'] != 'SUCCESS' or take['stale'] or not take['file'] or not (root / take['file']).is_file():
                    raise ValueError(f'Cue {i} needs a successful selected take matching its saved text, voice and speed.')
                filename = f'{i:02d}-{cue["id"][:8]}.mp3'
                archive.write(root / take['file'], filename)
                manifest['cues'].append({'title': cue['title'], 'file': filename, 'task_id': take['task_id'], 'settings': take['payload']})
                script.extend(['## ' + cue['title'], cue['text'], ''])
            archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.writestr('script.md', '\n'.join(script))
        output.seek(0)
        return send_file(output, mimetype='application/zip', as_attachment=True, download_name='cuecraft-narration-kit.zip')

    return app


if __name__ == '__main__':
    port = int(os.getenv('PORT', '8791'))
    print(f'CueCraft — http://127.0.0.1:{port} (local use only)')
    create_app().run(host='127.0.0.1', port=port, debug=False, threaded=True)
