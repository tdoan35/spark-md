"""Day-of vectors derived from build/05; historical hero values are synthetic inputs."""
import math
import unittest

from sparkmd.rules import assess, classify, growth_per_12mo
from sparkmd.rules.measurements import confirmed_measurement, longitudinal_change, sphere_volume, vdt_days


# (input, category, rule): thresholds are inclusive at the lower bound.
VECTORS = [
    ({"type": "solid", "mean_mm": 5.9}, "2", "S-BASE-<6"),
    ({"type": "solid", "mean_mm": 6.0}, "3", "S-BASE-6-8"),
    ({"type": "solid", "mean_mm": 7.9}, "3", "S-BASE-6-8"),
    ({"type": "solid", "mean_mm": 8.0}, "4A", "S-BASE-8-15"),
    ({"type": "solid", "mean_mm": 14.9}, "4A", "S-BASE-8-15"),
    ({"type": "solid", "mean_mm": 15.0}, "4B", "S-BASE-≥15"),
    ({"type": "solid", "mean_mm": 3.9, "new": True}, "2", "S-NEW-<4"),
    ({"type": "solid", "mean_mm": 4.0, "new": True}, "3", "S-NEW-4-6"),
    ({"type": "solid", "mean_mm": 5.9, "new": True}, "3", "S-NEW-4-6"),
    ({"type": "solid", "mean_mm": 6.0, "new": True}, "4A", "S-NEW-6-8"),
    ({"type": "solid", "mean_mm": 7.9, "new": True}, "4A", "S-NEW-6-8"),
    ({"type": "solid", "mean_mm": 8.0, "new": True}, "4B", "S-GROW-≥8"),
    ({"type": "solid", "mean_mm": 5.0, "growth_mm": 1.5}, "2", "S-BASE-<6"),
    ({"type": "solid", "mean_mm": 5.0, "growth_mm": 2.0}, "4A", "S-GROW-<8"),
    ({"type": "solid", "mean_mm": 7.9, "growth_mm": 2.0}, "4A", "S-GROW-<8"),
    ({"type": "solid", "mean_mm": 8.0, "growth_mm": 2.0}, "4B", "S-GROW-≥8"),
    ({"type": "solid", "mean_mm": 5.0, "slow_growing": True}, "4B", "S-N8"),
    ({"type": "solid", "mean_mm": 20, "benign_features": True}, "1", "S-BENIGN"),
    ({"type": "part_solid", "mean_mm": 5.9, "solid_mm": 2}, "2", "PS-BASE-<6"),
    ({"type": "part_solid", "mean_mm": 6.0, "solid_mm": 2}, "3", "PS-BASE-S<6"),
    ({"type": "part_solid", "mean_mm": 10, "solid_mm": 5.9}, "3", "PS-BASE-S<6"),
    ({"type": "part_solid", "mean_mm": 10, "solid_mm": 6.0}, "4A", "PS-BASE-S6-8"),
    ({"type": "part_solid", "mean_mm": 10, "solid_mm": 7.9}, "4A", "PS-BASE-S6-8"),
    ({"type": "part_solid", "mean_mm": 10, "solid_mm": 8.0}, "4B", "PS-BASE-S≥8"),
    ({"type": "part_solid", "mean_mm": 5.9, "solid_mm": 2, "new": True}, "3", "PS-NEW-<6"),
    ({"type": "part_solid", "mean_mm": 6, "solid_mm": 3.9, "new": True}, "4A", "PS-GROW-S<4"),
    ({"type": "part_solid", "mean_mm": 6, "solid_mm": 4.0, "new": True}, "4B", "PS-GROW-S≥4"),
    ({"type": "part_solid", "mean_mm": 10, "solid_mm": 3.9, "growth_mm": 2}, "4A", "PS-GROW-S<4"),
    ({"type": "part_solid", "mean_mm": 10, "solid_mm": 4.0, "growth_mm": 2}, "4B", "PS-GROW-S≥4"),
    ({"type": "ggo", "mean_mm": 29.9}, "2", "G-<30"),
    ({"type": "ggo", "mean_mm": 30.0}, "3", "G-≥30"),
    ({"type": "ggo", "mean_mm": 35, "new": True}, "3", "G-≥30"),
    ({"type": "ggo", "mean_mm": 35, "stable": True}, "2", "G-N7"),
    ({"type": "ggo", "mean_mm": 35, "slow_growing": True}, "2", "G-N7"),
    ({"type": "ggo", "mean_mm": 10, "suspicion_flags": ["ggn_doubling_1y"]}, "4X", "G-X"),
    ({"type": "solid", "mean_mm": 6, "suspicion_flags": ["spiculation"]}, "4X", "S-BASE-6-8+X"),
    ({"type": "solid", "mean_mm": 9, "suspicion_flags": ["lymphadenopathy"]}, "4X", "S-BASE-8-15+X"),
    ({"type": "solid", "mean_mm": 16, "suspicion_flags": ["metastasis"]}, "4X", "S-BASE-≥15+X"),
    ({"type": "solid", "mean_mm": 4.6}, "2", "S-BASE-<6"),
    ({"type": "solid", "mean_mm": 8.4, "growth_mm": 3.9}, "4B", "S-GROW-≥8"),
    ({"type": "solid", "mean_mm": 14.7, "growth_mm": 6.2}, "4B", "S-GROW-≥8"),
]


class TestRules(unittest.TestCase):
    def test_table(self):
        for nodule, category, rule in VECTORS:
            with self.subTest(nodule=nodule):
                result = classify(nodule)
                self.assertEqual((result["lung_rads"], result["rule_id"]), (category, rule))

    def test_exam_maximum_and_driver(self):
        result = assess([dict(VECTORS[0][0], nodule_id="low"),
                         dict(VECTORS[15][0], nodule_id="high")])
        self.assertEqual((result["lung_rads"], result["driver"]), ("4B", "high"))
        self.assertEqual(assess([])["lung_rads"], "1")
        self.assertEqual(assess([])["rule_id"], "NO-NODULES")

    def test_invalid_inputs_never_categorized(self):
        for nodule in ({"type": "solid", "mean_mm": None},
                       {"type": "solid", "mean_mm": math.nan},
                       {"type": "other", "mean_mm": 4},
                       {"type": "part_solid", "mean_mm": 6, "solid_mm": 8}):
            with self.subTest(nodule=nodule), self.assertRaises(ValueError):
                assess([nodule])

    def test_small_solid_not_upgraded_by_spiculation_alone(self):
        self.assertEqual(classify({"type": "solid", "mean_mm": 4,
                                   "suspicion_flags": ["spiculation"]})["lung_rads"], "2")


class TestGrowthInterval(unittest.TestCase):
    def test_interval_cases(self):
        for delta, days, expected in [(4, 371, 4 * 365.25 / 371),
                                      (2, 730, 2 * 365.25 / 730), (2, 30, 2),
                                      (1.5, 365.25, 1.5), (2, 365, 2),
                                      (-2, 730, -2 * 365.25 / 730), (0, 400, 0),
                                      (2, None, None), (None, 365, None)]:
            with self.subTest(delta=delta, days=days):
                actual = growth_per_12mo(delta, days)
                if expected is None:
                    self.assertIsNone(actual)
                else:
                    self.assertAlmostEqual(actual, expected)
        for days in (0, -1):
            self.assertIsNone(growth_per_12mo(2, days))

    def test_rate_not_raw_delta_drives_category(self):
        nodule = {"type": "solid", "mean_mm": 7, "growth_mm": growth_per_12mo(2, 730)}
        self.assertEqual(classify(nodule)["lung_rads"], "3")
        nodule["growth_mm"] = growth_per_12mo(4, 371)
        self.assertEqual(classify(nodule)["lung_rads"], "4A")


class TestConfirmedMeasurements(unittest.TestCase):
    def test_confirmation_and_sphere(self):
        result = confirmed_measurement(10, 8)
        self.assertEqual(result["mean_mm"], 9)
        self.assertAlmostEqual(result["volume_mm3"], 4 / 3 * math.pi * 4.5 ** 3)
        self.assertEqual(confirmed_measurement(6)["short_mm"], 6)
        for long_mm, short_mm in [(0, 0), (101, 8), (6, 7), (6, -1), (math.inf, 5)]:
            with self.subTest(long_mm=long_mm, short_mm=short_mm), self.assertRaises(ValueError):
                confirmed_measurement(long_mm, short_mm)

    def test_positive_subprecision_diameter_obeys_v08_rounding(self):
        measurement = confirmed_measurement(.01, .01)
        self.assertEqual(measurement["mean_mm"], 0.0)
        self.assertEqual(measurement["volume_mm3"], 0.0)
        self.assertEqual(classify(dict(measurement, type="solid"))["lung_rads"], "2")

    def test_doubling_and_non_growth(self):
        self.assertAlmostEqual(vdt_days(100, 200, 365), 365)
        for prior, current, days in [(0, 100, 365), (100, 100, 365), (100, 90, 365), (100, 200, None)]:
            self.assertIsNone(vdt_days(prior, current, days))

    def test_proposals_cannot_drive_longitudinal_change(self):
        prior = {"mean_mm": 6, "confirmed_at": "now"}
        current = {"mean_mm": 10, "confirmed_at": "now"}
        change = longitudinal_change(current, prior, 371)
        self.assertTrue(change["growth_normalized"])
        self.assertTrue(change["growing"])
        self.assertAlmostEqual(change["growth_per_12mo_mm"], 4 * 365.25 / 371)
        self.assertIsNone(longitudinal_change({"proposed_mean_mm": 10}, prior, 371))
        self.assertIsNone(longitudinal_change(current, {"mean_mm": 6}, 371))
        self.assertIsNone(longitudinal_change(current, prior, None))


if __name__ == "__main__":
    unittest.main()
