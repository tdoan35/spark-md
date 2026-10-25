import asyncio
import time

from fastapi import Request
from fastapi.responses import JSONResponse


def install_demo(app, worker, gate):
    state = {'replaying': False, 'patient_id': None, 'timepoint': None, 'speed': 1, 'mode': 'live', 'waiting_for': None, 'phase': 'idle'}
    replay_task = None

    def update(**changes):
        state.update(changes)
        worker.events.emit('demo_state', dict(state))

    def drop(pid, tp):
        if not isinstance(pid, str) or '/' in pid or '\\' in pid or pid in ('.', '..') or tp not in ('T0', 'T1', 'T2'):
            return {'error': 'invalid patient/timepoint'}, 422
        existing = worker.registry.one('SELECT study_uid FROM studies WHERE patient_id=? AND timepoint=?', (pid, tp))
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

    async def replay(pid, tps, mode, gap):
        try:
            for tp in tps:
                update(phase='dropping', timepoint=tp, waiting_for=None)
                value, code = await asyncio.to_thread(drop, pid, tp)
                if code != 200:
                    raise ValueError(value['error'])
                uid = value['study_uid']
                if mode == 'cached':
                    worker.log('system', 'Cached mode: results may be reused from an earlier run', uid)
                update(phase='analyzing', waiting_for='agent')
                while True:
                    status = worker.registry.one('SELECT status FROM studies WHERE study_uid=?', (uid,))['status']
                    if status == 'failed': raise ValueError('analysis failed')
                    if status in ('awaiting_confirmation', 'analyzed', 'reported', 'approved'): break
                    await asyncio.sleep(.25)
                update(phase='waiting_confirm', waiting_for='confirm')
                while worker.registry.one('SELECT status FROM studies WHERE study_uid=?', (uid,))['status'] == 'awaiting_confirmation':
                    await asyncio.sleep(.25)
                update(phase='drafting', waiting_for='agent')
                deadline = time.monotonic()+180
                while not worker.registry.one('SELECT report_id FROM reports WHERE study_uid=?', (uid,)):
                    if time.monotonic() > deadline:
                        worker.log('system', 'Replay draft wait timed out; continuing without automatic approval', uid)
                        break
                    await asyncio.sleep(.25)
                update(phase='gap', waiting_for=None)
                await asyncio.sleep(gap)
            update(replaying=False, phase='done', waiting_for=None)
        except asyncio.CancelledError:
            update(replaying=False, phase='stopped', waiting_for=None)
        except Exception as exc:
            worker.log('system', f'Replay failed: {exc}', None)
            update(replaying=False, phase='failed', waiting_for=None)

    @app.post('/api/demo/drop')
    async def demo_drop(request: Request):
        denied = gate(request, 'demo')
        if denied is not None: return denied
        body = await request.json()
        value, code = await asyncio.to_thread(drop, body.get('patient_id'), body.get('timepoint'))
        return JSONResponse(value, status_code=code)

    @app.post('/api/demo/reset')
    async def reset(request: Request):
        nonlocal replay_task
        denied = gate(request, 'demo')
        if denied is not None: return denied
        body = await request.json()
        if replay_task and not replay_task.done():
            replay_task.cancel()
            await replay_task
        with worker.jobs_lock:
            if any(j['state'] in ('queued', 'running') for j in worker.jobs.values()):
                return JSONResponse({'error': 'analysis running'}, status_code=409)
            selected = body.get('patient_ids')
            if selected is None and not body.get('empty'):
                selected = [path.name for path in (worker.config.home/'backlog').iterdir() if path.is_dir()]
                if worker.config.fake_seed:
                    selected.extend(row['patient_id'] for row in worker.registry.all("SELECT patient_id FROM patients WHERE cohort='fixture'"))
            removed = await asyncio.to_thread(worker.intake.reset, selected, bool(body.get('empty')))
            worker.jobs = {key: job for key, job in worker.jobs.items() if job['study_uid'] not in removed}
        if worker.config.fake_seed and not body.get('empty'):
            worker.seed()
        worker.events.emit('worklist_changed', {'reason': 'reset', 'study_uid': None})
        update(replaying=False, patient_id=None, timepoint=None, phase='idle', waiting_for=None)
        worker.log('system', 'Demo reset; human confirmation and approval required', None)
        return {'ok': True}

    @app.get('/api/demo/state')
    async def demo_state():
        return state

    @app.post('/api/demo/replay')
    async def start_replay(request: Request):
        nonlocal replay_task
        denied = gate(request, 'demo')
        if denied is not None: return denied
        if state['replaying']:
            return JSONResponse({'error': 'replay running'}, status_code=409)
        body = await request.json()
        if body.get('autoconfirm'):
            return JSONResponse({'error': 'only a human confirms diameters'}, status_code=403)
        pid = body.get('patient_id')
        tps = body.get('timepoints', ['T0', 'T1'])
        mode = body.get('mode', 'live')
        speed, gap = float(body.get('speed', 1)), float(body.get('gap_s', 3))
        if not isinstance(pid, str) or not isinstance(tps, list) or not tps or any(tp not in ('T0','T1','T2') for tp in tps) or mode not in ('live','cached') or speed <= 0 or gap < 0:
            return JSONResponse({'error': 'invalid replay parameters'}, status_code=422)
        update(replaying=True, patient_id=pid, timepoint=None, phase='dropping', waiting_for=None, speed=speed, mode=mode)
        replay_task = asyncio.create_task(replay(pid, tps, mode, gap/speed))
        return dict(state)

    @app.post('/api/demo/stop')
    async def stop_replay(request: Request):
        denied = gate(request, 'demo')
        if denied is not None: return denied
        if replay_task and not replay_task.done():
            replay_task.cancel()
            await replay_task
        else:
            update(replaying=False, phase='stopped', waiting_for=None)
        return dict(state)
