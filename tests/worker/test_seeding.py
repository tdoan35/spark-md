"""Reset seeds real intake/cache paths; no background clinical or agent actions."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx

from sparkmd.config import Config
from sparkmd.demo import install_demo
from sparkmd.findings import findings
from sparkmd.netstats import NetStats
from sparkmd.worker import Worker
from tests.worker.test_state import dicom


class ResetSeeding(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.entries = []
        offsets = ['patient_id,rank,day_offset']
        for index, (pid, cohort) in enumerate((('control-a', 'nlst_ctrl'), ('control-b', 'nlst_ctrl'), ('control-c', 'nlst_ctrl'), ('LIDC-case', 'lidc')), 1):
            for rank in range(3 if cohort == 'nlst_ctrl' else 1):
                uid = f'1.2.826.0.1.3680043.10.999.{index}.{rank}'
                sid = uid+'.1'
                tp = f'T{rank}'
                source = self.home/'backlog'/pid/tp
                for _ in range(100):
                    dicom(source, uid, sid, patient=pid, date=f'{2000+rank}0102')
                cache = self.home/'seed-cache'/sid
                cache.mkdir(parents=True)
                (cache/'findings.json').write_text(json.dumps({'pipeline_version': '0.5.0', 'assets': {'key_slices': []}}))
                matching = {'status': 'new', 'prior_nodule_id': None, 'prior_study_uid': None}
                if rank:
                    matching.update(status='matched', prior_nodule_id=pid+('-N1' if rank == 1 else '-T1-N1'),
                                    prior_study_uid=f'1.2.826.0.1.3680043.10.999.{index}.{rank-1}')
                (cache/'nodules.json').write_text(json.dumps([{
                    'nodule_id': pid+('-N1' if rank == 0 else f'-{tp}-N1'), 'track_id': pid+'-track', 'center_mm': [10, 20, 30],
                    'lobe': 'LUL (approximate)', 'matching': matching,
                    'proposed_long_mm': 8+rank, 'proposed_short_mm': 5+rank, 'proposed_mean_mm': 6.5+rank,
                    'proposal_source': 'A7', 'proposal_reason': None, 'box_mean_mm': 7+rank,
                    'mean_hu': -100, 'type': 'solid', 'det_score': .99,
                }]))
                self.entries.append({'patient_id': pid, 'cohort': cohort, 'timepoint': tp, 'study_uid': uid, 'series_uid': sid})
                if cohort == 'nlst_ctrl':
                    days = ((56, 382, 746), (0, 334, 735), (6, 344, 704))[index-1]
                    offsets.append(f'{pid},{rank},{days[rank]}')
        (self.home/'day_offsets.csv').write_text('\n'.join(offsets)+'\n')
        self.manifest = self.home/'demo-seeds.json'
        self.manifest.write_text(json.dumps(self.entries[::-1]))
        self.manifest_patch = patch('sparkmd.seeding.MANIFEST', self.manifest)
        self.manifest_patch.start()
        self.worker = Worker(Config(home=self.home, fake=False, fake_seed=False, hook_url='', hook_token=''))
        self.app = FastAPI()

        @self.app.exception_handler(ValueError)
        async def invalid(_request, exc):
            return JSONResponse({'error': str(exc)}, status_code=422)

        install_demo(self.app, self.worker, lambda *_args: None)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=('127.0.0.1', 1234)), base_url='http://test')
        self.no_detector = patch('sparkmd.imaging.run_analysis', side_effect=AssertionError('reset invoked detector'))
        self.no_hook = patch.object(self.worker, 'trigger', side_effect=AssertionError('seed dispatched agent'))
        self.no_detector.start()
        self.no_hook.start()

    async def asyncTearDown(self):
        await self.worker.stop_demo()
        self.worker.stop.set()
        for thread in self.worker.threads:
            thread.join()
        self.no_hook.stop()
        self.no_detector.stop()
        await self.client.aclose()
        self.worker.registry.close()
        self.manifest_patch.stop()
        self.tmp.cleanup()

    async def test_reset_seeds_only_four_pending_cohort_patients(self):
        # A prior hero row is reset, never silently re-seeded or analyzed.
        with self.worker.registry.transaction() as db:
            db.execute("INSERT INTO patients(patient_id) VALUES ('134503')")
            db.execute("INSERT INTO studies(study_uid,patient_id,timepoint,status,received_at) VALUES ('hero','134503','T0','organized','synthetic')")
        (self.home/'backlog'/'134503'/'T0').mkdir(parents=True)
        response = await self.client.post('/api/demo/reset', json={})
        self.assertEqual(response.status_code, 200, response.text)
        seeded = response.json()['seeded']
        self.assertEqual({s['patient_id'] for s in seeded}, {'control-a', 'control-b', 'control-c', 'LIDC-case'})
        self.assertEqual(len(seeded), 10)
        self.assertEqual({s['timepoint'] for s in seeded if s['patient_id'] == 'control-a'}, {'T0', 'T1', 'T2'})
        self.assertTrue(all(s['mode'] == 'cached' and s['status'] == 'awaiting_confirmation' for s in seeded))
        self.assertEqual(self.worker.registry.all("SELECT * FROM studies WHERE patient_id='134503'"), [])
        rows = self.worker.worklist()
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(row['mode'] == 'cached' and row['status'] == 'awaiting_confirmation' and row['lung_rads'] is None for row in rows))
        cohorts = {row['patient_id']: row['cohort'] for row in self.worker.registry.all('SELECT * FROM patients')}
        self.assertEqual([cohorts['control-a'], cohorts['control-b'], cohorts['control-c'], cohorts['LIDC-case']], ['nlst_ctrl', 'nlst_ctrl', 'nlst_ctrl', 'lidc'])
        for row in rows:
            ui, _ = findings(self.worker, row['study_uid'])
            self.assertEqual(ui['nodules'][0]['proposal']['mean_mm'], 6.5+int(row['timepoint'][1:]))
            self.assertIsNone(ui['nodules'][0]['mean_mm'])
            self.assertFalse(ui['nodules'][0]['confirmation']['confirmed'])
            self.assertIsNone(ui['assessment'])
            agent, _ = findings(self.worker, row['study_uid'], True)
            self.assertNotIn('proposal', agent['nodules'][0])
        for table in ('assessments', 'reports', 'outbox'):
            self.assertEqual(self.worker.registry.all('SELECT * FROM '+table), [])
        jobs = sorted(self.worker.jobs.values(), key=lambda job: job['started'])
        self.assertTrue(all(job['mode'] == 'cached' for job in jobs))
        self.assertTrue(all(previous['ended'] <= following['started'] for previous, following in zip(jobs, jobs[1:])))

    async def test_repeated_and_cold_resets_reseed_without_duplicates(self):
        for body in ({}, {}, {'empty': True}):
            response = await self.client.post('/api/demo/reset', json=body)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(self.worker.registry.all('SELECT * FROM studies')), 10)
            self.assertEqual(len(self.worker.registry.all('SELECT * FROM nodules')), 10)
            self.assertTrue(all(row['confirmed_at'] is None for row in self.worker.registry.all('SELECT * FROM nodules')))
            self.assertEqual(self.worker.registry.all('SELECT * FROM assessments'), [])
        self.assertTrue(all((self.home/'seed-cache'/entry['series_uid']/'nodules.json').exists() for entry in self.entries))

    async def test_missing_cache_preflight_preserves_existing_registry(self):
        response = await self.client.post('/api/demo/reset', json={})
        self.assertEqual(response.status_code, 200)
        before = self.worker.registry.all('SELECT * FROM studies ORDER BY study_uid')
        path = self.home/'seed-cache'/self.entries[1]['series_uid']/'nodules.json'
        path.unlink()
        response = await self.client.post('/api/demo/reset', json={})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.worker.registry.all('SELECT * FROM studies ORDER BY study_uid'), before)

    async def test_failed_A7_proposal_remains_pending_for_manual_measurement(self):
        entry = next(e for e in self.entries if e['patient_id'] == 'control-c' and e['timepoint'] == 'T1')
        path = self.home/'seed-cache'/entry['series_uid']/'nodules.json'
        nodes = json.loads(path.read_text())
        nodes[0].update(proposed_long_mm=None, proposed_short_mm=None, proposed_mean_mm=None,
                        proposal_reason='core_below_minus600_hu')
        path.write_text(json.dumps(nodes))
        response = await self.client.post('/api/demo/reset', json={})
        self.assertEqual(response.status_code, 200, response.text)
        data, _ = findings(self.worker, entry['study_uid'])
        self.assertEqual(data['pending_confirmation'], ['control-c-T1-N1'])
        self.assertIsNone(data['nodules'][0]['proposal']['mean_mm'])
        self.assertEqual(data['nodules'][0]['proposal']['reason'], 'core_below_minus600_hu')
        followup = next(e for e in self.entries if e['patient_id'] == 'control-c' and e['timepoint'] == 'T2')
        compared, _ = findings(self.worker, followup['study_uid'])
        self.assertIsNone(compared['nodules'][0]['prior']['proposal']['mean_mm'])
        self.assertEqual(compared['nodules'][0]['prior']['proposal']['reason'], 'core_below_minus600_hu')
        self.assertIsNone(data['assessment'])
        self.assertEqual(self.worker.registry.all('SELECT * FROM reports'), [])

    async def test_cached_row_mode_survives_worker_restart(self):
        response = await self.client.post('/api/demo/reset', json={})
        self.assertEqual(response.status_code, 200)
        restarted = Worker(Config(home=self.home, fake=False, fake_seed=False, hook_url='', hook_token=''))
        try:
            rows = restarted.worklist()
            self.assertEqual(len(rows), 10)
            self.assertTrue(all(row['mode'] == 'cached' for row in rows))
        finally:
            restarted.registry.close()

    async def test_reset_zero_snapshot_and_subsequent_physical_traffic(self):
        root = self.home/'net'
        interface = root/'lan'
        (interface/'device').mkdir(parents=True)
        (interface/'statistics').mkdir()
        (interface/'operstate').write_text('up')
        tx, rx = interface/'statistics'/'tx_bytes', interface/'statistics'/'rx_bytes'
        tx.write_text('100')
        rx.write_text('200')
        self.worker.netstats = NetStats(root)
        tx.write_text('150')
        rx.write_text('250')
        self.assertEqual(self.worker.netstats.sample()['tx_bytes'], 50)
        response = await self.client.post('/api/demo/reset', json={})
        self.assertEqual(response.status_code, 200)
        snapshot = response.json()['net_stats']
        self.assertEqual((snapshot['tx_bytes'], snapshot['rx_bytes']), (0, 0))
        events = [frame for _, frame in self.worker.events.history if 'event: net_stats' in frame.splitlines()]
        self.assertEqual(json.loads(events[-1].split('data: ', 1)[1]), snapshot)
        tx.write_text('158')
        rx.write_text('263')
        after = self.worker.netstats.sample()
        self.assertEqual((after['tx_bytes'], after['rx_bytes']), (8, 13))
        self.assertEqual(after['since'], snapshot['since'])

    async def test_control_history_keeps_real_offsets_and_prior_proposals_ui_only(self):
        response = await self.client.post('/api/demo/reset', json={})
        self.assertEqual(response.status_code, 200, response.text)
        entries = [e for e in self.entries if e['patient_id'] == 'control-a']
        study, code = self.worker.study(entries[2]['study_uid'])
        self.assertEqual(code, 200)
        self.assertEqual([(p['timepoint'], p['day_offset']) for p in study['priors']], [('T1', 382), ('T0', 56)])
        self.assertEqual((study['day_offset'], study['day_offset_source']), (746, 'sidecar'))
        for rank in (1, 2):
            ui, _ = findings(self.worker, entries[rank]['study_uid'])
            prior = ui['nodules'][0]['prior']
            self.assertEqual(prior['study_uid'], entries[rank-1]['study_uid'])
            self.assertEqual(prior['proposal']['mean_mm'], 6.5+rank-1)
            self.assertEqual(prior['interval_days'], (326, 364)[rank-1])
            self.assertFalse(prior['confirmation']['confirmed'])
            for field in ('mean_mm', 'volume_mm3', 'delta_mean_mm', 'growth_per_12mo_mm', 'vdt_days', 'growing'):
                self.assertIsNone(prior[field], field)
            agent, _ = findings(self.worker, entries[rank]['study_uid'], True)
            self.assertIsNone(agent['nodules'][0]['prior'])
            for field in ('proposal', 'mean_mm', 'long_mm', 'short_mm', 'volume_mm3'):
                self.assertNotIn(field, agent['nodules'][0])
        tracks = self.worker.registry.all("SELECT first_study_uid FROM tracks WHERE patient_id='control-a'")
        self.assertEqual(tracks, [{'first_study_uid': entries[0]['study_uid']}])

    async def test_empty_followup_stays_pending_without_assessment_or_phase_two(self):
        entry = next(e for e in self.entries if e['patient_id'] == 'control-a' and e['timepoint'] == 'T2')
        (self.home/'seed-cache'/entry['series_uid']/'nodules.json').write_text('[]')
        response = await self.client.post('/api/demo/reset', json={})
        self.assertEqual(response.status_code, 200, response.text)
        data, _ = findings(self.worker, entry['study_uid'])
        self.assertEqual(data['nodules'], [])
        self.assertIsNone(data['assessment'])
        self.assertEqual(self.worker.registry.one('SELECT status,mode FROM studies WHERE study_uid=?', (entry['study_uid'],)),
                         {'status': 'awaiting_confirmation', 'mode': 'cached'})
        self.assertEqual(self.worker.registry.all('SELECT * FROM reports'), [])

    async def test_missing_followup_offset_preserves_existing_worklist(self):
        response = await self.client.post('/api/demo/reset', json={})
        self.assertEqual(response.status_code, 200)
        before = self.worker.registry.all('SELECT * FROM studies ORDER BY study_uid')
        path = self.home/'day_offsets.csv'
        path.write_text('\n'.join(line for line in path.read_text().splitlines() if not line.startswith('control-a,2,'))+'\n')
        response = await self.client.post('/api/demo/reset', json={})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.worker.registry.all('SELECT * FROM studies ORDER BY study_uid'), before)

    async def test_unlinked_tracks_keep_prior_proposal_history_without_inventing_matches(self):
        entries = [e for e in self.entries if e['patient_id'] == 'control-a']
        for entry in entries[1:]:
            path = self.home/'seed-cache'/entry['series_uid']/'nodules.json'
            nodes = json.loads(path.read_text())
            nodes[0]['track_id'] += '-'+entry['timepoint']
            nodes[0]['matching'].update(status='unresolved', prior_nodule_id=None, flags=['distance_above_5mm'])
            path.write_text(json.dumps(nodes))
        response = await self.client.post('/api/demo/reset', json={})
        self.assertEqual(response.status_code, 200, response.text)
        for rank in (1, 2):
            ui, _ = findings(self.worker, entries[rank]['study_uid'])
            self.assertIsNone(ui['nodules'][0]['prior'])
            self.assertEqual(ui['nodules'][0]['matching']['status'], 'unresolved')
            self.assertEqual(ui['nodules'][0]['matching']['prior_study_uid'], entries[rank-1]['study_uid'])
            self.assertEqual([p['timepoint'] for p in ui['priors']], [f'T{r}' for r in range(rank-1, -1, -1)])
            self.assertEqual(ui['priors'][0]['nodules'][0]['proposal']['mean_mm'], 6.5+rank-1)
            self.assertFalse(ui['priors'][0]['nodules'][0]['confirmation']['confirmed'])
            agent, _ = findings(self.worker, entries[rank]['study_uid'], True)
            self.assertNotIn('priors', agent)
            self.assertNotIn('matching', agent['nodules'][0])

    async def test_manifest_cannot_seed_hero(self):
        self.entries[0]['patient_id'] = '134503'
        self.manifest.write_text(json.dumps(self.entries))
        response = await self.client.post('/api/demo/reset', json={})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.worker.registry.all('SELECT * FROM studies'), [])


if __name__ == '__main__':
    unittest.main()
