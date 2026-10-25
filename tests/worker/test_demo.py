import asyncio
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from sparkmd.demo import install_demo
from sparkmd.registry import Registry


class Events:
    def __init__(self):
        self.items = []

    def emit(self, kind, value):
        self.items.append((kind, dict(value)))


class Intake:
    def __init__(self, worker):
        self.worker = worker
        self.drops = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.initial_status = 'awaiting_confirmation'
        self.resets = []

    def ingest_study(self, source):
        self.started.set()
        self.release.wait()
        pid, tp = source.parent.name, source.name
        uid = pid+'-'+tp
        with self.worker.registry.transaction() as db:
            db.execute('INSERT OR IGNORE INTO patients(patient_id) VALUES (?)', (pid,))
            db.execute('INSERT INTO studies(study_uid,patient_id,timepoint,status,received_at) VALUES (?,?,?,?,?)',
                       (uid, pid, tp, self.initial_status, 'synthetic'))
        self.drops.append(uid)
        return uid

    def reset(self, selected, empty):
        self.resets.append((selected, empty))
        rows = self.worker.registry.all('SELECT study_uid,patient_id FROM studies')
        removed = [row['study_uid'] for row in rows if selected is None or row['patient_id'] in selected]
        with self.worker.registry.transaction() as db:
            for uid in removed:
                db.execute('DELETE FROM studies WHERE study_uid=?', (uid,))
        return removed


class DemoReplay(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        home = Path(self.tmp.name)
        for tp in ('T0', 'T1', 'T2'):
            (home/'backlog'/'hero'/tp).mkdir(parents=True)
        self.worker = SimpleNamespace(
            config=SimpleNamespace(home=home, fake_seed=False), registry=Registry(home/'registry.sqlite'),
            jobs_lock=threading.RLock(), jobs={}, events=Events(), logs=[], netstats_resets=0, seeds=0,
        )
        self.worker.log = lambda *args: self.worker.logs.append(args)
        self.worker.netstats = SimpleNamespace(reset=self.reset_netstats)
        self.worker.seed = self.seed
        self.worker.intake = Intake(self.worker)
        self.worker.analysis_modes = {}
        self.app = FastAPI()

        def gate(request, operation):
            if request.client and request.client.host == '127.0.0.1' and request.headers.get('X-SparkMD-Caller') != 'agent':
                return None
            return JSONResponse({'error': operation+'_loopback_only'}, status_code=403)

        install_demo(self.app, self.worker, gate)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=('127.0.0.1', 1234)), base_url='http://test')

    async def asyncTearDown(self):
        self.worker.intake.release.set()
        await self.worker.stop_demo()
        await self.client.aclose()
        self.worker.registry.close()
        self.tmp.cleanup()

    def reset_netstats(self):
        self.worker.netstats_resets += 1

    def seed(self):
        self.worker.seeds += 1

    async def until(self, predicate):
        async def wait():
            while not predicate():
                await asyncio.sleep(.01)
        await asyncio.wait_for(wait(), 4)

    async def phase(self, phase, waiting_for=None):
        await self.until(lambda: self.worker.demo_state['phase'] == phase and self.worker.demo_state['waiting_for'] == waiting_for)

    async def start(self, **values):
        response = await self.client.post('/api/demo/replay', json={'patient_id': 'hero', 'gap_s': 0, **values})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def status(self, value, uid='hero-T0'):
        with self.worker.registry.transaction() as db:
            db.execute('UPDATE studies SET status=? WHERE study_uid=?', (value, uid))

    def report(self, kind, version=1, status='draft', uid='hero-T0'):
        rid = f'{uid}-{kind}-{version}'
        with self.worker.registry.transaction() as db:
            db.execute('INSERT INTO reports(report_id,study_uid,kind,markdown,version,status) VALUES (?,?,?,?,?,?)',
                       (rid, uid, kind, 'synthetic human-gated report', version, status))
        return rid

    def approve(self, rid):
        with self.worker.registry.transaction() as db:
            db.execute("UPDATE reports SET status='approved',approved_by='test-human' WHERE report_id=?", (rid,))

    async def test_two_phase_waits_for_confirmation_and_both_human_approvals(self):
        self.worker.intake.initial_status = 'organized'
        initial = await self.start(mode='cached', speed=2)
        self.assertEqual(initial['mode'], 'cached')
        self.assertEqual(initial['speed'], 2)
        await self.phase('analyzing', 'agent')
        self.assertEqual(self.worker.intake.drops, ['hero-T0'])
        self.assertEqual(self.worker.registry.all('SELECT * FROM reports'), [])
        self.status('awaiting_confirmation')
        await self.phase('waiting_confirm', 'confirm')
        self.assertEqual(self.worker.intake.drops, ['hero-T0'])
        self.status('analyzed')  # The simulated human action, never a harness call.
        await self.phase('drafting', 'agent')
        radiology = self.report('radiology')
        await asyncio.sleep(.3)
        self.assertEqual(self.worker.demo_state['waiting_for'], 'agent')
        letter = self.report('pcp_letter')
        await self.phase('drafting', 'approve')
        self.approve(radiology)
        await asyncio.sleep(.3)
        self.assertEqual(self.worker.intake.drops, ['hero-T0'])
        self.approve(letter)
        await self.until(lambda: self.worker.demo_state['timepoint'] == 'T1')
        await self.phase('analyzing', 'agent')
        self.status('awaiting_confirmation', 'hero-T1')
        await self.phase('waiting_confirm', 'confirm')
        self.status('analyzed', 'hero-T1')
        self.report('radiology', status='approved', uid='hero-T1')
        self.report('pcp_letter', status='approved', uid='hero-T1')
        await self.phase('done')
        self.assertFalse(self.worker.demo_state['replaying'])
        fields = {'replaying', 'patient_id', 'timepoint', 'speed', 'mode', 'waiting_for', 'phase'}
        states = [value for kind, value in self.worker.events.items if kind == 'demo_state']
        self.assertTrue(all(set(value) == fields for value in states))
        self.assertTrue(all(value['mode'] == 'cached' for value in states))
        self.assertIn('waiting_confirm', [value['phase'] for value in states])
        self.assertIn('gap', [value['phase'] for value in states])

    async def test_latest_reports_must_both_be_approved(self):
        await self.start()
        await self.phase('waiting_confirm', 'confirm')
        self.status('reported')
        self.report('radiology', status='approved')
        self.report('pcp_letter', status='approved')
        latest_rad = self.report('radiology', version=2)
        latest_letter = self.report('pcp_letter', version=2)
        await self.phase('drafting', 'approve')
        self.assertEqual(self.worker.intake.drops, ['hero-T0'])
        self.approve(latest_rad)
        await asyncio.sleep(.3)
        self.assertEqual(self.worker.intake.drops, ['hero-T0'])
        self.approve(latest_letter)
        await self.until(lambda: 'hero-T1' in self.worker.intake.drops)

    async def test_missing_draft_warns_after_180_seconds_without_advancing(self):
        clock = [0]
        with patch('sparkmd.demo.time', SimpleNamespace(monotonic=lambda: clock[0])):
            await self.start()
            await self.phase('waiting_confirm', 'confirm')
            self.status('analyzed')
            await self.phase('drafting', 'agent')
            self.report('radiology')
            logged_before_timeout = len(self.worker.logs)
            clock[0] = 181
            await self.until(lambda: len(self.worker.logs) > logged_before_timeout)
            self.assertEqual(self.worker.demo_state['phase'], 'drafting')
            self.assertEqual(self.worker.demo_state['waiting_for'], 'agent')
            self.assertEqual(self.worker.intake.drops, ['hero-T0'])

    async def test_duplicate_running_and_existing_replay_return_409(self):
        await self.start()
        await self.phase('waiting_confirm', 'confirm')
        response = await self.client.post('/api/demo/replay', json={'patient_id': 'hero'})
        self.assertEqual(response.status_code, 409)
        await self.worker.stop_demo()
        self.status('approved')
        response = await self.client.post('/api/demo/replay', json={'patient_id': 'hero'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['study_uid'], 'hero-T0')
        self.assertEqual(self.worker.registry.one('SELECT status FROM studies')['status'], 'approved')
        self.assertEqual(self.worker.intake.resets, [])
        self.assertEqual(self.worker.intake.drops, ['hero-T0'])

    async def test_stop_during_confirmation_preserves_registry_and_prevents_next_drop(self):
        await self.start()
        await self.phase('waiting_confirm', 'confirm')
        before = self.worker.registry.all('SELECT * FROM studies')
        response = await asyncio.wait_for(self.client.post('/api/demo/stop'), 1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['phase'], 'stopped')
        self.assertEqual(self.worker.registry.all('SELECT * FROM studies'), before)
        self.assertEqual(self.worker.intake.drops, ['hero-T0'])

    async def test_stop_waits_for_inflight_ingest_to_settle(self):
        self.worker.intake.release.clear()
        await self.start()
        self.assertTrue(await asyncio.to_thread(self.worker.intake.started.wait, 2))
        stopped = asyncio.create_task(self.client.post('/api/demo/stop'))
        try:
            await asyncio.sleep(.05)
            self.assertFalse(stopped.done())
            self.assertEqual(self.worker.intake.drops, [])
        finally:
            self.worker.intake.release.set()
        response = await asyncio.wait_for(stopped, 2)
        self.assertEqual(response.json()['phase'], 'stopped')
        self.assertEqual(self.worker.intake.drops, ['hero-T0'])
        self.assertEqual(self.worker.registry.one('SELECT status FROM studies')['status'], 'awaiting_confirmation')

    async def test_failure_at_every_wait_does_not_advance(self):
        for phase, waiting in [('analyzing', 'agent'), ('waiting_confirm', 'confirm'), ('drafting', 'agent'), ('drafting', 'approve'), ('gap', None)]:
            with self.subTest(phase=phase, waiting_for=waiting):
                response = await self.client.post('/api/demo/reset', json={'empty': True})
                self.assertEqual(response.status_code, 200)
                self.worker.intake.drops.clear()
                self.worker.intake.initial_status = 'organized' if phase == 'analyzing' else 'awaiting_confirmation'
                await self.start(gap_s=30)
                if phase not in ('analyzing', 'waiting_confirm'):
                    await self.phase('waiting_confirm', 'confirm')
                    self.status('analyzed')
                    if waiting == 'approve' or phase == 'gap':
                        report_status = 'approved' if phase == 'gap' else 'draft'
                        self.report('radiology', status=report_status)
                        self.report('pcp_letter', status=report_status)
                await self.phase(phase, waiting)
                self.status('failed')
                await self.phase('failed')
                self.assertFalse(self.worker.demo_state['replaying'])
                self.assertEqual(self.worker.intake.drops, ['hero-T0'])

    async def test_reset_serializes_with_ingest_and_rebaselines_after_success(self):
        self.worker.intake.release.clear()
        await self.start()
        self.assertTrue(await asyncio.to_thread(self.worker.intake.started.wait, 2))
        reset = asyncio.create_task(self.client.post('/api/demo/reset', json={'empty': True}))
        try:
            await asyncio.sleep(.05)
            self.assertFalse(reset.done())
            self.assertEqual(self.worker.intake.resets, [])
            self.assertEqual(self.worker.netstats_resets, 0)
        finally:
            self.worker.intake.release.set()
        self.assertEqual((await asyncio.wait_for(reset, 2)).status_code, 200)
        self.assertEqual(self.worker.registry.all('SELECT * FROM studies'), [])
        self.assertEqual(self.worker.netstats_resets, 1)
        self.assertEqual(self.worker.demo_state['phase'], 'idle')
        self.assertEqual(self.worker.intake.drops, ['hero-T0'])

    async def test_reset_refuses_running_jobs_without_rebaselining(self):
        self.worker.jobs['analysis'] = {'state': 'running', 'study_uid': 'hero-T0'}
        response = await self.client.post('/api/demo/reset', json={})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.worker.netstats_resets, 0)
        self.assertEqual(self.worker.intake.resets, [])

    async def test_fake_seed_and_normal_drop_contracts_are_preserved(self):
        self.worker.config.fake_seed = True
        with self.worker.registry.transaction() as db:
            db.execute("INSERT INTO patients(patient_id,cohort) VALUES ('fixture', 'fixture')")
        response = await self.client.post('/api/demo/reset', json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(self.worker.intake.resets[-1][0]), {'hero', 'fixture'})
        self.assertEqual(self.worker.seeds, 1)
        self.assertEqual(self.worker.netstats_resets, 1)
        response = await self.client.post('/api/demo/drop', json={'patient_id': 'hero', 'timepoint': 'T0'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'study_uid': 'hero-T0', 'status': 'organized'})
        self.assertEqual((await self.client.post('/api/demo/drop', json={'patient_id': 'hero', 'timepoint': 'T0'})).status_code, 409)
        self.assertEqual((await self.client.post('/api/demo/drop', json={'patient_id': 'missing', 'timepoint': 'T0'})).status_code, 404)
        self.worker.analysis_modes.update({'hero-T0': 'cached', 'untouched': 'live'})
        response = await self.client.post('/api/demo/reset', json={'empty': True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.worker.seeds, 1)
        self.assertEqual(self.worker.analysis_modes, {'untouched': 'live'})

    async def test_nonloopback_demo_routes_and_agent_caller_are_forbidden(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=('192.0.2.1', 1234)), base_url='http://test') as remote:
            for action in ('drop', 'reset', 'replay', 'stop'):
                self.assertEqual((await remote.post('/api/demo/'+action, json={})).status_code, 403)
            self.assertEqual((await remote.get('/api/demo/state')).status_code, 403)
        response = await self.client.post('/api/demo/replay', headers={'X-SparkMD-Caller': 'agent'}, json={'patient_id': 'hero'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.worker.intake.drops, [])

    async def test_autoconfirm_is_always_refused(self):
        with patch.dict('os.environ', {'SPARKMD_ALLOW_AUTOCONFIRM': '1', 'SPARKMD_RECORDING': '0'}):
            response = await self.client.post('/api/demo/replay', json={'patient_id': 'hero', 'autoconfirm': True})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.worker.demo_state['replaying'])

    async def test_invalid_and_nonfinite_replay_parameters_are_rejected(self):
        invalid = [
            {'patient_id': value} for value in ('', ' ', '.', '..', '../hero', '/hero', 'hero/T0', 'hero\\T0', 'hero\0', None, 123)
        ] + [
            {'timepoints': value} for value in ([], ['T0', 'T0'], ['T1', 'T0'], ['T0', 'T3'], 'T0', [None], [{}])
        ] + [
            {key: value} for key, values in (
                ('speed', (0, -1, 'nan', 'inf', '-inf', 'bad', None, True, {}, 1e-320)),
                ('gap_s', (-1, 'nan', 'inf', '-inf', 'bad', None, False, {})),
                ('mode', ('other', None, [])),
            ) for value in values
        ]
        for values in invalid:
            with self.subTest(values=values):
                response = await self.client.post('/api/demo/replay', json={'patient_id': 'hero', **values})
                self.assertEqual(response.status_code, 422, response.text)
        for route in ('replay', 'drop', 'reset'):
            self.assertEqual((await self.client.post('/api/demo/'+route, json=[])).status_code, 422)
            self.assertEqual((await self.client.post('/api/demo/'+route, content='not json')).status_code, 422)
        self.assertEqual((await self.client.post('/api/demo/drop', json={'patient_id': '../hero', 'timepoint': 'T0'})).status_code, 422)
        self.assertEqual(self.worker.intake.drops, [])


if __name__ == '__main__':
    unittest.main()
