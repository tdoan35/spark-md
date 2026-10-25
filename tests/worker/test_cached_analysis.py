"""Cached demo runs restore proposals, not clinical approval or fresh detection."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sparkmd.config import Config
from sparkmd.findings import findings
from sparkmd.worker import Worker


class CachedAnalysis(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.worker = Worker(Config(home=self.home, fake=False, fake_seed=True))
        self.addCleanup(self.close_worker)
        asyncio.run(self.worker.call_tool('select_series', {
            'study_uid': 'fixture-T0', 'series_uid': 'fixture-T0-soft', 'reason': 'synthetic cache smoke'}))
        self.worker.analysis_modes['fixture-T0'] = 'cached'
        self.cache = self.home/'cache'/'fixture-T0-soft'
        self.cache.mkdir(parents=True)

    def close_worker(self):
        self.worker.stop.set()
        for thread in self.worker.threads:
            thread.join()
        self.worker.registry.close()

    def save_cache(self, *, failed=False):
        proposal = None if failed else 7.7
        (self.cache/'nodules.json').write_text(json.dumps([{
            'nodule_id': 'cached-N1', 'center_mm': [10, 20, 30], 'lobe': 'LUL (approximate)',
            'match_position_mm': [0, 0, 10], 'match_eligible': True,
            'track_id': 'cached-track',
            'matching': {'status': 'new', 'prior_nodule_id': None, 'prior_study_uid': None,
                         'confidence': 'none', 'rule': 'lobe-position-mutual-v1', 'flags': [], 'candidates': []},
            'proposed_long_mm': proposal, 'proposed_short_mm': None if failed else 5.2,
            'proposed_mean_mm': None if failed else 6.5, 'proposal_source': 'A7',
            'proposal_reason': 'no_valid_component' if failed else None,
            'box_mean_mm': 7.1, 'mean_hu': -150, 'type': 'solid', 'det_score': .99,
            'long_mm': 99, 'short_mm': 99, 'mean_mm': 99, 'volume_mm3': 999,
        }]))
        (self.cache/'findings.json').write_text(json.dumps({
            'pipeline_version': '0.4.0', 'assets': {
                'lung_mesh': '/api/studies/fixture-T0/assets/lung.glb',
                'nodule_mesh': '/api/studies/fixture-T0/assets/nodules.glb',
                'key_slices': [], 'slice_stack': {'count': 151, 'index_digits': 3},
            }}))

    def test_cached_proposals_never_restore_confirmed_measurements(self):
        self.save_cache()
        with patch('sparkmd.imaging.run_analysis', side_effect=AssertionError('cached replay invoked imaging')):
            job, code = asyncio.run(self.worker.analyze('fixture-T0', 5))
        self.assertEqual(code, 200)
        self.assertEqual(job['state'], 'done', job)
        self.assertEqual(job['study_status'], 'awaiting_confirmation')
        payload, _ = findings(self.worker, 'fixture-T0')
        nodule = payload['nodules'][0]
        self.assertEqual(nodule['proposal']['mean_mm'], 6.5)
        self.assertEqual(payload['pending_confirmation'], ['cached-N1'])
        self.assertIsNone(payload['assessment'])
        for field in ('long_mm', 'short_mm', 'mean_mm', 'volume_mm3'):
            self.assertIsNone(nodule[field])
        self.assertFalse(nodule['confirmation']['confirmed'])
        self.assertEqual(payload['assets']['slice_stack']['count'], 151)
        agent, _ = findings(self.worker, 'fixture-T0', True)
        self.assertNotIn('proposal', agent['nodules'][0])
        self.assertNotIn('mean_mm', agent['nodules'][0])
        self.assertEqual(self.worker.registry.all('SELECT * FROM reports'), [])
        modes = [json.loads(row['payload_json']).get('mode') for row in self.worker.registry.all('SELECT payload_json FROM agent_events')]
        self.assertIn('cached', modes)

    def test_cached_failure_reason_stays_reviewable(self):
        self.save_cache(failed=True)
        with patch('sparkmd.imaging.run_analysis', side_effect=AssertionError('cached replay invoked imaging')):
            job, _ = asyncio.run(self.worker.analyze('fixture-T0', 5))
        self.assertEqual(job['study_status'], 'awaiting_confirmation')
        payload, _ = findings(self.worker, 'fixture-T0')
        self.assertEqual(payload['nodules'][0]['proposal']['reason'], 'no_valid_component')
        self.assertIsNone(payload['nodules'][0]['proposal']['long_mm'])

    def test_cached_rerun_preserves_confirmed_study_after_restart(self):
        self.save_cache()
        asyncio.run(self.worker.analyze('fixture-T0', 5))
        _, code = self.worker.confirm('cached-N1', {'long_mm': 8, 'short_mm': 6, 'by': 'Synthetic reviewer'})
        self.assertEqual(code, 200)
        self.worker.jobs.clear()  # In-memory jobs do not survive worker restart.
        before = self.worker.registry.one("SELECT * FROM studies WHERE study_uid='fixture-T0'")
        with patch('sparkmd.imaging.run_analysis', side_effect=AssertionError('confirmed study invoked imaging')):
            _, code = asyncio.run(self.worker.analyze('fixture-T0', 5))
        self.assertEqual(code, 409)
        self.assertEqual(self.worker.registry.one("SELECT * FROM studies WHERE study_uid='fixture-T0'"), before)
        nodule = self.worker.registry.one("SELECT * FROM nodules WHERE nodule_id='cached-N1'")
        self.assertEqual((nodule['long_mm'], nodule['short_mm'], nodule['mean_mm']), (8, 6, 7))
        self.assertEqual(nodule['confirmed_by'], 'Synthetic reviewer')

    def test_pre_admission_cache_is_not_reused(self):
        self.save_cache()
        path = self.cache/'findings.json'
        metadata = json.loads(path.read_text())
        metadata['pipeline_version'] = '0.2.0'
        path.write_text(json.dumps(metadata))
        with patch('sparkmd.imaging.run_analysis', side_effect=AssertionError('old cache invoked imaging')):
            job, _ = asyncio.run(self.worker.analyze('fixture-T0', 5))
        self.assertEqual(job['state'], 'failed')
        self.assertEqual(self.worker.registry.all('SELECT * FROM nodules'), [])

    def test_linked_cache_requires_its_audited_prior(self):
        self.save_cache()
        path = self.cache/'nodules.json'
        nodules = json.loads(path.read_text())
        nodules[0]['matching'].update(status='matched', prior_nodule_id='missing-prior', prior_study_uid='missing-study')
        path.write_text(json.dumps(nodules))
        with patch('sparkmd.imaging.run_analysis', side_effect=AssertionError('missing prior invoked imaging')):
            job, _ = asyncio.run(self.worker.analyze('fixture-T0', 5))
        self.assertEqual(job['state'], 'failed')
        self.assertEqual(self.worker.registry.all('SELECT * FROM nodules'), [])

    def test_missing_cache_fails_without_detector_fallback(self):
        with patch('sparkmd.imaging.run_analysis', side_effect=AssertionError('cached replay invoked imaging')):
            job, _ = asyncio.run(self.worker.analyze('fixture-T0', 5))
        self.assertEqual(job['state'], 'failed')
        self.assertIn('cached analysis unavailable', job['error'])
        self.assertEqual(self.worker.registry.all('SELECT * FROM nodules'), [])


if __name__ == '__main__':
    unittest.main()
