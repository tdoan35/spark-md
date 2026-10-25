import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from sparkmd.findings import findings, recompute
from sparkmd.imaging.lobes import LungSplit
from sparkmd.imaging.pipeline import run_analysis
from sparkmd.imaging.volume import Volume
from sparkmd.registry import Registry
from sparkmd.rules.measurements import confirmed_measurement


class TestNoduleAdmission(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.registry = Registry(self.home / 'registry.sqlite')
        self.addCleanup(self.registry.close)
        shape = (41, 41, 41)
        x, y, z = np.ogrid[:41, :41, :41]
        hu = np.full(shape, -850, dtype=np.float32)
        hu[(x - 20) ** 2 + (y - 20) ** 2 + (z - 12) ** 2 <= 25] = 40
        self.volume = Volume(hu, np.eye(4), 'series')
        self.split = LungSplit(np.full(shape, 2, dtype=np.uint8), np.eye(4), {
            'sides': {'L': {'min_ras_mm': [0, 0, 0], 'max_ras_mm': [40, 40, 40]}},
            'volume_ml': 1, 'lobe_rule': 'synthetic-geometry',
        })
        with self.registry.transaction() as db:
            db.execute("INSERT INTO patients(patient_id) VALUES ('patient')")
            db.execute("""INSERT INTO studies(study_uid,patient_id,rank,status,received_at)
                VALUES ('study','patient',0,'organized','now')""")
            db.execute("""INSERT INTO series(series_uid,study_uid,selected,eligible,path)
                VALUES ('series','study',1,1,'unused-dicom-path')""")
        self.worker = SimpleNamespace(registry=self.registry, config=SimpleNamespace(home=self.home, fake=False),
                                      status=lambda uid, state: None)

    def candidate(self, score, *, outside=False):
        return {'center_mm': [1000, 1000, 1000] if outside else [20, 20, 12],
                'size_mm': [10, 10, 10], 'box_mean_mm': 10, 'det_score': score}

    def analyze(self, candidates):
        # Synthetic detector/volume inputs; real A7, tracking, persistence and findings.
        with patch('sparkmd.imaging.pipeline.detect', return_value=candidates), \
             patch('sparkmd.imaging.pipeline.dicom_to_volume', return_value=self.volume), \
             patch('sparkmd.imaging.pipeline.split_lungs', return_value=self.split):
            return run_analysis('study', registry=self.registry, home=self.home)

    def test_score_boundary_not_proposal_success_controls_confirmation(self):
        result = self.analyze([self.candidate(.95), self.candidate(.90, outside=True),
                               self.candidate(.899999), self.candidate(.2, outside=True)])
        ui, status = findings(self.worker, 'study')
        self.assertEqual(status, 200)
        self.assertEqual({n['det_score'] for n in ui['nodules']}, {.95, .90})
        self.assertEqual(set(ui['pending_confirmation']), {n['nodule_id'] for n in result['nodules']})
        failed = next(n for n in ui['nodules'] if n['det_score'] == .90)
        self.assertIsNone(failed['proposal']['mean_mm'])
        self.assertEqual(failed['proposal']['reason'], 'detector_center_outside_volume')
        self.assertTrue(all(n['mean_mm'] is None for n in ui['nodules']))
        self.assertFalse(recompute(self.worker, 'study'))
        self.assertIsNone(ui['assessment'])
        candidates = json.loads((self.home / 'cache/series/candidates.json').read_text())
        by_score = {c['det_score']: c for c in candidates}
        self.assertIsNotNone(by_score[.899999]['proposed_mean_mm'])
        self.assertFalse(by_score[.899999]['admitted'])
        self.assertFalse(by_score[.2]['admitted'])
        self.assertEqual(by_score[.2]['proposal_reason'], 'detector_center_outside_volume')
        admission = self.registry.one("SELECT payload_json FROM agent_events WHERE message LIKE 'Candidate admission%'")
        excluded = json.loads(admission['payload_json'])['excluded']
        self.assertEqual({n['det_score'] for n in excluded}, {.899999, .2})

    def test_excluded_candidates_do_not_block_assessment_after_human_confirmation(self):
        result = self.analyze([self.candidate(.95), self.candidate(.4, outside=True)])
        self.assertFalse(recompute(self.worker, 'study'))
        accepted = confirmed_measurement(6, 5)
        with self.registry.transaction() as db:
            db.execute("""UPDATE nodules SET long_mm=?,short_mm=?,mean_mm=?,volume_mm3=?,
                confirmed_at='human' WHERE nodule_id=?""",
                       (accepted['long_mm'], accepted['short_mm'], accepted['mean_mm'],
                        accepted['volume_mm3'], result['nodules'][0]['nodule_id']))
        self.assertTrue(recompute(self.worker, 'study'))
        ui, _ = findings(self.worker, 'study')
        self.assertEqual(ui['pending_confirmation'], [])
        self.assertEqual(ui['assessment']['lung_rads'], '2')
        self.assertEqual(ui['assessment']['rule_id'], 'S-BASE-<6')


if __name__ == '__main__':
    unittest.main()
