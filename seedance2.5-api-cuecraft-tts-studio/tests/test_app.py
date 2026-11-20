"""Offline integration checks using the real Flask routes and SQLite store."""
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
import uuid
import zipfile
from unittest.mock import patch

from app import create_app
from cuecraft.provider import ProviderError, RunningHub


class FakeProvider:
    key = 'test-placeholder'
    base_url = 'https://www.runninghub.cn'

    def __init__(self):
        self.submissions = 0
        self.queries = 0
        self.mode = 'success'
        self.payloads = []

    def submit(self, payload):
        self.submissions += 1
        self.payloads.append(payload)
        if self.mode == 'timeout':
            raise ProviderError('Submission timed out.', True)
        if self.mode == 'auth':
            raise ProviderError('Authentication denied.')
        return {'taskId': 'offline-task', 'status': 'RUNNING', 'results': None}

    def query(self, task_id):
        self.queries += 1
        if self.mode == 'query-error':
            raise ProviderError('Query network timeout.')
        if self.mode == 'failed':
            return {'status': 'FAILED', 'results': None}
        if self.mode == 'empty':
            return {'status': 'SUCCESS', 'results': []}
        return {'taskId': task_id, 'status': 'SUCCESS', 'results': [{'url': 'https://example.com/test.mp3', 'outputType': 'mp3'}]}

    def download(self, url, destination):
        if self.mode == 'download-error':
            raise ProviderError('Download failed.')
        destination.write_bytes(b'ID3' + b'fixture' * 100)


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.provider = FakeProvider()
        self.app = create_app(self.temp.name, self.provider)
        self.client = self.app.test_client()
        self.project = self.client.post('/api/projects', json={'title': 'Test', 'script': 'Welcome to the gallery.'}).get_json()
        self.cid = self.project['cues'][0]['id']
        self.pid = self.project['id']

    def tearDown(self):
        self.temp.cleanup()

    def submit(self, token=None):
        return self.client.post(f'/api/cues/{self.cid}/takes', json={'token': token or str(uuid.uuid4())})

    def test_submit_dedup_query_and_export(self):
        token = str(uuid.uuid4())
        first = self.submit(token).get_json()
        second = self.submit(token).get_json()
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(self.provider.submissions, 1)
        self.assertEqual(self.provider.payloads[0]['enable_base64_output'], False)
        result = self.client.post(f'/api/takes/{first["id"]}/query', json={})
        self.assertEqual(result.get_json()['status'], 'SUCCESS')
        self.assertEqual(self.provider.submissions, 1)
        export = self.client.get(f'/api/projects/{self.pid}/export')
        self.assertEqual(export.status_code, 200)
        with zipfile.ZipFile(BytesIO(export.data)) as archive:
            self.assertIn('script.md', archive.namelist())
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['cues'][0]['settings']['text'], 'Welcome to the gallery.')
            self.assertTrue(any(n.endswith('.mp3') for n in archive.namelist()))
        # Already saved audio never re-queries or re-submits.
        self.client.post(f'/api/takes/{first["id"]}/query', json={})
        self.assertEqual(self.provider.queries, 1)

    def test_unknown_blocks_new_generation_and_attaches(self):
        self.provider.mode = 'timeout'
        take = self.submit().get_json()
        self.assertEqual(take['status'], 'UNKNOWN')
        self.assertEqual(self.submit().status_code, 400)
        self.provider.mode = 'success'
        self.client.post(f'/api/takes/{take["id"]}/attach', json={'task_id': 'recovered-task'})
        self.client.post(f'/api/takes/{take["id"]}/query', json={})
        self.assertEqual(self.provider.submissions, 1)
        self.assertEqual(self.app.extensions['store'].take(take['id'])['status'], 'SUCCESS')

    def test_restart_preserves_records_and_marks_inflight_unknown(self):
        take = self.submit().get_json()
        self.app.extensions['store'].update_take(take['id'], status='SUBMITTING', task_id=None)
        restarted = create_app(self.temp.name, self.provider)
        self.assertEqual(restarted.extensions['store'].take(take['id'])['status'], 'UNKNOWN')
        self.assertEqual(len(restarted.test_client().get('/api/projects').get_json()), 1)

    def test_changed_draft_blocks_stale_export(self):
        take = self.submit().get_json()
        self.client.post(f'/api/takes/{take["id"]}/query', json={})
        response = self.client.patch(f'/api/cues/{self.cid}', json={'title': 'Changed', 'text': 'New script.', 'voice': 'Wise_Woman', 'speed': 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(f'/api/projects/{self.pid}/export').status_code, 400)
        project = self.client.get(f'/api/projects/{self.pid}').get_json()
        self.assertTrue(project['cues'][0]['takes'][0]['stale'])

    def test_query_failures_never_resubmit(self):
        take = self.submit().get_json()
        for mode in ['query-error', 'empty', 'download-error']:
            self.provider.mode = mode
            self.assertEqual(self.client.post(f'/api/takes/{take["id"]}/query', json={}).status_code, 502)
        self.provider.mode = 'success'
        self.assertEqual(self.client.post(f'/api/takes/{take["id"]}/query', json={}).get_json()['status'], 'SUCCESS')
        self.assertEqual(self.provider.submissions, 1)
        self.assertFalse(list(Path(self.temp.name).glob('*.part')))

    def test_remote_failure_and_auth_feedback(self):
        self.provider.mode = 'auth'
        self.assertEqual(self.submit().get_json()['status'], 'FAILED')
        self.provider.mode = 'success'
        take = self.submit().get_json()
        self.provider.mode = 'failed'
        self.assertEqual(self.client.post(f'/api/takes/{take["id"]}/query', json={}).get_json()['status'], 'FAILED')

    def test_invalid_inputs_and_missing_key(self):
        for speed in [0, 3, True, 1.001, '1']:
            self.assertEqual(self.client.patch(f'/api/cues/{self.cid}', json={'title':'T','text':'Text','voice':'Wise_Woman','speed':speed}).status_code, 400)
        self.assertEqual(self.client.post('/api/projects',json={'title':'T','script':'x'*2001}).status_code,400)
        self.assertEqual(self.client.post('/api/projects',json={'title':'T','script':'\n\n'.join(['x']*31)}).status_code,400)
        self.provider.key = ''
        self.assertEqual(self.submit().status_code,400)
        self.assertEqual(self.provider.submissions,0)

    def test_local_origin_and_public_assets(self):
        self.assertEqual(self.client.post('/api/projects',json={},headers={'Origin':'https://other.example'}).status_code,403)
        self.assertEqual(self.client.get('/',headers={'Host':'evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/.env').status_code,404)
        self.assertEqual(self.client.get('/api/config').get_json()['configured'],True)
        self.assertNotIn('test-placeholder',self.client.get('/api/config').get_data(as_text=True))
        with self.client.get('/') as response:
            self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])

    def test_download_rejects_private_targets(self):
        provider = RunningHub('test','https://www.runninghub.cn')
        with self.assertRaises(ProviderError):
            provider.download('http://example.com/test.mp3',Path(self.temp.name)/'out')
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ProviderError):
                provider.download('https://localhost/test.mp3',Path(self.temp.name)/'out')

    def test_crash_response_token_reuse(self):
        self.provider.mode='timeout'
        token=str(uuid.uuid4())
        take=self.submit(token).get_json()
        again=self.submit(token).get_json()
        self.assertEqual(take['id'],again['id'])
        self.assertEqual(self.provider.submissions,1)
        self.assertEqual(self.client.post(f'/api/takes/{take["id"]}/resolve',json={'confirmed_no_task':False}).status_code,400)
        self.assertEqual(self.client.post(f'/api/takes/{take["id"]}/resolve',json={'confirmed_no_task':True}).status_code,200)


if __name__ == '__main__':
    unittest.main()
