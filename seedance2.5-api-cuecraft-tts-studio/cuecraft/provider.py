"""Verified RunningHub speech contract; no automatic paid retries."""
import ipaddress
import socket
from urllib.parse import urlparse, urljoin

import requests

SUBMIT_PATH = '/openapi/v2/rhart-audio/text-to-audio/speech-02-hd'
QUERY_PATH = '/openapi/v2/query'
VOICES = ['Wise_Woman', 'Friendly_Person', 'Inspirational_girl', 'Deep_Voice_Man',
          'Calm_Woman', 'Casual_Guy', 'Lively_Girl', 'Patient_Man', 'Young_Knight',
          'Determined_Man', 'Lovely_Girl', 'Decent_Boy', 'Imposing_Manner',
          'Elegant_Man', 'Abbess', 'Sweet_Girl_2', 'Exuberant_Girl']


class ProviderError(Exception):
    def __init__(self, message, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


class RunningHub:
    def __init__(self, key, base_url):
        if base_url not in ('https://www.runninghub.cn', 'https://www.runninghub.ai'):
            raise ValueError('RUNNINGHUB_BASE_URL must be the official .cn or .ai HTTPS origin.')
        self.key = key
        self.base_url = base_url

    def post(self, path, payload, submitting=False):
        if not self.key:
            raise ProviderError('Missing RUNNINGHUB_API_KEY. Configure .env and restart.')
        try:
            response = requests.post(
                self.base_url + path, json=payload,
                headers={'Authorization': 'Bearer ' + self.key},
                timeout=(10, 60), allow_redirects=False)
        except requests.RequestException:
            raise ProviderError('Network error or timeout. Query an existing task; do not blindly submit again.', submitting)
        if response.status_code in (401, 403):
            raise ProviderError('RunningHub authentication or model permission denied.')
        if not 200 <= response.status_code < 300:
            raise ProviderError(f'RunningHub HTTP {response.status_code}. Check the console before another submission.', submitting)
        try:
            data = response.json()
        except ValueError:
            raise ProviderError('RunningHub returned invalid JSON.', submitting)
        if not isinstance(data, dict):
            raise ProviderError('Unexpected RunningHub response.', submitting)
        return data

    def submit(self, payload):
        return self.post(SUBMIT_PATH, payload, submitting=True)

    def query(self, task_id):
        return self.post(QUERY_PATH, {'taskId': task_id})

    def download(self, url, destination):
        """Only public HTTPS targets, bounded redirects/size; never send API auth to CDN."""
        for _ in range(4):
            parsed = urlparse(url)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                raise ProviderError('Audio URL must be public HTTPS.')
            try:
                addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
                if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                    raise ProviderError('Private audio URL rejected.')
                with requests.get(url, stream=True, timeout=(10, 45), allow_redirects=False) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get('Location', ''))
                        continue
                    response.raise_for_status()
                    total = 0
                    with open(destination, 'wb') as output:
                        for chunk in response.iter_content(65536):
                            total += len(chunk)
                            if total > 50 * 1024 * 1024:
                                raise ProviderError('Audio exceeds the local 50 MiB download limit.')
                            output.write(chunk)
                if total < 4:
                    raise ProviderError('Empty audio output.')
                # MP3 is the documented output. Reject JSON/HTML masquerading as audio.
                with open(destination, 'rb') as source:
                    prefix = source.read(3)
                if not (prefix == b'ID3' or (prefix[0] == 255 and prefix[1] & 224 == 224)):
                    raise ProviderError('Expected an MP3 output; received another file format.')
                return
            except (requests.RequestException, OSError):
                raise ProviderError('Could not save audio. Retry query/download; it will not generate again.')
        raise ProviderError('Too many audio download redirects.')
