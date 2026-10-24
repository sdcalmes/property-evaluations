"""Public-source capture with resumable caches and explicit access failures."""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temp.replace(path)


def fetch_bytes(url, attempts=3):
    if urlsplit(url).scheme not in ('http', 'https'):
        raise ValueError('Source must use http or https')
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'PropertyEvaluationResearch/1.0', 'Accept': '*/*'}), timeout=45) as response:
                return response.read(), response.headers.get('Content-Type', '')
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise RuntimeError(f'HTTP {exc.code}: {url}') from exc
        except (URLError, TimeoutError) as exc:
            if attempt == attempts - 1:
                raise RuntimeError(f'Network failure: {url}: {exc}') from exc
        time.sleep(2 ** attempt)


class JSONCapture:
    """Cache entries: {source_url, captured_at, response}. Never cache API errors.

    Blocked HTTP: open pending-request.json's URL in an authorized browser,
    save its JSON response with provenance at cache_path, then rerun.
    """
    def __init__(self, directory, refresh=False):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.refresh = refresh
        self.sources = []

    def get(self, endpoint, params=None):
        url = endpoint + ('?' + urlencode(sorted(params.items())) if params else '')
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.directory / f'{key}.json'
        cached = path.exists() and not self.refresh
        if cached:
            entry = json.loads(path.read_text())
            if entry.get('source_url') != url or not entry.get('captured_at'):
                raise ValueError(f'Invalid provenance in {path}')
        else:
            write_json(self.directory / 'pending-request.json', {
                'source_url': url, 'cache_path': str(path),
                'instructions': 'Save {source_url, captured_at (actual UTC timestamp), response (JSON object)} at cache_path; rerun without --refresh.'})
            raw, _ = fetch_bytes(url)
            try:
                response = json.loads(raw)
            except ValueError as exc:
                raise ValueError('Expected JSON; access/challenge page is not GIS data') from exc
            entry = {'source_url': url, 'captured_at': now(), 'response': response}
        data = entry['response']
        if not isinstance(data, dict) or 'error' in data:
            raise ValueError(f'ArcGIS/API error at {url}: {data}')
        if not cached:
            write_json(path, entry)
        self.sources.append({k: entry[k] for k in ('source_url', 'captured_at')})
        return data


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Import a browser-retrieved JSON response for a pending capture')
    parser.add_argument('--pending', required=True)
    parser.add_argument('--response', required=True, help='Raw saved response JSON, not HTML or cache wrapper')
    parser.add_argument('--captured-at', required=True, help='Actual ISO-8601 UTC capture timestamp')
    args = parser.parse_args()
    captured_at = datetime.fromisoformat(args.captured_at.replace('Z', '+00:00'))
    if captured_at.tzinfo is None:
        parser.error('Timestamp must include a timezone')
    pending = json.loads(Path(args.pending).read_text())
    response = json.loads(Path(args.response).read_text())
    if not isinstance(response, dict) or 'error' in response:
        parser.error('Response is not successful API JSON')
    write_json(pending['cache_path'], {'source_url': pending['source_url'],
               'captured_at': captured_at.isoformat(), 'response': response})
    print(pending['cache_path'])


if __name__ == '__main__':
    main()
