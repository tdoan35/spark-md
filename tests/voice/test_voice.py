"""Voice routes (/api/asr, /api/tts) against stub whisper-server and TTS container (stdlib unittest,
test_ask.py style). Run: /home/dell/.venvs/spark-md/bin/python -m unittest tests.voice.test_voice -v
(no GPU, no whisper-server, no TTS container, no network).
"""
from email import message_from_bytes
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import socket
import threading
import time
import unittest
import urllib.error
import urllib.request

from .wavs import clip, pcm, wav


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


ASR_PORT, TTS_PORT, PORT = free_port(), free_port(), free_port()
BASE = f'http://127.0.0.1:{PORT}'
os.environ['SPARKMD_ASR_URL'] = f'http://127.0.0.1:{ASR_PORT}'
os.environ['SPARKMD_TTS_URL'] = f'http://127.0.0.1:{TTS_PORT}'
DEAD = free_port()   # nothing listens here: upstream-down cases

import sparkmd.voice   # noqa: E402  (after the env block: URLs are read at import, like ask.py)

PCM = bytes(range(256)) * 4   # fake 24 kHz s16 payload the TTS stub returns


class Recorder:
    calls = []

    def log(self, *args, **kwargs):
        Recorder.calls.append(args)


class ASRStub(BaseHTTPRequestHandler):
    """POST /inference: records the multipart, answers with `text`."""
    requests, text, status = [], ' Show me the nodule.', 200

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        parts = {}
        msg = message_from_bytes(b'Content-Type: ' + self.headers['Content-Type'].encode() + b'\r\n\r\n' + body,
                                 policy=email_policy)
        for part in msg.iter_parts():
            parts[part.get_param('name', header='content-disposition')] = part.get_payload(decode=True)
        ASRStub.requests.append(parts)
        self.send_response(ASRStub.status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'text': ASRStub.text}).encode())


class TTSStub(BaseHTTPRequestHandler):
    """POST /v1/audio/speech: records the JSON body, returns raw PCM."""
    requests, status = [], 200

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        TTSStub.requests.append(json.loads(body))
        if TTSStub.status != 200:
            self.send_response(TTSStub.status); self.end_headers(); self.wfile.write(b'boom'); return
        self.send_response(200)
        self.send_header('Content-Type', 'audio/L16; rate=24000; channels=1')
        self.end_headers()
        self.wfile.write(PCM)


def post(path, data, headers):
    req = urllib.request.Request(BASE + path, data, headers)
    try:
        response = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.status, response.read(), response.headers.get('Content-Type')


def asr_post(body, headers=None):
    return post('/api/asr', body, {'Content-Type': 'audio/wav'} | (headers or {}))


def tts_post(obj, headers=None):
    return post('/api/tts', json.dumps(obj).encode(), {'Content-Type': 'application/json'} | (headers or {}))


class Voice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import uvicorn
        from fastapi import FastAPI


        app = FastAPI()
        app.state.worker = Recorder()

        @app.get('/api/health')
        async def health():
            return {'ok': True}
        app.include_router(sparkmd.voice.router)
        cls.asr = ThreadingHTTPServer(('127.0.0.1', ASR_PORT), ASRStub)
        cls.tts = ThreadingHTTPServer(('127.0.0.1', TTS_PORT), TTSStub)
        for server in (cls.asr, cls.tts):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        cls.server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=PORT, log_level='warning'))
        threading.Thread(target=cls.server.run, daemon=True).start()
        for _ in range(100):
            try:
                if post('/api/health', None, {})[0] == 200:
                    break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.asr.shutdown()
        cls.tts.shutdown()

    def setUp(self):
        ASRStub.requests.clear(); ASRStub.text, ASRStub.status = ' Show me the nodule.', 200
        TTSStub.requests.clear(); TTSStub.status = 200
        Recorder.calls.clear()
        self.addCleanup(setattr, sparkmd.voice, 'ASR_URL', sparkmd.voice.ASR_URL)
        self.addCleanup(setattr, sparkmd.voice, 'TTS_URL', sparkmd.voice.TTS_URL)

    # --- /api/asr ------------------------------------------------------------------
    def test_asr_matches_and_forwards(self):
        status, body, _ = asr_post(clip('synth_show_nodule'))
        self.assertEqual(status, 200)
        got = json.loads(body)
        self.assertEqual(got['command'], 'show_nodule')
        self.assertEqual(got['phrase'], 'Show me the nodule.')
        self.assertEqual(got['text'], 'Show me the nodule.')
        self.assertGreaterEqual(got['score'], 0.80)
        sent = ASRStub.requests[0]

        self.assertEqual(sent['prompt'].decode(), sparkmd.voice.PROMPT)   # phrase prompt per request (09)
        self.assertEqual(sent['response_format'], b'json')
        self.assertEqual(sent['file'], clip('synth_show_nodule'))  # the WAV as received (09)

    def test_asr_accepts_bench_clip_set(self):
        for name, command in [('synth_show_nodule', 'show_nodule'), ('synth_compare_prior', 'compare_prior'),
                              ('synth_why_flag', 'why_flag'), ('synth_reset_view', 'reset_view')]:
            ASRStub.text = {'show_nodule': 'Show me the nodule.', 'compare_prior': 'Compare it to last year.',
                            'why_flag': 'Why did you flag this?', 'reset_view': 'Reset the view.'}[command]
            status, body, _ = asr_post(clip(name))
            self.assertEqual((status, json.loads(body)['command']), (200, command), name)

    def test_asr_rejects_bad_wav(self):
        cases = [b'', b'not a wav at all', wav(pcm(0.2, 200), rate=44100), wav(pcm(0.2, 200), channels=2),
                 wav(pcm(0.2, 200), bits=8), clip('synth_too_long'), b'x' * (256 * 1024 + 1)]
        for i, bad in enumerate(cases):
            status, body, _ = asr_post(bad)
            self.assertEqual(status, 422, f'case {i}')
            self.assertTrue(json.loads(body)['error'])

    def test_asr_blank_audio_maps_to_null(self):
        ASRStub.text = '[BLANK_AUDIO]'
        status, body, _ = asr_post(clip('synth_silence'))
        got = json.loads(body)
        self.assertEqual((status, got['command'], got['phrase'], got['score']), (200, None, None, 0.0))

    def test_asr_unmatched_text_maps_to_null(self):
        ASRStub.text = 'What is the weather in Paris'
        _, body, _ = asr_post(clip('synth_room_noise'))
        got = json.loads(body)
        self.assertIsNone(got['command'])
        self.assertIsNone(got['phrase'])

    def test_asr_gates_and_upstream_down(self):
        status, body, _ = asr_post(clip('synth_show_nodule'), {'X-SparkMD-Caller': 'agent'})
        self.assertEqual((status, json.loads(body)['error']), (403, 'asr_loopback_only'))
        self.assertEqual(Recorder.calls, [('system', 'Denied asr: UI loopback caller required', None)])
        sparkmd.voice.ASR_URL = f'http://127.0.0.1:{DEAD}'
        status, body, _ = asr_post(clip('synth_show_nodule'))
        self.assertEqual((status, json.loads(body)['error']), (502, 'asr_unavailable'))

    # --- /api/tts ------------------------------------------------------------------
    def test_tts_normalises_and_streams_pcm(self):
        text = ('**Lung-RADS 4B** (see [the table](x)). The nodule grew **1.6 mm**. Second sentence. Third one.')
        status, body, ctype = tts_post({'text': text})
        self.assertEqual(status, 200)
        self.assertEqual(body, PCM)
        self.assertEqual(ctype, 'audio/L16; rate=24000; channels=1')
        sent = TTSStub.requests[0]
        self.assertEqual(sent['model'], 'tts-1')
        self.assertEqual(sent['voice'], 'aiden')
        self.assertEqual(sent['response_format'], 'pcm')   # never zip (09 gotcha)
        self.assertEqual(sent['input'], 'Lung RADS 4B (see the table). The nodule grew 1.6 millimeters.')

    def test_tts_caps_at_300_chars(self):
        long_first = ('The nodule diameter grew by more than expected today ' * 7).strip() + '.'
        status, _, _ = tts_post({'text': long_first})
        self.assertEqual(status, 200)
        sent = TTSStub.requests[0]['input']
        self.assertLessEqual(len(sent), 300)
        self.assertTrue(sent[-1].isalnum())   # cut on a word boundary, no dangling separator
        self.assertNotIn('.', sent)           # the only period was past the cap

    def test_tts_422_and_upstream_down(self):
        for bad in ({}, {'text': ''}, {'text': '   '}):
            status, _, _ = tts_post(bad)
            self.assertEqual(status, 422, bad)
        sparkmd.voice.TTS_URL = f'http://127.0.0.1:{DEAD}'
        status, body, _ = tts_post({'text': 'View reset.'})
        self.assertEqual((status, json.loads(body)['error']), (502, 'tts_unavailable'))

    def test_speakable(self):
        from sparkmd.voice import speakable
        self.assertEqual(speakable('# Report\nLUNG-RADS 4B: 5.6 mm.'), 'Report Lung RADS 4B: 5.6 millimeters.')
        self.assertEqual(speakable('The scan is clean. Nothing to flag.'), 'The scan is clean. Nothing to flag.')

if __name__ == '__main__':
    unittest.main()
