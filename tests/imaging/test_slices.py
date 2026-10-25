import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from sparkmd.imaging.slices import render_slices
from sparkmd.imaging.volume import Volume


def synthetic_volume(signs=(1, 1, 1)):
    """Equivalent translated, anisotropic grids for signed axial IOPs."""
    hu = np.full((32, 24, 5), -1000, dtype=np.float32)
    for k in range(5):
        hu[2:8, 3:9, k] = -1300 + k * 100  # left/posterior landmark
        hu[22:29, 16:22, k] = -600 + k * 100  # right/anterior landmark
    hu[12:16, 10:14, :] = -2000  # window lower clamp
    hu[17:21, 3:7, :] = 1000  # window upper clamp
    affine = np.diag([.7, 1.3, 2.5, 1.])
    affine[:3, 3] = [-30, 18, -11]
    original = hu
    for axis, sign in enumerate(signs):
        if sign < 0:
            hu = np.flip(hu, axis=axis)
            affine[:3, 3] += affine[:3, axis] * (hu.shape[axis] - 1)
            affine[:3, axis] *= -1
    return Volume(hu, affine, 'synthetic'), original


def nodule(xyz=(10.25, 8.75, 2.2), nodule_id='N1', depth=15):
    # Physical coordinates of the common canonical grid, independent of IOP.
    center = (np.array([-30, 18, -11]) + np.array([.7, 1.3, 2.5]) * xyz).tolist()
    return {'nodule_id': nodule_id, 'center_mm': center, 'size_mm': [7, 7.8, depth],
            'det_score': .99, 'proposed_long_mm': 999, 'long_mm': None}


def pixels(path):
    with Image.open(path) as image:
        return np.asarray(image).copy()


class TestSlices(unittest.TestCase):
    def test_signed_iop_native_grid_orientation_window_and_boxes(self):
        # Both signs of each IOP direction, including inferior-first storage.
        for signs in ((1, 1, 1), (-1, -1, 1), (-1, 1, -1), (1, -1, -1)):
            with self.subTest(signs=signs), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                volume, hu = synthetic_volume(signs)
                finding = nodule()
                assets = render_slices(volume, [finding], root, 'study-1')
                key = assets['key_slices'][0]
                self.assertEqual(key['name'], 'key_axial_N1.png')
                self.assertEqual(key['url'], '/api/studies/study-1/assets/key_axial_N1.png')
                self.assertEqual(key['plane'], 'axial')
                self.assertEqual(key['nodule_id'], 'N1')
                np.testing.assert_allclose(key['box_px'], [15.75, 11.25, 10, 6])
                actual = pixels(root / key['name'])
                expected = (np.clip((hu[::-1, ::-1, 2].T + 1350) / 1500, 0, 1) * 255).astype(np.uint8)
                # Exact pixel equality also rules out burned-in boxes or resizing.
                np.testing.assert_array_equal(actual, expected)
                self.assertEqual(actual.shape, (24, 32))
                self.assertEqual(actual[4, 6], 161)  # anterior at top, right at left
                self.assertEqual(actual[18, 27], 42)  # posterior/left opposite corner
                self.assertEqual(actual[12, 18], 0)
                self.assertEqual(actual[18, 13], 255)
                stack = assets['slice_stack']
                self.assertEqual(stack['count'], 5)
                self.assertEqual(stack['size'], [32, 24])
                self.assertEqual(stack['spacing_mm'], 2.5)
                self.assertEqual(stack['z_mm'], [-1, -3.5, -6, -8.5, -11])
                self.assertEqual(stack['index_digits'], 3)
                self.assertEqual(stack['url_pattern'], '/api/studies/study-1/assets/stack_{i}.jpg')
                self.assertEqual(stack['nodule_slices'][0]['index'], 2)
                self.assertEqual(stack['nodule_slices'][0]['half_range'], 3)
                np.testing.assert_allclose(stack['nodule_slices'][0]['box_px'], key['box_px'])
                self.assertEqual(json.loads((root / 'stack.json').read_text()), stack)
                for index, k in enumerate(range(4, -1, -1)):
                    jpeg = pixels(root / f'stack_{index:03d}.jpg')
                    expected_slice = (np.clip((hu[::-1, ::-1, k].T + 1350) / 1500, 0, 1) * 255).astype(np.uint8)
                    self.assertEqual(jpeg.shape, actual.shape)
                    self.assertLess(np.abs(jpeg.astype(float) - expected_slice).mean(), 3)
                jpeg = pixels(root / 'stack_002.jpg')
                self.assertLess(np.abs(jpeg.astype(float) - actual).mean(), 3)

    def test_clamped_slice_indices_preserve_off_grid_box_centers(self):
        volume, hu = synthetic_volume()
        findings = [nodule((-2, 30, 99), 'above', depth=.1),
                    nodule((40, -4, -99), 'below', depth=10)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = render_slices(volume, findings, root, 'study')
            entries = assets['slice_stack']['nodule_slices']
            self.assertEqual([entry['index'] for entry in entries], [0, 4])
            self.assertEqual([entry['half_range'] for entry in entries], [1, 2])
            np.testing.assert_allclose(entries[0]['box_px'], [28, -10, 10, 6])
            np.testing.assert_allclose(entries[1]['box_px'], [-14, 24, 10, 6])
            for finding, k in zip(findings, (4, 0)):
                expected = (np.clip((hu[::-1, ::-1, k].T + 1350) / 1500, 0, 1) * 255).astype(np.uint8)
                np.testing.assert_array_equal(pixels(root / f"key_axial_{finding['nodule_id']}.png"), expected)
            self.assertEqual(findings[0]['center_mm'], nodule((-2, 30, 99))['center_mm'])

    def test_empty_nodules_still_render_full_stack(self):
        volume, _ = synthetic_volume()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = render_slices(volume, [], root, 'empty')
            self.assertEqual(assets['key_slices'], [])
            self.assertEqual(assets['slice_stack']['nodule_slices'], [])
            self.assertEqual(len(list(root.glob('stack_*.jpg'))), 5)
            self.assertTrue((root / 'stack.json').is_file())

    def test_key_only_mode_has_no_stack_files(self):
        volume, _ = synthetic_volume()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'new-output'
            assets = render_slices(volume, [nodule()], root, 'study', stack=False)
            self.assertIsNone(assets['slice_stack'])
            self.assertEqual([path.name for path in root.iterdir()], ['key_axial_N1.png'])

    def test_stack_index_width_grows_with_count(self):
        volume = Volume(np.full((1, 1, 1001), -600, dtype=np.float32), np.eye(4), 'long')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = render_slices(volume, [], root, 'long')
            self.assertEqual(assets['slice_stack']['index_digits'], 4)
            self.assertTrue((root / 'stack_0000.jpg').is_file())
            self.assertTrue((root / 'stack_1000.jpg').is_file())
            self.assertEqual(assets['slice_stack']['z_mm'][0], 1000)


if __name__ == '__main__':
    unittest.main()
