"""Shared helpers for the 11 acceptance runner: black-box HTTP only (stdlib), read-only by default.

Env: SPARKMD_TEST_URL (default http://127.0.0.1:8100), SPARKMD_SANDBOX_ADDR (10.77.0.1),
SPARKMD_RECORDING=1 (also read from the worker's own environment), SPARKMD_QA_NO_SANDBOX=1.
Nothing here confirms or approves a report; the only POSTs are 403/404 probes that the gates reject first.
"""
import json
import os
import re
import subprocess
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

BASE = os.environ.get('SPARKMD_TEST_URL', 'http://127.0.0.1:8100').rstrip('/')
PORT = urllib.parse.urlparse(BASE).port or 80
SANDBOX_ADDR = os.environ.get('SPARKMD_SANDBOX_ADDR', '10.77.0.1')
LLM_URL = os.environ.get('SPARKMD_LLM_URL', 'http://127.0.0.1:8000/v1').rstrip('/')
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
STATUS_ORDER = ['received', 'organized', 'analyzing', 'awaiting_confirmation', 'analyzed', 'reported', 'approved']
PRIORITY_RANK = {'urgent': 0, 'elevated': 1, 'routine': 2}


def http(path, body=None, *, base=None, method=None, agent=False, timeout=15):
    """-> (status, parsed JSON or text or None, headers). Never raises on HTTP errors."""
    headers = {'Content-Type': 'application/json'}
    if agent:
        headers['X-SparkMD-Caller'] = 'agent'
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request((base or BASE) + path, data, headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        resp = exc
    with resp:
        raw = resp.read()
        head = {k.lower(): v for k, v in resp.headers.items()}
    try:
        return resp.status, (json.loads(raw) if raw else None), head
    except ValueError:
        return resp.status, raw.decode('utf-8', 'replace'), head


def get(path, **kw):
    return http(path, **kw)


def sandbox_base():
    return f'http://{SANDBOX_ADDR}:{PORT}'


def worker_env():
    """The worker process's environment (same user), or {} when unreadable."""
    try:
        out = subprocess.run(['ss', '-ltnpH', f'sport = :{PORT}'], capture_output=True, text=True, timeout=5).stdout
        pid = re.search(r'pid=(\d+)', out)
        if not pid:
            return {}
        raw = open(f'/proc/{pid.group(1)}/environ', 'rb').read().split(b'\0')
        return dict(item.decode().split('=', 1) for item in raw if b'=' in item)
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}


def recording():
    """True when the worker or this shell is in the recording state, or a replay is live."""
    if os.environ.get('SPARKMD_RECORDING') == '1' or worker_env().get('SPARKMD_RECORDING') == '1':
        return True
    try:
        state = get('/api/demo/state')[1]
        return bool(isinstance(state, dict) and state.get('replaying'))
    except OSError:
        return False


def ts(value):
    return datetime.fromisoformat(value) if value else None


class Data:
    """Cached read-only views of the worker. One instance per run."""

    def __init__(self):
        self._cache = {}

    def _once(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    def worklist(self):
        return self._once('worklist', lambda: get('/api/worklist')[1])

    def study(self, uid):
        return self._once(('study', uid), lambda: get(f'/api/studies/{uid}')[1])

    def findings(self, uid):
        return self._once(('findings', uid), lambda: get(f'/api/studies/{uid}/findings')[1])

    def agent_findings(self, uid):
        return self._once(('afind', uid), lambda: get(f'/api/studies/{uid}/findings', agent=True)[1])

    def reports(self, uid):
        return self._once(('reports', uid), lambda: get(f'/api/studies/{uid}/reports')[1])

    def log(self):
        return self._once('log', lambda: get('/api/agent-log?limit=2000')[1])

    def outbox(self):
        return self._once('outbox', lambda: get('/api/outbox')[1])

    def demo(self):
        return self._once('demo', lambda: get('/api/demo/state')[1])

    def latest_reports(self, uid):
        """Latest version per kind."""
        best = {}
        for r in self.reports(uid) or []:
            if r['kind'] not in best or r['version'] > best[r['kind']]['version']:
                best[r['kind']] = r
        return best

    def confirmed(self, uid):
        f = self.findings(uid)
        return bool(f['nodules']) and not f.get('pending_confirmation') and all(n['confirmation']['confirmed'] for n in f['nodules'])


DATA = Data()


def sandbox_checks():
    """Run agent/tests/acceptance.sh (no LLM) once; -> {check id: ('PASS'|'FAIL', text)} or a skip reason string."""
    if 'sbx' in DATA._cache:
        return DATA._cache['sbx']
    script = os.path.join(REPO, 'agent', 'tests', 'acceptance.sh')
    if os.environ.get('SPARKMD_QA_NO_SANDBOX') == '1':
        out = 'SPARKMD_QA_NO_SANDBOX=1'
    elif recording():
        out = 'recording state: no sandbox probes'
    elif not os.path.exists(script):
        out = 'agent/tests/acceptance.sh not present'
    else:
        try:
            run = subprocess.run(['bash', script], capture_output=True, text=True, timeout=240, cwd=REPO)
            out = {}
            for line in run.stdout.splitlines():
                m = re.match(r'(PASS|FAIL) (A\d+)\s+(.*)', line)
                if m:
                    out[m.group(2)] = (m.group(1), m.group(3))
            if not out:
                out = 'no check lines from acceptance.sh: ' + (run.stderr or run.stdout)[-200:]
        except (OSError, subprocess.SubprocessError) as exc:
            out = f'acceptance.sh could not run: {exc}'
    DATA._cache['sbx'] = out
    return out


# --- text scanning shared by V1-V3 ---------------------------------------------------------------

CATEGORY = r'(?:4[ABX]|[0-4]|S)'
CAT_PATTERNS = [
    re.compile(r'Lung-?RADS\W{0,3}(?:v?\d{4}\W{1,3})?(?:category\W{1,3})?(' + CATEGORY + r')\b', re.I),
    re.compile(r'\bcategory\W{1,3}(' + CATEGORY + r')\b', re.I),
]
MM = re.compile(r'\d+(?:\.\d+)?\s*mm\b', re.I)
NUMBER = re.compile(r'(?<![\w.])\d+(?:\.\d+)?(?!\w|\.\d)')


def categories(text):
    seen = []
    for pattern in CAT_PATTERNS:
        seen += [m.group(1).upper() for m in pattern.finditer(text)]
    return seen


def numbers_in(value):
    """Every numeric leaf and every number inside a string of a JSON value."""
    out = []
    if isinstance(value, bool) or value is None:
        pass
    elif isinstance(value, (int, float)):
        out.append(float(value))
    elif isinstance(value, str):
        out += [float(m) for m in NUMBER.findall(value)]
    elif isinstance(value, dict):
        for v in value.values():
            out += numbers_in(v)
    elif isinstance(value, list):
        for v in value:
            out += numbers_in(v)
    return out


def allowed_numbers(findings, study):
    base = numbers_in(findings) + numbers_in({k: study.get(k) for k in ('day_offset', 'rank', 'patient_id', 'study_date')})
    allowed = set()
    for x in base:
        for y in (x, x / 10, x * 10):
            for d in (0, 1, 2):
                allowed.add(round(y, d))
    return allowed


MONTH_WHITELIST = re.compile(r'\b(?:3|6|12)[- ]months?\b', re.I)


def unlisted_numbers(text, allowed):
    """Numbers in agent-written text that are not in the findings (V3, review list)."""
    text = re.sub(r'\b\d{4}-\d{2}-\d{2}\b|\b(?:19|20)\d{2}\b', ' ', text)          # dates, years
    text = re.sub(r'(?m)^\s*(?:[-*]\s*)?\d+[.)]\s', ' ', text)                    # list markers
    text = re.sub(r'\bLung-?RADS\W{0,3}(?:v?\d{4}\W{1,3})?(?:category\W{1,3})?' + CATEGORY + r'\b', ' ', text, flags=re.I)
    text = re.sub(r'\bcategory\W{1,3}' + CATEGORY + r'\b', ' ', text, flags=re.I)
    text = MONTH_WHITELIST.sub(' ', text)
    bad = []
    for m in NUMBER.findall(text):
        value = float(m)
        if not any(abs(value - a) < 1e-6 for a in allowed):
            bad.append(m)
    return bad


# --- reporter ------------------------------------------------------------------------------------

class Result(unittest.TextTestResult):
    """Prints one PASS/FAIL/SKIP line per check, keyed by the ID in the method name (test_V1_x -> V1)."""

    rows = []

    def _id(self, test):
        m = re.match(r'test_([A-Z]\d+[a-z]?)_', test._testMethodName)
        return m.group(1) if m else test._testMethodName

    def _emit(self, word, test, note=''):
        line = f'{word:4} {self._id(test):4} {test.shortDescription() or ""}'
        if note:
            line += f'  -- {note}'
        print(line, flush=True)
        self.rows.append({'id': self._id(test), 'result': word, 'desc': test.shortDescription(), 'note': note})

    def addSuccess(self, test):
        note = getattr(test, 'note', '')
        self._emit('PASS', test, note)

    def addFailure(self, test, err):
        self._emit('FAIL', test, str(err[1]).strip().replace('\n', ' | ')[:400])

    def addError(self, test, err):
        self._emit('FAIL', test, f'{err[0].__name__}: {err[1]}'[:400])

    def addSkip(self, test, reason):
        self._emit('SKIP', test, reason)


class QA(unittest.TestCase):
    note = ''

    def setUp(self):
        self.note = ''

    def studies(self):
        return self.rows_or_skip()

    def rows_or_skip(self):
        try:
            rows = DATA.worklist()
        except OSError as exc:
            self.fail(f'worker unreachable at {BASE}: {exc}')
        if not isinstance(rows, list):
            self.fail(f'worklist is not a list: {rows!r}'[:200])
        return rows

    def need(self, rows, why):
        if not rows:
            self.skipTest(why)
        return rows

    def no_post_when_recording(self):
        if recording():
            self.skipTest('recording state: GET-only')
