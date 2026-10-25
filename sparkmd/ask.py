"""POST /api/ask: canonical viewer phrase -> immediate viewer action (09), then the harness answer
re-framed as our delta/tool/done/error SSE frames (08 "/api/ask stream (pinned)").
Mount: app.include_router(ask_router) inside create_app, after app.state.worker is set.
"""
import asyncio
from difflib import SequenceMatcher
import json
import os
import re
import subprocess
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
import httpx

router = APIRouter()

# Matcher as benched in 09 (stdlib only).
COMMANDS = {
    'show_nodule': ['show me the nodule', 'show the nodule', 'show me that nodule'],
    'compare_prior': ['compare it to last year', 'compare to last year', 'compare this to last years scan'],
    'why_flag': ['why did you flag this', 'why was this flagged', 'why did you flag this one'],
    'reset_view': ['reset the view', 'reset view'],
}
VIEWER = {'show_nodule', 'compare_prior', 'reset_view'}  # why_flag only asks for an answer
FILLER = {'okay', 'ok', 'um', 'uh', 'so', 'hey', 'please', 'spark', 'alright', 'now'}


def norm(t):
    t = re.sub(r"\bwhy'd\b", 'why did', t.lower().replace('’', "'"))
    t = re.sub(r"[^a-z' ]+", ' ', t).replace("'", '')
    return ' '.join(w for w in t.split() if w not in FILLER)


def match(text, threshold=0.80, margin=0.08):
    n = norm(text)
    s = sorted(((max(SequenceMatcher(None, n, p).ratio() for p in ps), c) for c, ps in COMMANDS.items()), reverse=True)
    (s1, c1), (s2, _) = s[0], s[1]
    return (c1 if s1 >= threshold and s1 - s2 >= margin else None), round(s1, 3)


def frame(event, data):
    return f'event: {event}\ndata: {json.dumps(data)}\n\n'


# Viewer actions already done by an in-flight ask, keyed (study_uid, command) -> result.
# Agent viewer_command calls that repeat one are answered from here instead of moving the camera again.
ACTIVE = {}


def install_dedup(worker):
    if getattr(worker, '_ask_dedup', False):
        return
    original = worker.call_tool

    async def call_tool(name, args, agent=True):
        if name == 'viewer_command' and agent and isinstance(args, dict):
            done = ACTIVE.get((args.get('study_uid'), args.get('command')))
            if done is not None:
                worker.log('system', f"Duplicate {args.get('command')} suppressed (already done for this question)", args.get('study_uid'))
                return done | {'deduplicated': True}, 200
        return await original(name, args, agent)

    worker.call_tool = call_tool
    worker._ask_dedup = True


def human(request):
    # Same rule as the worker's gates: loopback and no agent header (00: the UI is the only /api/ask caller).
    return request.client is not None and request.client.host in ('127.0.0.1', '::1') \
        and request.headers.get('X-SparkMD-Caller', '').lower() != 'agent'


class Harness:
    """OpenAI-compatible chat endpoint of the harness (OpenClaw gateway chatCompletions, 07)."""

    def __init__(self):
        self.url = os.environ.get('SPARKMD_ASK_URL', 'http://127.0.0.1:18789/v1/chat/completions')
        self.model = os.environ.get('SPARKMD_ASK_MODEL', 'openclaw')
        self.token = os.environ.get('SPARKMD_ASK_TOKEN', '')
        # Gateway tokens are short-lived (07): mint with e.g. `nemoclaw spark-md-openclaw gateway-token --quiet`.
        self.token_cmd = os.environ.get('SPARKMD_ASK_TOKEN_CMD', '')
        self.timeout = float(os.environ.get('SPARKMD_ASK_TIMEOUT_S', '180'))  # cold prefill ~30-35 s (07)

    async def mint(self):
        if self.token_cmd:
            out = await asyncio.to_thread(subprocess.run, self.token_cmd, shell=True, capture_output=True, text=True, timeout=30)
            self.token = out.stdout.strip()
        return self.token

    async def stream(self, study_uid, prompt):
        if not self.token:
            await self.mint()
        body = {'model': self.model, 'stream': True, 'user': f'spark-md-ask-{study_uid}',  # one session per study
                'messages': [{'role': 'user', 'content': prompt}]}
        timeout = httpx.Timeout(self.timeout, connect=5)
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            for attempt in (0, 1):
                headers = {'Authorization': f'Bearer {self.token}'} if self.token else {}
                async with client.stream('POST', self.url, json=body, headers=headers) as response:
                    if response.status_code == 401 and attempt == 0 and self.token_cmd:
                        await self.mint()
                        continue
                    if response.status_code >= 400:
                        raise RuntimeError(f'harness HTTP {response.status_code}: {(await response.aread())[:200].decode(errors="replace")}')
                    if 'text/event-stream' not in response.headers.get('content-type', ''):
                        data = json.loads(await response.aread())
                        yield 'delta', {'text': data['choices'][0]['message'].get('content') or ''}
                        return
                    async for line in response.aiter_lines():
                        if not line.startswith('data:'):
                            continue
                        data = line[5:].strip()
                        if data == '[DONE]':
                            return
                        choice = (json.loads(data).get('choices') or [{}])[0]
                        delta = choice.get('delta') or {}
                        for call in delta.get('tool_calls') or []:
                            fn = call.get('function') or {}
                            if fn.get('name'):
                                yield 'tool', {'tool': fn['name'], 'args': fn.get('arguments')}
                        if delta.get('content'):  # reasoning_content (Qwen thinking) is not shown
                            yield 'delta', {'text': delta['content']}
                    return


HARNESS = Harness()


def prompt_for(study_uid, text, action):
    lines = [f'Question about study {study_uid} from the radiologist: {text}',
             'Answer per the Q&A section of your instructions (numbers only from get_findings).']
    if action:
        lines.append(f"Already done by the worker for this question: viewer_command {action['command']}"
                     + (f" (nodule {action['nodule_id']})" if action.get('nodule_id') else '') + '. Do not call it again.')
    return '\n'.join(lines)


@router.post('/api/ask')
async def ask(request: Request):
    worker = request.app.state.worker
    install_dedup(worker)
    if not human(request):
        worker.log('system', 'Denied ask: UI loopback caller required', None)
        return JSONResponse({'error': 'ask_loopback_only'}, status_code=403)
    try:
        body = await request.json()
    except ValueError:
        body = None
    uid, text = (body or {}).get('study_uid'), (body or {}).get('text')
    if not isinstance(uid, str) or not isinstance(text, str) or not text.strip():
        return JSONResponse({'error': 'study_uid and text required'}, status_code=422)
    if not worker.registry.one('SELECT study_uid FROM studies WHERE study_uid=?', (uid,)):
        return JSONResponse({'error': 'study not found'}, status_code=404)

    command, score = match(text)
    action = None
    if command in VIEWER:
        args = {'study_uid': uid, 'command': command}
        if command == 'show_nodule':
            nodule = worker.registry.one('''SELECT n.nodule_id FROM nodules n LEFT JOIN assessments a ON a.study_uid=n.study_uid
                WHERE n.study_uid=? ORDER BY (n.nodule_id = a.driver_nodule_id) DESC, n.nodule_id LIMIT 1''', (uid,))
            if nodule:
                args['nodule_id'] = nodule['nodule_id']
        # Before any LLM work: the camera never waits for prefill (09).
        action, status = await worker.call_tool('viewer_command', args, False)
        worker.log('system', f'command → {command}', uid, {'phrase': text, 'score': score, 'status': status})
        if status >= 400:
            action = None

    async def stream():
        key = (uid, command)
        if action:
            ACTIVE[key] = action
            yield frame('tool', {'tool': 'viewer_command', 'args': action})
        started = time.monotonic()
        try:
            async for event, data in HARNESS.stream(uid, prompt_for(uid, text, action)):
                yield frame(event, data)
            yield frame('done', {'ok': True})
        except Exception as exc:
            worker.log('system', f'Ask failed: {type(exc).__name__}: {exc}', uid)
            yield frame('error', {'message': f'{type(exc).__name__}: {exc}'})
        finally:
            if action and ACTIVE.get(key) is action:
                del ACTIVE[key]
            worker.log('system', f'Ask finished in {time.monotonic()-started:.1f}s', uid)

    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
