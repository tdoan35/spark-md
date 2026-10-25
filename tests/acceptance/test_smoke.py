"""Smoke pass (11 §Run order): the worker contract surface, MCP, UI, LLM, sandbox route. Read-only."""
import re
import urllib.error
import urllib.request

from qa import BASE, DATA, LLM_URL, QA, get, http, sandbox_checks

STUDY_KEYS = {'study_uid', 'patient_id', 'timepoint', 'status', 'priority', 'day_offset', 'lung_rads', 'reports_awaiting'}
NODULE_KEYS = {'nodule_id', 'track_id', 'long_mm', 'short_mm', 'mean_mm', 'volume_mm3', 'confirmation', 'prior'}
CDN = re.compile(r'googleapis|gstatic|cdn\.|unpkg|jsdelivr|cdnjs|cloudflare|fonts\.', re.I)


class Smoke(QA):
    def test_S01_health(self):
        """GET /api/health: ok, contract 0.8"""
        status, body, _ = get('/api/health')
        self.assertEqual(status, 200)
        self.assertEqual(body.get('status'), 'ok')
        self.assertEqual(body.get('contract_version'), '0.8')
        self.note = 'placeholder (fake imaging) worker' if body.get('placeholder') else 'real imaging worker'

    def test_S02_worklist_shape(self):
        """GET /api/worklist: list, 00 v0.8 row fields, sorted by priority"""
        rows = self.rows_or_skip()
        for r in rows:
            self.assertFalse(STUDY_KEYS - set(r), f'row missing {STUDY_KEYS - set(r)}')
        ranks = [{'urgent': 0, 'elevated': 1, 'routine': 2}.get(r['priority'], 9) for r in rows]
        self.assertEqual(ranks, sorted(ranks), 'worklist not sorted by priority first')
        self.note = f'{len(rows)} studies' + ('' if rows else ' (empty worklist)')

    def test_S03_mcp(self):
        """POST /mcp: initialize, 9 tools, none approve/confirm, GET 405, DELETE 204"""
        status, body, head = http('/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26'}})
        self.assertEqual(status, 200)
        self.assertTrue(head.get('mcp-session-id'), 'no Mcp-Session-Id')
        self.assertEqual(http('/mcp', {'jsonrpc': '2.0', 'method': 'notifications/initialized'})[0], 202)
        names = {t['name'] for t in http('/mcp', {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})[1]['result']['tools']}
        self.assertEqual(len(names), 9, sorted(names))
        self.assertFalse([n for n in names if re.search('approv|confirm', n)], 'gate tool exposed')
        self.assertEqual(http('/mcp')[0], 405)
        self.assertEqual(http('/mcp', method='DELETE')[0], 204)

    def test_S04_sse(self):
        """GET /api/events is an event stream"""
        resp = urllib.request.urlopen(BASE + '/api/events', timeout=5)
        try:
            self.assertEqual(resp.status, 200)
            self.assertIn('text/event-stream', resp.headers.get('content-type', ''))
        finally:
            resp.close()

    def test_S05_demo_state(self):
        """GET /api/demo/state: 00 v0.8 fields"""
        state = get('/api/demo/state')[1]
        self.assertFalse({'replaying', 'mode', 'waiting_for', 'phase', 'speed'} - set(state), state)
        self.assertIn(state['mode'], ('live', 'cached'))
        self.note = f"phase={state['phase']} mode={state['mode']}"

    def test_S06_ui_served(self):
        """GET / serves the UI, no CDN/web-font references in it"""
        status, html, _ = get('/')
        if status != 200:
            self.skipTest(f'UI not served by the worker (GET / -> {status}); run vite build')
        self.assertIn('id="root"', html)
        assets = re.findall(r'(?:src|href)="(/[^"]+\.(?:js|css))"', html)
        self.assertTrue(assets, 'no bundled assets referenced')
        for path in [''] + assets:
            text = html if not path else get(path)[1]
            text = text if isinstance(text, str) else ''
            if not path:
                self.assertFalse(re.findall(r'(?:src|href)="https?://', text), 'index.html loads an external URL')
            self.assertFalse(CDN.findall(text.replace('gstatic-draco-stripped', '')), f'{path or "index"} mentions a CDN/font host')
        self.note = f'{len(assets)} assets scanned'

    def test_S07_llm(self):
        """LLM on 127.0.0.1:8000 serves qwen3.8-27b"""
        try:
            status, body, _ = http('/models', base=LLM_URL, timeout=5)
        except (OSError, urllib.error.URLError) as exc:
            self.fail(f'LLM unreachable: {exc}')
        self.assertEqual(status, 200)
        self.assertIn('qwen3.8-27b', [m['id'] for m in body['data']])

    def test_S08_study_and_findings_shape(self):
        """GET study + findings per study: contract fields, placeholder flag"""
        rows = self.need(self.rows_or_skip(), 'empty worklist')
        for r in rows:
            f = DATA.findings(r['study_uid'])
            self.assertEqual(f['study_uid'], r['study_uid'])
            for key in ('nodules', 'pending_confirmation', 'assessment', 'assets', 'placeholder'):
                self.assertIn(key, f, f'{r["study_uid"][-8:]} findings missing {key}')
            for n in f['nodules']:
                self.assertFalse(NODULE_KEYS - set(n), f'nodule missing {NODULE_KEYS - set(n)}')
            study = DATA.study(r['study_uid'])
            self.assertIn('series', study)
            self.assertIn('priors', study)
        self.note = f'{len(rows)} studies'

    def test_S09_outbox_and_log(self):
        """GET /api/outbox and /api/agent-log: lists with the contract fields"""
        self.assertIsInstance(DATA.outbox(), list)
        log = DATA.log()
        self.assertIsInstance(log, list)
        for row in log[:50]:
            self.assertFalse({'id', 'ts', 'source', 'message'} - set(row))
        self.note = f'{len(DATA.outbox())} outbox, {len(log)} log rows'

    def test_S10_netstats(self):
        """GET /api/netstats"""
        status, body, _ = get('/api/netstats')
        if status == 404:
            self.skipTest('not built yet (404)')
        self.assertEqual(status, 200)
        self.assertIsInstance(body, dict)
        self.note = str(body)[:120]

    def test_S11_sandbox_reaches_llm_and_worker(self):
        """sandbox -> LLM /v1/models and -> worker /api/health (agent/tests/acceptance.sh A1, A2)"""
        sbx = sandbox_checks()
        if isinstance(sbx, str):
            self.skipTest(sbx)
        for check in ('A1', 'A2'):
            self.assertIn(check, sbx, f'{check} did not run')
            self.assertEqual(sbx[check][0], 'PASS', sbx[check][1])
