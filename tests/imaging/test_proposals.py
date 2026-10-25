import platform
import unittest

import numpy as np

from sparkmd.imaging.detector import decode_candidates, detect
from sparkmd.imaging.proposals import axial_diameters, propose_a7
from sparkmd.imaging.volume import Volume


def synthetic_nodule(spacing=(.5, .5, 1), core=40):
    spacing = np.array(spacing)
    shape = (65, 65, 33)
    center = np.array(shape) // 2
    grid = np.ogrid[tuple(slice(0, n) for n in shape)]
    radius2 = sum(((grid[a] - center[a]) * spacing[a] / r) ** 2 for a, r in enumerate((5, 4, 4)))
    hu = np.full(shape, -850, dtype=np.float32)
    hu[radius2 <= 1] = core
    affine = np.diag([*spacing, 1.])
    vol = Volume(hu, affine, 'synthetic')
    candidate = {'center_mm': vol.voxel_to_ras(center).tolist(), 'size_mm': [10, 8, 8],
                 'box_mean_mm': 9, 'det_score': .99}
    return vol, candidate


class TestProposalSafety(unittest.TestCase):
    def test_solid_proposal_not_accepted_measurement(self):
        vol, candidate = synthetic_nodule()
        proposal = propose_a7(vol, candidate)
        self.assertIsNone(proposal.values['proposal_reason'])
        self.assertAlmostEqual(proposal.values['proposed_long_mm'], 10, delta=1.5)
        self.assertAlmostEqual(proposal.values['proposed_short_mm'], 8, delta=1.5)
        self.assertNotIn('mean_mm', proposal.values)
        seed = np.array(proposal.values['seed_voxel'])
        self.assertTrue(np.all(np.abs((seed - vol.ras_to_voxel(candidate['center_mm'])) * vol.spacing) <= np.array(candidate['size_mm']) / 2))

    def test_low_contrast_retains_candidate_without_proposed_diameter(self):
        vol, candidate = synthetic_nodule(core=-700)
        proposal = propose_a7(vol, candidate)
        self.assertEqual(proposal.values['proposal_reason'], 'core_below_minus600_hu')
        self.assertIsNone(proposal.mask)
        self.assertIsNone(proposal.values['proposed_mean_mm'])
        self.assertEqual(proposal.values['box_mean_mm'], 9)

    def test_outside_center_and_empty_mask_fail_closed(self):
        vol, candidate = synthetic_nodule()
        candidate['center_mm'] = [1000, 1000, 1000]
        self.assertEqual(propose_a7(vol, candidate).values['proposal_reason'], 'detector_center_outside_volume')
        with self.assertRaises(ValueError):
            axial_diameters(np.zeros((3, 3, 3), dtype=bool), [1, 1, 1])

    def test_unrelated_bright_tissue_not_selected(self):
        vol, candidate = synthetic_nodule()
        vol.hu[45:50, 29:36, 14:19] = 1000
        proposal = propose_a7(vol, candidate)
        seed = np.array(proposal.values['seed_voxel'])
        self.assertLess(seed[0], 40)
        self.assertLess(proposal.values['proposed_long_mm'], 12)


class TestDetectorGeometry(unittest.TestCase):
    def test_lps_centers_not_transposed_or_double_flipped(self):
        candidates = decode_candidates([[10, -20, 30, 8, 6, 4], [-5, 15, 40, 4, 2, 6]], [.7, .9])
        self.assertEqual(candidates[0]['center_mm'], [5, -15, 40])
        self.assertEqual(candidates[1]['center_mm'], [-10, 20, 30])
        self.assertEqual(candidates[1]['box_mean_mm'], 7)
        self.assertEqual(decode_candidates([], []), [])

    def test_invalid_outputs_fail_not_silent_candidate_drop(self):
        for box, score in [([1, 2, 3, 0, 6, 7], .9), ([1, 2, 3, 5, 6, 7], float('nan'))]:
            with self.subTest(box=box), self.assertRaises(ValueError):
                decode_candidates([box], [score])
        with self.assertRaises(ValueError):
            decode_candidates([[1, 2, 3, 4, 5, 6]], [])

    @unittest.skipUnless(platform.system() == 'Darwin', 'Mac-only guard')
    def test_mac_refuses_gpu_inference_before_torch_import(self):
        with self.assertRaisesRegex(RuntimeError, 'GB10'):
            detect('not-read-on-Mac.nii.gz')


if __name__ == '__main__':
    unittest.main()
