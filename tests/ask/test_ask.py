"""/api/ask against an in-process fake worker and a stub OpenAI-compatible harness (stdlib unittest).
Run: .venv/bin/python -m unittest tests.ask.test_ask -v   (needs no LLM, OpenClaw or network)
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


HOME = tempfile.mkdtemp(prefix='sparkmd-ask-')
STUB_PORT, PORT = free_port(), free_port()
BASE = f'http://127.0.0.1:{PORT}'
os.environ.update(SPARKMD_HOME=HOME, SPARKMD_FAKE_SEED='1', SPARKMD_FAKE_IMAGING='1', SPARKMD_FAKE_ANALYZE_S='0.2',
                  SPARKMD_ASK_URL=f'http://127.0.0.1:{STUB_PORT}/v1/chat/completions', SPARKMD_ASK_TOKEN='stub-token',
                  SPARKMD_ASK_TIMEOUT_S='20')
os.environ.pop('SPARKMD_HOOK_URL', None)


class Stub(BaseHTTPRequestHandler):
    """Streams an answer after `delay`; with `agent_repeat`, first calls the worker's MCP viewer_command like the agent would."""
    requests, mcp_results = [], []
    delay, status, agent_repeat = 0.0, 200, None
    answer = ['The nodule ', 'is in the ', 'left upper lobe.']

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        Stub.requests.append({'t': time.monotonic(), 'auth': self.headers.get('Authorization'), 'body': body})
        if Stub.agent_repeat:
            Stub.mcp_results.append(mcp('viewer_command', Stub.agent_repeat))
        time.sleep(Stub.delay)
        if Stub.status != 200:
            self.send_response(Stub.status); self.end_headers(); self.wfile.write(b'boom'); return
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        chunks = [{'choices': [{'delta': {'reasoning_content': 'hidden thinking'}}]}]
        chunks += [{'choices': [{'delta': {'content': c}}]} for c in Stub.answer]
        for c in chunks:
            self.wfile.write(f'data: {json.dumps(c)}\n\n'.encode()); self.wfile.flush()
        self.wfile.write(b'data: [DONE]\n\n')


def request(path, body=None, headers=None):
    req = urllib.request.Request(BASE+path, None if body is None else json.dumps(body).encode(),
                                 {'Content-Type': 'application/json'} | (headers or {}))
    try:
        response = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.status, response.read()


def mcp(name, args):
    _, raw = request('/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': args}},
                     {'X-SparkMD-Caller': 'agent'})
    return json.loads(json.loads(raw)['result']['content'][0]['text'])


def ask(uid, text, headers=None):
    """Returns ([(event, data, seconds since request)], http status)."""
    started = time.monotonic()
    req = urllib.request.Request(BASE+'/api/ask', json.dumps({'study_uid': uid, 'text': text}).encode(),
                                 {'Content-Type': 'application/json'} | (headers or {}))
    try:
        response = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as exc:
        return [], exc.code
    frames, event = [], None
    with response:
        for raw in response:
            line = raw.decode().rstrip('\n')
            if line.startswith('event: '):
                event = line[7:]
            elif line.startswith('data: '):
                frames.append((event, json.loads(line[6:]), time.monotonic()-started))
    return frames, 200


class SSE(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.events, self.ready = [], threading.Event()

    def run(self):
        with urllib.request.urlopen(BASE+'/api/events', timeout=60) as response:
            event = None
            for raw in response:
                line = raw.decode().rstrip('\n')
                if line.startswith(': connected'):
                    self.ready.set()
                if line.startswith('event: '):
                    event = line[7:]
                elif line.startswith('data: ') and event == 'viewer_command':
                    self.events.append(json.loads(line[6:]))

    def commands(self, uid):
        return [e['command'] for e in self.events if e.get('study_uid') == uid]


class Ask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import uvicorn
        from sparkmd.app import app
        from sparkmd.ask import router as ask_router
        routes = app.router.routes
        if not any(getattr(r, 'path', None) == '/api/ask' or getattr(r, 'router', None) is ask_router for r in routes):
            # Not mounted by W yet: include it ahead of the catch-all UI static mount at '/'.
            count = len(routes)
            app.include_router(ask_router)
            routes[:0] = [routes.pop() for _ in range(len(routes) - count)]
        cls.stub = ThreadingHTTPServer(('127.0.0.1', STUB_PORT), Stub)
        threading.Thread(target=cls.stub.serve_forever, daemon=True).start()
        cls.server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=PORT, log_level='warning'))
        threading.Thread(target=cls.server.run, daemon=True).start()
        for _ in range(100):
            try:
                if request('/api/health')[0] == 200: break
            except OSError:
                time.sleep(0.1)
        cls.sse = SSE(); cls.sse.start(); cls.sse.ready.wait(5)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.stub.shutdown()

    def setUp(self):
        Stub.requests.clear(); Stub.mcp_results.clear()
        Stub.delay, Stub.status, Stub.agent_repeat = 0.0, 200, None

    def test_matcher(self):
        from sparkmd.ask import match
        for text, command in [('Show me the nodule', 'show_nodule'), ('okay, compare it to last year', 'compare_prior'),
                              ("Why'd you flag this?", 'why_flag'), ('Reset the view please', 'reset_view'),
                              ('What is the weather in Paris', None)]:
            self.assertEqual(match(text)[0], command, text)

    def test_viewer_action_before_agent_and_duplicate_suppressed(self):
        uid = 'fixture-T1'
        Stub.delay, Stub.agent_repeat = 1.5, {'study_uid': uid, 'command': 'show_nodule'}
        before = len(self.sse.commands(uid))
        frames, status = ask(uid, 'Show me the nodule')
        self.assertEqual(status, 200)
        self.assertEqual(frames[0][0], 'tool')
        self.assertEqual(frames[0][1]['args']['command'], 'show_nodule')
        self.assertLess(frames[0][2], 1.0, 'viewer action must not wait for the harness')
        self.assertEqual(''.join(d['text'] for e, d, _ in frames if e == 'delta'), ''.join(Stub.answer))
        self.assertEqual(frames[-1][:2], ('done', {'ok': True}))
        self.assertTrue(Stub.mcp_results[0].get('deduplicated'))
        time.sleep(0.3)
        self.assertEqual(self.sse.commands(uid)[before:], ['show_nodule'], 'exactly one camera move per ask')
        sent = Stub.requests[0]
        self.assertEqual(sent['auth'], 'Bearer stub-token')
        self.assertEqual(sent['body']['model'], 'openclaw')
        self.assertEqual(sent['body']['user'], f'spark-md-ask-{uid}')
        self.assertIn('Already done by the worker for this question: viewer_command show_nodule', sent['body']['messages'][0]['content'])
        _, raw = request(f'/api/agent-log?study_uid={uid}&limit=20')
        messages = [e['message'] for e in json.loads(raw)]
        self.assertIn('command → show_nodule', messages)
        self.assertTrue(any(m.startswith('Duplicate show_nodule suppressed') for m in messages))
        # Dedup is scoped to the request: a later agent call moves the camera again.
        mcp('viewer_command', {'study_uid': uid, 'command': 'show_nodule'})
        time.sleep(0.3)
        self.assertEqual(self.sse.commands(uid)[before:], ['show_nodule', 'show_nodule'])

    def test_why_flag_only_asks(self):
        uid = 'fixture-T0'
        before = len(self.sse.commands(uid))
        frames, status = ask(uid, 'Why did you flag this?')
        self.assertEqual(status, 200)
        self.assertNotIn('tool', [e for e, _, _ in frames])
        self.assertEqual(frames[-1][0], 'done')
        self.assertNotIn('Already done', Stub.requests[0]['body']['messages'][0]['content'])
        time.sleep(0.3)
        self.assertEqual(self.sse.commands(uid)[before:], [])

    def test_compare_and_reset_emit_immediately(self):
        for text, command in [('Compare it to last year', 'compare_prior'), ('Reset the view', 'reset_view')]:
            frames, _ = ask('fixture-T2', text)
            self.assertEqual(frames[0][1]['args']['command'], command)
            self.assertEqual(frames[-1][0], 'done')

    def test_harness_error_frame(self):
        Stub.status = 500
        frames, status = ask('fixture-T0', 'Why did you flag this?')
        self.assertEqual(status, 200)
        self.assertEqual(frames[-1][0], 'error')
        self.assertIn('500', frames[-1][1]['message'])

    def test_rejects_agent_and_bad_input(self):
        self.assertEqual(ask('fixture-T0', 'Show me the nodule', {'X-SparkMD-Caller': 'agent'})[1], 403)
        self.assertEqual(ask('no-such-study', 'Show me the nodule')[1], 404)
        self.assertEqual(ask('fixture-T0', '  ')[1], 422)


if __name__ == '__main__':
    unittest.main()
