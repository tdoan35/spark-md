"""Validate the bundled, precomputed demo data without invoking Sybil scoring."""
import json
from pathlib import Path
import unittest


class RiskFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[2] / 'fixtures' / 'sybil_risk.json'
        cls.fixture = json.loads(path.read_text())

    def test_twelve_patients_have_three_contiguous_screens(self):
        patients = self.fixture['patients']
        self.assertIsInstance(patients, dict)
        self.assertEqual(len(patients), 12)
        for patient_id, patient in patients.items():
            with self.subTest(patient_id=patient_id):
                screens = patient['screens']
                self.assertIsInstance(screens, list)
                self.assertEqual(len(screens), 3)
                self.assertEqual([screen['timepoint'] for screen in screens], ['T0', 'T1', 'T2'])

    def test_every_screen_has_study_and_series_uids(self):
        for patient_id, patient in self.fixture['patients'].items():
            for screen in patient['screens']:
                with self.subTest(patient_id=patient_id, timepoint=screen['timepoint']):
                    for key in ('study_uid', 'series_uid'):
                        self.assertIsInstance(screen[key], str)
                        self.assertTrue(screen[key].strip(), key)

    def test_six_year_probabilities_are_bounded_and_nondecreasing(self):
        for patient_id, patient in self.fixture['patients'].items():
            for screen in patient['screens']:
                with self.subTest(patient_id=patient_id, timepoint=screen['timepoint']):
                    risks = screen['risk_1_to_6yr']
                    self.assertIsInstance(risks, list)
                    self.assertEqual(len(risks), 6)
                    for risk in risks:
                        self.assertIn(type(risk), (int, float))
                        self.assertTrue(0 <= risk <= 1, risk)
                    self.assertTrue(all(earlier <= later for earlier, later in zip(risks, risks[1:])))
