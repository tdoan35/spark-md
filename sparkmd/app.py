from contextlib import asynccontextmanager
import asyncio
import json
import os
from pathlib import Path
import threading
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .worker import Worker

TOOL_FIELDS = {
    'list_studies': ({'status': {'type': 'string'}}, []),
    'get_study': ({'study_uid': {'type': 'string'}}, ['study_uid']),
    'select_series': ({'study_uid': {'type': 'string'}, 'series_uid': {'type': 'string'}, 'reason': {'type': 'string'}}, ['study_uid', 'series_uid', 'reason']),
    'run_analysis': ({'study_uid': {'type': 'string'}}, ['study_uid']),
    'get_findings': ({'study_uid': {'type': 'string'}}, ['study_uid']),
    'save_report': ({'study_uid': {'type': 'string'}, 'kind': {'type': 'string', 'enum': ['radiology', 'pcp_letter']}, 'markdown': {'type': 'string'}}, ['study_uid', 'kind', 'markdown']),
    'set_priority': ({'study_uid': {'type': 'string'}, 'priority': {'type': 'string', 'enum': ['routine', 'elevated', 'urgent']}, 'reason': {'type': 'string'}}, ['study_uid', 'priority', 'reason']),
    'viewer_command': ({'study_uid': {'type': 'string'}, 'command': {'type': 'string', 'enum': ['show_nodule', 'compare_prior', 'reset_view', 'show_extras']}, 'nodule_id': {'type': 'string'}}, ['study_uid', 'command']),
    'log_event': ({'study_uid': {'type': 'string'}, 'message': {'type': 'string'}}, ['message']),
}


def caller_agent(request):
    return request.headers.get('X-SparkMD-Caller', '').lower() == 'agent' or not request.client or request.client.host not in ('127.0.0.1', '::1')


def human(request):
    # Neither forwarded headers nor an agent header can confer UI privileges.
    return request.client is not None and request.client.host == '127.0.0.1' and not caller_agent(request)


def result(value):
    obj, status = value
    return JSONResponse(obj, status_code=status)


def create_app(config=None):
    worker = Worker(config)

    @asynccontextmanager
    async def lifespan(app):
        thread = threading.Thread(target=worker.intake.watch, args=(worker.stop,), daemon=True)
        worker.threads.append(thread)
        thread.start()
        # An interrupted process cannot leave an exam permanently 'analyzing'.
        for row in worker.registry.all("SELECT study_uid FROM studies WHERE status='analyzing'"):
            worker.status(row['study_uid'], 'organized')
            worker.log('system', 'Interrupted analysis can be restarted', row['study_uid'])
        async def publish_netstats():
            while True:
                worker.events.emit('net_stats', worker.netstats.sample())
                await asyncio.sleep(2)

        monitor = asyncio.create_task(publish_netstats())
        try:
            yield
        finally:
            await worker.stop_demo()
            worker.stop.set()
            monitor.cancel()
            try:
                await monitor
            except asyncio.CancelledError:
                pass
            for thread in worker.threads:
                await asyncio.to_thread(thread.join)
            worker.registry.close()

    app = FastAPI(title='Spark MD research worker', lifespan=lifespan)
    app.state.worker = worker

    @app.middleware('http')
    async def request_log(request, call_next):
        started = time.monotonic()
        payload = None
        if request.headers.get('content-type', '').startswith('application/json'):
            try:
                payload = json.loads(await request.body())
            except (ValueError, UnicodeDecodeError):
                pass
        response = await call_next(request)
        duration = round((time.monotonic()-started)*1000, 2)
        if caller_agent(request) and request.url.path.startswith('/api/'):
            worker.log('tool_call', f'{request.method} {request.url.path} -> {response.status_code}', request.path_params.get('uid'),
                       {'status': response.status_code, 'duration_ms': duration, 'run_id': request.headers.get('X-SparkMD-Run-Id')})
        reqlog = os.environ.get('SPARKMD_REQLOG')
        if reqlog:
            path = Path(reqlog)
            path.parent.mkdir(parents=True, exist_ok=True)
            with worker.registry.lock, path.open('a') as output:
                output.write(json.dumps({'method': request.method, 'path': request.url.path, 'body': payload, 'status': response.status_code, 'duration_ms': duration})+'\n')
        return response

    @app.exception_handler(ImportError)
    async def unavailable(request, exc):
        return JSONResponse({'error': f'layer unavailable: {exc}'}, status_code=503)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'error': str(exc)}, status_code=422)

    async def body(request):
        try:
            obj = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise ValueError('JSON object required')
        if not isinstance(obj, dict):
            raise ValueError('JSON object required')
        return obj

    async def tool(request, name, args):
        return result(await worker.call_tool(name, args, caller_agent(request)))

    def gate(request, operation):
        if human(request):
            return None
        worker.log('system', f'Denied {operation}: UI loopback caller required', None)
        return JSONResponse({'error': operation+'_loopback_only'}, status_code=403)

    @app.get('/api/health')
    async def health():
        return {'status': 'ok', 'worker_version': '0.1.0', 'contract_version': '0.8', 'placeholder': worker.config.fake}

    @app.get('/api/worklist')
    async def worklist(request: Request, status: str | None = None):
        return await tool(request, 'list_studies', {'status': status})

    @app.get('/api/studies/{uid}')
    async def study(uid: str, request: Request):
        return await tool(request, 'get_study', {'study_uid': uid})

    @app.post('/api/studies/{uid}/select-series')
    async def select(uid: str, request: Request):
        return await tool(request, 'select_series', (await body(request)) | {'study_uid': uid})

    @app.post('/api/studies/{uid}/analyze')
    async def analyze(uid: str, request: Request):
        return await tool(request, 'run_analysis', (await body(request)) | {'study_uid': uid})

    @app.get('/api/jobs/{job_id}')
    async def job(job_id: str):
        with worker.jobs_lock:
            if job_id not in worker.jobs:
                return JSONResponse({'error': 'job not found'}, status_code=404)
            return worker.job_payload(worker.jobs[job_id])

    @app.get('/api/studies/{uid}/findings')
    async def get_findings(uid: str, request: Request):
        return await tool(request, 'get_findings', {'study_uid': uid})

    @app.get('/api/studies/{uid}/assets/{name:path}')
    async def asset(uid: str, name: str):
        series = worker.registry.one('SELECT series_uid FROM series WHERE study_uid=? AND selected=1', (uid,))
        if not series:
            return JSONResponse({'error': 'selected series not found'}, status_code=404)
        root = (worker.config.home/'cache'/series['series_uid']).resolve()
        path = (root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() not in ('.glb', '.png', '.jpg', '.jpeg', '.json'):
            return JSONResponse({'error': 'asset not found'}, status_code=404)
        return FileResponse(path)

    @app.post('/api/studies/{uid}/reports')
    async def report(uid: str, request: Request):
        return await tool(request, 'save_report', (await body(request)) | {'study_uid': uid})

    @app.get('/api/studies/{uid}/reports')
    async def reports(uid: str):
        return worker.registry.all('SELECT * FROM reports WHERE study_uid=? ORDER BY version DESC,kind', (uid,))

    @app.post('/api/nodules/{nid}/confirm')
    async def confirm(nid: str, request: Request):
        denied = gate(request, 'confirm')
        if denied is not None: return denied
        payload = await body(request)
        return result(await asyncio.to_thread(worker.confirm, nid, payload))

    @app.post('/api/reports/{rid}/approve')
    async def approve(rid: str, request: Request):
        denied = gate(request, 'approve')
        if denied is not None: return denied
        payload = await body(request)
        return result(await asyncio.to_thread(worker.approve, rid, payload))

    @app.post('/api/studies/{uid}/priority')
    async def priority(uid: str, request: Request):
        return await tool(request, 'set_priority', (await body(request)) | {'study_uid': uid})

    @app.post('/api/viewer/command')
    async def viewer(request: Request):
        return await tool(request, 'viewer_command', await body(request))

    @app.post('/api/agent-log')
    async def agent_log(request: Request):
        return await tool(request, 'log_event', await body(request))

    @app.get('/api/agent-log')
    async def log_history(study_uid: str | None = None, limit: int = 200):
        limit = min(2000, max(1, limit))
        if study_uid is None:
            rows = worker.registry.all('SELECT * FROM agent_events ORDER BY id DESC LIMIT ?', (limit,))
        else:
            rows = worker.registry.all('SELECT * FROM agent_events WHERE study_uid=? ORDER BY id DESC LIMIT ?', (study_uid, limit))
        for row in rows:
            row.update(json.loads(row['payload_json'] or '{}'))
        return list(reversed(rows))

    @app.get('/api/events')
    async def events(request: Request):
        last = request.headers.get('Last-Event-ID')
        try: last = int(last) if last else None
        except ValueError: last = None
        return StreamingResponse(worker.events.stream(last), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.get('/api/netstats')
    async def netstats():
        return worker.netstats.sample()

    @app.get('/api/outbox')
    async def outbox():
        rows = worker.registry.all('''SELECT o.*,r.study_uid,s.patient_id FROM outbox o JOIN reports r USING(report_id)
            JOIN studies s USING(study_uid) ORDER BY o.ts DESC,o.id DESC''')
        for row in rows:
            row['payload'] = json.loads(row.pop('payload_json'))
            row['subject'] = 'Lung CT screening follow-up'
        return rows

    @app.post('/mcp')
    async def mcp(request: Request):
        message = await body(request)
        method, rid = message.get('method'), message.get('id')
        if 'id' not in message:
            return Response(status_code=202)
        headers = {}
        if method == 'initialize':
            response = {'protocolVersion': message.get('params', {}).get('protocolVersion', '2025-03-26'), 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'spark-md-worker', 'version': '0.1.0'}}
            headers['Mcp-Session-Id'] = uuid.uuid4().hex
        elif method == 'ping':
            response = {}
        elif method == 'tools/list':
            response = {'tools': [{'name': name, 'description': name.replace('_', ' '), 'inputSchema': {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}} for name, (properties, required) in TOOL_FIELDS.items()]}
        elif method == 'tools/call':
            params = message.get('params') or {}
            name, args = params.get('name'), params.get('arguments') or {}
            started = time.monotonic()
            if name not in TOOL_FIELDS or not isinstance(args, dict):
                obj, code = {'error': 'unknown tool or invalid arguments'}, 422
            elif any(k not in args for k in TOOL_FIELDS[name][1]):
                obj, code = {'error': 'missing required arguments'}, 422
            else:
                try:
                    if name == 'run_analysis':
                        args['wait_s'] = worker.config.mcp_wait
                    obj, code = await worker.call_tool(name, args, True)
                except ImportError as exc:
                    obj, code = {'error': f'layer unavailable: {exc}'}, 503
                except (ValueError, TypeError) as exc:
                    obj, code = {'error': str(exc)}, 422
            duration = round((time.monotonic()-started)*1000, 2)
            worker.log('tool_call', f'{name} -> {code} ({duration/1000:.3f}s)', args.get('study_uid') if isinstance(args, dict) else None,
                       {'tool': name, 'args': args, 'status': code, 'duration_ms': duration})
            response = {'content': [{'type': 'text', 'text': json.dumps(obj)}], 'isError': code >= 400}
        else:
            return JSONResponse({'jsonrpc': '2.0', 'id': rid, 'error': {'code': -32601, 'message': 'Method not found'}})
        return JSONResponse({'jsonrpc': '2.0', 'id': rid, 'result': response}, headers=headers)

    @app.get('/mcp')
    async def mcp_get():
        return Response(status_code=405, headers={'Allow': 'DELETE, POST'})

    @app.delete('/mcp')
    async def mcp_delete():
        return Response(status_code=204)

    from .demo import install_demo
    install_demo(app, worker, gate)
    from .ask import router as ask_router
    app.include_router(ask_router)
    from .voice import router as voice_router
    app.include_router(voice_router)
    if worker.config.ui_dir.is_dir():
        app.mount('/', StaticFiles(directory=worker.config.ui_dir, html=True), name='ui')
    return app


app = create_app()
