"""Voice routes: POST /api/asr and POST /api/tts (09-voice.md; 00 v0.4/v0.5).

Mount for sparkmd/app.py (same place as the ask router, before the StaticFiles mount):

    from .voice import router as voice_router
    app.include_router(voice_router)

/api/asr: 16 kHz mono s16 WAV in -> whisper-server (127.0.0.1:8178, per-request phrase prompt) ->
stdlib matcher -> {text, command, phrase, score}; 422 unless the body is that WAV.
/api/tts: {text} -> normalised -> TTS container (127.0.0.1:8020, voice aiden, response_format pcm) ->
raw 24 kHz s16le PCM streamed back. Both upstreams are loopback-only; neither is exposed to the agent.
"""
import json
import os
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
import httpx

from .ask import match

router = APIRouter()

# Env read at import, like ask.py. Point both at stubs in tests.
ASR_URL = os.environ.get('SPARKMD_ASR_URL', 'http://127.0.0.1:8178') + '/inference'
TTS_URL = os.environ.get('SPARKMD_TTS_URL', 'http://127.0.0.1:8020') + '/v1/audio/speech'
# 09 Parameters: biasing prompt sent with every /inference request (bench: +4-10 clips/variant).
PROMPT = 'Show me the nodule. Compare it to last year. Why did you flag this? Reset the view.'
CANONICAL = {'show_nodule': 'Show me the nodule.', 'compare_prior': 'Compare it to last year.',
             'why_flag': 'Why did you flag this?', 'reset_view': 'Reset the view.'}
MAX_BYTES = 256 * 1024   # 09 interface: <= 6 s, <= 256 kB of 16 kHz mono s16
MAX_SECONDS = 6.0


def human(request):
    # Same rule as /api/ask: loopback and no agent header (the agent has no ASR/TTS tool, 09).
    return request.client is not None and request.client.host in ('127.0.0.1', '::1') \
        and request.headers.get('X-SparkMD-Caller', '').lower() != 'agent'


def wav_info(data):
    """(rate, channels, bits, pcm_bytes) of a RIFF PCM WAV, else None (any non-conforming body)."""
    if len(data) < 44 or data[0:4] != b'RIFF' or data[8:12] != b'WAVE':
        return None
    pos, fmt, dat = 12, None, None
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        size = int.from_bytes(data[pos + 4:pos + 8], 'little')
        if cid == b'fmt ' and size >= 16:
            fmt = data[pos + 8:pos + 8 + size]
        elif cid == b'data':
            dat = size if size else len(data) - pos - 8   # size 0 = stream to end of file
        pos += 8 + size + (size & 1)                      # chunks are word-aligned
    if fmt is None or not dat:
        return None
    if int.from_bytes(fmt[0:2], 'little') != 1:           # PCM only (no float/WAVE_FORMAT_EXTENSIBLE)
        return None
    return (int.from_bytes(fmt[4:8], 'little'), int.from_bytes(fmt[2:4], 'little'),
            int.from_bytes(fmt[14:16], 'little'), dat)


def speakable(text):
    """09 TTS normalisation: strip markdown, Lung-RADS -> Lung RADS, mm -> millimeters,
    first <= 2 sentences / <= 300 chars (round-trip tested in the bench)."""
    t = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text)   # links/images -> their text
    t = re.sub(r'[#*_`>]', '', t)
    t = t.replace('|', ' ')
    t = re.sub(r'lung-?rads', 'Lung RADS', t, flags=re.I)
    t = re.sub(r'\bmm\b', 'millimeters', t)
    t = ' '.join(t.split())                               # collapse whitespace left by stripping
    sentences = [p for p in re.split(r'(?<=[.!?])\s+', t) if p]   # lookbehind: keep 5.6 whole
    t = ' '.join(sentences[:2])[:300]
    if len(t) == 300:                                     # cut on a word boundary, still <= 300 chars
        t = t.rsplit(' ', 1)[0].rstrip(' ,;:')
    return t.strip()


@router.post('/api/asr')
async def asr(request: Request):
    worker = getattr(request.app.state, 'worker', None)
    if not human(request):
        if worker:
            worker.log('system', 'Denied asr: UI loopback caller required', None)
        return JSONResponse({'error': 'asr_loopback_only'}, status_code=403)
    wav = await request.body()
    if len(wav) > MAX_BYTES:
        return JSONResponse({'error': 'clip too large (max 256 kB)'}, status_code=422)
    info = wav_info(wav)
    if not info or info[:3] != (16000, 1, 16):
        return JSONResponse({'error': 'audio/wav 16 kHz mono s16 required'}, status_code=422)
    if info[3] / 32000 > MAX_SECONDS:
        return JSONResponse({'error': 'clip too long (max 6 s)'}, status_code=422)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=5), trust_env=False) as client:
            response = await client.post(ASR_URL, files={'file': ('clip.wav', wav, 'audio/wav')},
                                         data={'response_format': 'json', 'prompt': PROMPT})
    except httpx.HTTPError as exc:
        if worker:
            worker.log('system', f'ASR failed: {type(exc).__name__}: {exc}', None)
        return JSONResponse({'error': 'asr_unavailable'}, status_code=502)
    if response.status_code >= 400:
        if worker:
            worker.log('system', f'ASR server HTTP {response.status_code}', None)
        return JSONResponse({'error': 'asr_upstream'}, status_code=502)
    text = (response.json().get('text') or '').strip()
    if re.fullmatch(r'\[[^\]]*\]', text):   # [BLANK_AUDIO] and friends: empty input (09)
        text = ''
    command, score = match(text)
    return {'text': text, 'command': command, 'phrase': CANONICAL.get(command), 'score': score}


@router.post('/api/tts')
async def tts(request: Request):
    worker = getattr(request.app.state, 'worker', None)
    if not human(request):
        if worker:
            worker.log('system', 'Denied tts: UI loopback caller required', None)
        return JSONResponse({'error': 'tts_loopback_only'}, status_code=403)
    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError):
        body = None
    text = (body or {}).get('text') if isinstance(body, dict) else None
    if not isinstance(text, str) or not text.strip():
        return JSONResponse({'error': 'text required'}, status_code=422)
    payload = {'model': 'tts-1', 'voice': 'aiden', 'input': speakable(text) or text.strip(),
               'response_format': 'pcm'}   # never 'zip': it would fetch a forced aligner (09 gotcha)
    client = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=5), trust_env=False)
    try:
        response = await client.send(client.build_request('POST', TTS_URL, json=payload), stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        if worker:
            worker.log('system', f'TTS failed: {type(exc).__name__}: {exc}', None)
        return JSONResponse({'error': 'tts_unavailable'}, status_code=502)
    if response.status_code >= 400:
        detail = (await response.aread())[:200].decode(errors='replace')
        await response.aclose()
        await client.aclose()
        if worker:
            worker.log('system', f'TTS server HTTP {response.status_code}: {detail}', None)
        return JSONResponse({'error': 'tts_upstream'}, status_code=502)

    async def pcm():
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(pcm(), media_type='audio/L16; rate=24000; channels=1',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
