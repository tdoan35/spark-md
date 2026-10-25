"""Loopback replay controls for build/10; no confirm or approve path exists here.

Each study waits for analysis, diameter confirmation, both drafts, and both human
approvals before the next drop. Cached mode selects recorded v0.3+ proposals in
the worker; stop drains any active intake before returning. Reset is explicit.
"""

import asyncio
import math
import time

from fastapi import Request
from fastapi.responses import JSONResponse


class _ReplayStopped(Exception):
    pass


def install_demo(app, worker, gate):
    state = {'replaying': False, 'patient_id': None, 'timepoint': None, 'speed': 1, 'mode': 'live', 'waiting_for': None, 'phase': 'idle'}
    worker.demo_state = state
    replay_task = None
    stop_event = asyncio.Event()
    lifecycle = asyncio.Lock()

    def update(**changes):
        state.update(changes)
        worker.events.emit('demo_state', dict(state))

    def valid_patient(pid):
        return isinstance(pid, str) and bool(pid.strip()) and pid not in ('.', '..') and not any(c in pid for c in ('/', '\\', '\0'))

    def existing_study(pid, tp):
        return worker.registry.one('SELECT study_uid FROM studies WHERE patient_id=? AND timepoint=?', (pid, tp))

    def drop(pid, tp):
        if not valid_patient(pid) or tp not in ('T0', 'T1', 'T2'):
            return {'error': 'invalid patient/timepoint'}, 422
        existing = existing_study(pid, tp)
        if existing:
            return {'error': 'already dropped', 'study_uid': existing['study_uid']}, 409
        source = worker.config.home/'backlog'/pid/tp
        if not source.is_dir():
            return {'error': 'backlog study not found'}, 404
        uid = worker.intake.ingest_study(source)
        study = worker.registry.one('SELECT timepoint FROM studies WHERE study_uid=?', (uid,))
        if study['timepoint'] != tp:
            worker.log('system', f'Requested {tp}, computed {study["timepoint"]}; missing earlier studies', uid)
        return {'study_uid': uid, 'status': 'organized'}, 200

    def check_stop():
        if stop_event.is_set():
            raise _ReplayStopped

    async def pause(seconds=.25):
        check_stop()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
        check_stop()

    def status(uid):
        check_stop()
        study = worker.registry.one('SELECT status FROM studies WHERE study_uid=?', (uid,))
        if not study or study['status'] == 'failed':
            raise ValueError('study failed or disappeared')
        return study['status']

    async def wait_status(uid, targets):
        while status(uid) not in targets:
            await pause()

    def latest_reports(uid):
        rows = worker.registry.all(
            "SELECT kind,status FROM reports r WHERE study_uid=? AND kind IN ('radiology','pcp_letter') "
            'AND version=(SELECT MAX(version) FROM reports WHERE study_uid=r.study_uid AND kind=r.kind)', (uid,))
        return {row['kind']: row['status'] for row in rows}

    async def replay(pid, tps, gap):
        try:
            for tp in tps:
                check_stop()
                update(phase='dropping', timepoint=tp, waiting_for=None)
                # Never cancel this thread: stop/reset must wait until intake has settled.
                value, code = await asyncio.to_thread(drop, pid, tp)
                check_stop()
                if code != 200:
                    raise ValueError(value['error'])
                uid = value['study_uid']
                update(phase='analyzing', waiting_for='agent')
                await wait_status(uid, {'awaiting_confirmation', 'analyzed', 'reported', 'approved'})
                update(phase='waiting_confirm', waiting_for='confirm')
                await wait_status(uid, {'analyzed', 'reported', 'approved'})
                update(phase='drafting', waiting_for='agent')
                deadline = time.monotonic()+180
                warned = False
                while True:
                    status(uid)
                    reports = latest_reports(uid)
                    complete = all(kind in reports for kind in ('radiology', 'pcp_letter'))
                    waiting_for = 'approve' if complete else 'agent'
                    if state['waiting_for'] != waiting_for:
                        update(waiting_for=waiting_for)
                    if complete and all(value == 'approved' for value in reports.values()):
                        break
                    if not complete and not warned and time.monotonic() >= deadline:
                        worker.log('system', 'Replay draft wait timed out after 180s; still waiting for both drafts and human approval', uid)
                        warned = True
                    await pause()
                update(phase='gap', waiting_for=None)
                deadline = time.monotonic()+gap
                while True:
                    status(uid)
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:
                        break
                    await pause(min(.25, remaining))
            update(replaying=False, phase='done', waiting_for=None)
        except _ReplayStopped:
            update(replaying=False, phase='stopped', waiting_for=None)
        except Exception as exc:
            worker.log('system', f'Replay failed: {exc}', None)
            update(replaying=False, phase='failed', waiting_for=None)

    async def stop_locked():
        stop_event.set()
        if replay_task and not replay_task.done():
            await asyncio.shield(replay_task)
        else:
            update(replaying=False, phase='stopped', waiting_for=None)

    async def stop():
        async with lifecycle:
            await stop_locked()

    worker.stop_demo = stop

    async def body(request):
        try:
            value = await request.json()
        except (ValueError, UnicodeDecodeError):
            return None
        return value if isinstance(value, dict) else None

    @app.post('/api/demo/drop')
    async def demo_drop(request: Request):
        denied = gate(request, 'demo')
        if denied is not None: return denied
        values = await body(request)
        if values is None:
            return JSONResponse({'error': 'JSON object required'}, status_code=422)
        async with lifecycle:
            if state['replaying']:
                return JSONResponse({'error': 'replay running'}, status_code=409)
            value, code = await asyncio.to_thread(drop, values.get('patient_id'), values.get('timepoint'))
        return JSONResponse(value, status_code=code)

    @app.post('/api/demo/reset')
    async def reset(request: Request):
        denied = gate(request, 'demo')
        if denied is not None: return denied
        values = await body(request)
        if values is None:
            return JSONResponse({'error': 'JSON object required'}, status_code=422)
        async with lifecycle:
            await stop_locked()
            with worker.jobs_lock:
                if any(j['state'] in ('queued', 'running') for j in worker.jobs.values()):
                    return JSONResponse({'error': 'analysis running'}, status_code=409)
                selected = values.get('patient_ids')
                if selected is None and not values.get('empty'):
                    selected = [path.name for path in (worker.config.home/'backlog').iterdir() if path.is_dir()]
                    if worker.config.fake_seed:
                        selected.extend(row['patient_id'] for row in worker.registry.all("SELECT patient_id FROM patients WHERE cohort='fixture'"))
                removed = await asyncio.to_thread(worker.intake.reset, selected, bool(values.get('empty')))
                worker.jobs = {key: job for key, job in worker.jobs.items() if job['study_uid'] not in removed}
                for uid in removed:
                    worker.analysis_modes.pop(uid, None)
            if worker.config.fake_seed and not values.get('empty'):
                worker.seed()
            worker.netstats.reset()
            worker.events.emit('worklist_changed', {'reason': 'reset', 'study_uid': None})
            update(replaying=False, patient_id=None, timepoint=None, speed=1, mode='live', phase='idle', waiting_for=None)
            worker.log('system', 'Demo reset; human confirmation and approval required', None)
        return {'ok': True}

    @app.get('/api/demo/state')
    async def demo_state(request: Request):
        denied = gate(request, 'demo')
        if denied is not None: return denied
        return dict(state)

    @app.post('/api/demo/replay')
    async def start_replay(request: Request):
        nonlocal replay_task, stop_event
        denied = gate(request, 'demo')
        if denied is not None: return denied
        values = await body(request)
        if values is None:
            return JSONResponse({'error': 'JSON object required'}, status_code=422)
        if values.get('autoconfirm'):
            return JSONResponse({'error': 'only a human confirms diameters'}, status_code=403)
        pid = values.get('patient_id')
        tps = values.get('timepoints', ['T0', 'T1'])
        mode = values.get('mode', 'live')
        try:
            if isinstance(values.get('speed'), bool) or isinstance(values.get('gap_s'), bool):
                raise ValueError
            speed, gap = float(values.get('speed', 1)), float(values.get('gap_s', 3))
            valid_tps = isinstance(tps, list) and bool(tps) and all(tp in ('T0', 'T1', 'T2') for tp in tps)
            if not valid_patient(pid) or not valid_tps or tps != sorted(set(tps)) or mode not in ('live', 'cached') or not math.isfinite(speed) or not math.isfinite(gap) or speed <= 0 or gap < 0 or not math.isfinite(gap/speed):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            return JSONResponse({'error': 'invalid replay parameters'}, status_code=422)
        async with lifecycle:
            if state['replaying']:
                return JSONResponse({'error': 'replay running'}, status_code=409)
            for tp in tps:
                existing = existing_study(pid, tp)
                if existing:
                    return JSONResponse({'error': 'already dropped', 'study_uid': existing['study_uid']}, status_code=409)
            stop_event = asyncio.Event()
            update(replaying=True, patient_id=pid, timepoint=None, phase='dropping', waiting_for=None, speed=speed, mode=mode)
            replay_task = asyncio.create_task(replay(pid, tps, gap/speed))
            return dict(state)

    @app.post('/api/demo/stop')
    async def stop_replay(request: Request):
        denied = gate(request, 'demo')
        if denied is not None: return denied
        await stop()
        return dict(state)
