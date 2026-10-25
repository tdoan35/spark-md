import unittest

import numpy as np
from scipy import ndimage

from sparkmd.imaging.layers import build_layers
from sparkmd.imaging.lobes import LungSplit
from sparkmd.imaging.volume import Volume


def chest(shape=(48, 44, 32), affine=None, *, lungs=True):
    affine = np.diag([1.5, 1.5, 1.5, 1.]) if affine is None else affine
    hu = np.full(shape, -1000, dtype=np.float32)
    hu[2:-2, 2:-2, :] = 0
    labels = np.zeros(shape, dtype=np.uint8)
    if lungs:
        labels[5:-5, 5:-5, 3:-3] = 1
        hu[labels > 0] = -850
    return Volume(hu, affine, 'synthetic-render-layers'), LungSplit(labels, affine, {})


class TestAirwayLayers(unittest.TestCase):
    def test_trachea_seed_propagates_to_branches_but_not_disconnected_air(self):
        volume, split = chest(lungs=False)
        connected = np.zeros(volume.hu.shape, dtype=bool)
        connected[22:26, 20:24, 3:] = True
        connected[25:34, 21:24, 8:12] = True
        volume.hu[connected] = -1000
        volume.hu[10:14, 10:14, 4:8] = -1000
        masks, audit = build_layers(volume, split)
        expected = ndimage.binary_dilation(connected)
        np.testing.assert_array_equal(masks['airways'], expected)
        entry = audit['layers']['airways']
        self.assertEqual(entry['status'], 'present')
        self.assertEqual(entry['reason'], 'trachea_seed_propagation')
        self.assertEqual(entry['voxels'], int(expected.sum()))
        self.assertAlmostEqual(entry['volume_mm3'], expected.sum() * 1.5 ** 3)
        self.assertEqual(masks['airways'].dtype, np.bool_)

    def test_large_connected_lung_leak_is_rejected_without_fake_geometry(self):
        volume, split = chest((80, 80, 80), lungs=False)
        volume.hu[10:70, 10:70, :65] = -1000
        volume.hu[38:42, 38:42, 64:] = -1000
        masks, audit = build_layers(volume, split)
        self.assertIsNone(masks['airways'])
        entry = audit['layers']['airways']
        self.assertEqual(entry['status'], 'rejected')
        self.assertEqual(entry['reason'], 'rejected_leak_over_400ml')
        self.assertEqual(entry['voxels'], 0)
        self.assertEqual(entry['volume_mm3'], 0)

    def test_seed_area_uses_actual_in_plane_spacing_and_strict_air_hu(self):
        affine = np.diag([2., 3., 1., 1.])
        for hu, present in [(-951, True), (-950, False)]:
            with self.subTest(hu=hu):
                volume, split = chest(affine=affine, lungs=False)
                # Six voxels = 36 mm2; the old hard-coded 1.5 mm rule rejects it.
                volume.hu[23:25, 20:23, 4:] = hu
                masks, audit = build_layers(volume, split)
                self.assertEqual(masks['airways'] is not None, present)
                if not present:
                    self.assertEqual(audit['layers']['airways']['reason'], 'no_trachea_seed')

    def test_only_top_ten_slices_supply_a_seed(self):
        volume, split = chest(lungs=False)
        volume.hu[22:26, 20:24, :22] = -1000
        masks, audit = build_layers(volume, split)
        self.assertIsNone(masks['airways'])
        self.assertEqual(audit['layers']['airways']['status'], 'absent')
        self.assertEqual(audit['layers']['airways']['reason'], 'no_trachea_seed')


class TestVesselLayers(unittest.TestCase):
    def test_erosion_excludes_pleura_and_physical_filter_removes_small_blobs(self):
        volume, split = chest()
        volume.hu[12:17, 12:17, 10:15] = -500
        volume.hu[30:33, 27:30, 18:21] = -500
        volume.hu[5:7, 10:30, 10:20] = -500
        masks, audit = build_layers(volume, split)
        expected = np.zeros(volume.hu.shape, dtype=bool)
        expected[12:17, 12:17, 10:15] = True
        np.testing.assert_array_equal(masks['vessels'], expected)
        self.assertEqual(audit['layers']['vessels']['voxels'], 125)
        self.assertAlmostEqual(audit['layers']['vessels']['volume_mm3'], 125 * 3.375)

    def test_hu_and_component_volume_boundaries_are_strict_using_determinant(self):
        # Mirroring and shear make column-norm products differ from |det| = 2.
        affine = np.array([[-1., 1., 0., 0.], [0., 1., 0., 0.],
                           [0., 0., 2., 0.], [0., 0., 0., 1.]])
        volume, split = chest((56, 56, 44), affine)
        volume.hu[10:15, 10:15, 8:14] = -599  # Exactly 300 mm3: reject.
        volume.hu[30:35, 30:35, 20:26] = -599
        volume.hu[35, 30, 20] = -599  # 302 mm3: retain.
        volume.hu[10:16, 30:36, 20:26] = -600  # Large, but exactly HU cutoff.
        masks, audit = build_layers(volume, split)
        expected = np.zeros(volume.hu.shape, dtype=bool)
        expected[30:35, 30:35, 20:26] = True
        expected[35, 30, 20] = True
        np.testing.assert_array_equal(masks['vessels'], expected)
        self.assertAlmostEqual(audit['grid']['voxel_mm3'], 2)
        self.assertAlmostEqual(audit['layers']['vessels']['volume_mm3'], 302)

    def test_default_six_connectivity_does_not_merge_corner_touching_blobs(self):
        volume, split = chest()
        volume.hu[10:14, 10:14, 10:14] = -500
        volume.hu[14:18, 14:18, 14:18] = -500
        masks, audit = build_layers(volume, split)
        self.assertIsNone(masks['vessels'])
        self.assertEqual(audit['layers']['vessels']['status'], 'absent')
        self.assertEqual(audit['layers']['vessels']['reason'], 'no_large_components')


class TestSkeletonLayers(unittest.TestCase):
    def test_body_outline_and_erosion_exclude_table_outside_and_skin(self):
        shape = (64, 56, 40)
        hu = np.full(shape, -1000, dtype=np.float32)
        hu[8:56, 6:46, :] = 0
        hu[4:60, 49:54, :] = 700  # Separate CT table, not largest axial body.
        hu[1:5, 6:14, 4:36] = 700  # Disconnected exterior object.
        hu[8, 10:42, 4:36] = 700  # Bright skin, removed by body erosion.
        hu[25:35, 20:30, 10:20] = 700
        affine = np.diag([1.5, 1.5, 1.5, 1.])
        volume = Volume(hu, affine, 'synthetic-skeleton')
        split = LungSplit(np.zeros(shape, dtype=np.uint8), affine, {})
        masks, audit = build_layers(volume, split)
        expected = np.zeros(shape, dtype=bool)
        expected[25:35, 20:30, 10:20] = True
        np.testing.assert_array_equal(masks['skeleton'], expected)
        self.assertAlmostEqual(audit['layers']['skeleton']['volume_mm3'], 3375)

    def test_closing_bridges_one_voxel_marrow_gap_before_component_filter(self):
        volume, split = chest(lungs=False)
        volume.hu[14:20, 15:23, 10:18] = 500
        volume.hu[21:27, 15:23, 10:18] = 500
        masks, audit = build_layers(volume, split)
        skeleton = masks['skeleton']
        self.assertIsNotNone(skeleton)
        self.assertTrue(skeleton[20, 18, 14])
        self.assertTrue(skeleton[16, 18, 14])
        self.assertTrue(skeleton[24, 18, 14])
        self.assertEqual(ndimage.label(skeleton)[1], 1)
        self.assertGreater(audit['layers']['skeleton']['volume_mm3'], 2000)

    def test_hu_and_two_ml_component_boundaries_are_strict(self):
        affine = np.diag([1., 2., 1., 1.])
        affine[0, 1] = 1
        volume, split = chest((64, 60, 48), affine, lungs=False)
        volume.hu[8:18, 8:18, 6:16] = 251  # Exactly 2000 mm3: reject.
        volume.hu[30:40, 25:35, 20:30] = 251
        volume.hu[40, 25, 20] = 251  # Strictly greater: retain.
        volume.hu[45:56, 42:53, 32:43] = 250  # Above volume cutoff, not HU.
        masks, audit = build_layers(volume, split)
        expected = np.zeros(volume.hu.shape, dtype=bool)
        expected[30:40, 25:35, 20:30] = True
        expected[40, 25, 20] = True
        np.testing.assert_array_equal(masks['skeleton'], expected)
        self.assertAlmostEqual(audit['layers']['skeleton']['volume_mm3'], 2002)


class TestLayerGridAndAudit(unittest.TestCase):
    def test_native_hu_is_linearly_resampled_onto_translated_lung_grid(self):
        hu = np.full((80, 70, 60), -1000, dtype=np.float32)
        hu[1:-1, 1:-1, :] = 0
        x = np.arange(8, 65, dtype=np.float32)
        hu[8:65, 8:55, 10:50] = (-650 + 2 * x)[:, None, None]
        native_affine = np.eye(4)
        native_affine[:3, 3] = [100, -40, 25]
        target_affine = np.diag([2., 2., 2., 1.])
        target_affine[:3, 3] = native_affine[:3, 3] + [4.5, 6, 8]
        labels = np.zeros((36, 30, 24), dtype=np.uint8)
        labels[5:28, 5:23, 3:20] = 1
        volume = Volume(hu, native_affine, 'native-translated')
        split = LungSplit(labels, target_affine, {})
        masks, audit = build_layers(volume, split)
        expected = ndimage.binary_erosion(labels > 0, iterations=2)
        # At i=10, native x=24.5 gives -601 HU; i=11 gives -597 HU.
        expected[:11, :, :] = False
        np.testing.assert_array_equal(masks['vessels'], expected)
        self.assertEqual(masks['vessels'].shape, labels.shape)
        self.assertAlmostEqual(audit['grid']['voxel_mm3'], 8)

    def test_outside_native_volume_uses_minus_1000_not_zero_padding(self):
        native_affine = np.eye(4)
        native_affine[:3, 3] = [12, 12, 4]
        volume = Volume(np.zeros((24, 24, 24), dtype=np.float32),
                        native_affine, 'translated-small-native')
        labels = np.zeros((48, 48, 32), dtype=np.uint8)
        labels[4:44, 4:44, 2:30] = 1
        split = LungSplit(labels, np.eye(4), {})
        masks, audit = build_layers(volume, split)
        expected = np.zeros(labels.shape, dtype=bool)
        expected[12:36, 12:36, 4:28] = True
        np.testing.assert_array_equal(masks['vessels'], expected)

    def test_empty_layers_have_explicit_reasons(self):
        shape = (24, 24, 24)
        affine = np.eye(4)
        volume = Volume(np.full(shape, -1000, dtype=np.float32), affine, 'empty')
        split = LungSplit(np.zeros(shape, dtype=np.uint8), affine, {})
        masks, audit = build_layers(volume, split)
        self.assertEqual(set(masks), {'airways', 'vessels', 'skeleton'})
        self.assertEqual(audit['source'], 'threshold-render-only')
        self.assertIs(audit['clinical_measurement'], False)
        for name, mask in masks.items():
            with self.subTest(layer=name):
                self.assertIsNone(mask)
                entry = audit['layers'][name]
                self.assertEqual(entry['status'], 'absent')
                self.assertEqual(entry['voxels'], 0)
                self.assertEqual(entry['volume_mm3'], 0)
        self.assertEqual(audit['layers']['airways']['reason'], 'no_trachea_seed')
        for name in ('vessels', 'skeleton'):
            self.assertEqual(audit['layers'][name]['reason'], 'no_large_components')


if __name__ == '__main__':
    unittest.main()
