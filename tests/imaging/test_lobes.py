import unittest

import numpy as np

from sparkmd.imaging.lobes import label_from_geometry, split_lungs
from sparkmd.imaging.volume import Volume
from sparkmd.imaging.matching import match_nodules


def synthetic_chest(shift=(0, 0, 0)):
    shape = (160, 96, 128)
    x, y, z = np.ogrid[tuple(slice(0, n) for n in shape)]
    body = ((x - 80) / 75) ** 2 + ((y - 48) / 44) ** 2 <= 1
    hu = np.full(shape, -1000, dtype=np.float32)
    hu[np.broadcast_to(body, shape)] = 0
    for center_x in (48, 112):
        lung = ((x - center_x) / 28) ** 2 + ((y - 48) / 30) ** 2 + ((z - 64) / 45) ** 2 <= 1
        hu[lung] = -850
    affine = np.diag([1.5, 1.5, 1.5, 1])
    affine[:3, 3] = np.array([-120, -72, -96]) + shift
    return Volume(hu, affine, 'synthetic-chest')


class TestApproximateHeightRule(unittest.TestCase):
    def setUp(self):
        self.bounds = {'min_ras_mm': [-50, -60, -100], 'max_ras_mm': [50, 60, 100]}

    def test_right_thirds_and_left_halves_are_explicitly_approximate(self):
        for side, z, expected in [('R', -80, 'RLL'), ('R', 0, 'RML'), ('R', 80, 'RUL'),
                                  ('L', -80, 'LLL'), ('L', 80, 'LUL')]:
            with self.subTest(side=side, z=z):
                label = label_from_geometry([0, 0, z], side, self.bounds)
                self.assertEqual(label['lobe'], expected + ' (approximate)')
                self.assertTrue(label['approximate'])
                self.assertTrue(label['match_eligible'])

    def test_boundary_and_outside_assignments_prevent_confident_links(self):
        for z, inside, flag in [(0, True, 'approximate_lobe_boundary'),
                                (80, False, 'nearest_lung_outside_mask'), (110, True, 'outside_lung_bounds')]:
            with self.subTest(z=z):
                label = label_from_geometry([0, 0, z], 'L', self.bounds, inside_mask=inside)
                self.assertFalse(label['match_eligible'])
                self.assertIn(flag, label['match_flags'])
        unknown = label_from_geometry([0, 0, 0], None, None)
        self.assertIsNone(unknown['lobe'])
        self.assertIsNone(unknown['match_position_mm'])

    def test_scanner_translation_cancels_before_matching(self):
        shift = np.array([27, -12, 8])
        first = label_from_geometry([10, 0, 80], 'L', self.bounds)
        translated = {key: (np.array(value) + shift).tolist() for key, value in self.bounds.items()}
        second = label_from_geometry(np.array([11, 0, 80]) + shift, 'L', translated)
        decision, = match_nodules([dict(second, nodule_id='T1')], [dict(first, nodule_id='T0')])
        self.assertEqual(decision['prior_nodule_id'], 'T0')
        self.assertAlmostEqual(decision['distance_mm'], 1)


class TestThresholdLungSplit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.volume = synthetic_chest()
        cls.split = split_lungs(cls.volume)

    def test_bilateral_masks_and_anatomical_sides(self):
        for point, expected in [([48, 0, 45], 'RUL'), ([48, 0, 0], 'RML'),
                                ([48, 0, -45], 'RLL'), ([-48, 0, 45], 'LUL'), ([-48, 0, -45], 'LLL')]:
            with self.subTest(point=point):
                self.assertEqual(self.split.label(point)['lobe'], expected + ' (approximate)')
        for side in ('R', 'L'):
            self.assertGreater(self.split.geometry['sides'][side]['volume_ml'], 300)
        self.assertIsNone(self.split.label([500, 500, 500])['lobe'])

    def test_empty_chest_refuses_invented_lobes(self):
        volume = Volume(np.full((30, 30, 30), -1000, dtype=np.float32), np.eye(4), 'empty')
        with self.assertRaisesRegex(ValueError, 'no >300 mL'):
            split_lungs(volume)


if __name__ == '__main__':
    unittest.main()
