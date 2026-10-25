import tempfile
import unittest
from pathlib import Path

import nibabel as nib
import numpy as np
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, CTImageStorage, generate_uid

from sparkmd.imaging.series import is_axial, select_series, values
from sparkmd.imaging.volume import dicom_to_volume


def slices(root, positions=(0, 2, 4), iop=(1, 0, 0, 0, 1, 0)):
    study, series = generate_uid(), generate_uid()
    for index, z in enumerate(positions):
        meta = FileMetaDataset()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        meta.MediaStorageSOPClassUID = CTImageStorage
        meta.MediaStorageSOPInstanceUID = generate_uid()
        ds = FileDataset(str(root / f'{9-index}.dcm'), {}, file_meta=meta, preamble=b'\0' * 128)
        ds.SOPClassUID, ds.SOPInstanceUID = CTImageStorage, meta.MediaStorageSOPInstanceUID
        ds.StudyInstanceUID, ds.SeriesInstanceUID = study, series
        ds.Modality, ds.Rows, ds.Columns = 'CT', 2, 3
        ds.ImageOrientationPatient = list(iop)
        ds.ImagePositionPatient, ds.PixelSpacing = [10, 20, z], [2, 3]
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, 'MONOCHROME2'
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
        ds.RescaleSlope, ds.RescaleIntercept = index + .5, -1000
        ds.PixelData = (np.arange(6, dtype=np.int16).reshape(2, 3) + index * 10).tobytes()
        ds.save_as(ds.filename, enforce_file_format=True)


class TestSelection(unittest.TestCase):
    def row(self, uid='a', **changes):
        return dict(dict(series_uid=uid, modality='CT', n_instances=120, slice_thickness=2,
                         image_type=['ORIGINAL', 'PRIMARY', 'AXIAL'], axial=True, kernel='B30f'), **changes)

    def test_soft_thinnest_not_sharp(self):
        rows = select_series([self.row('a'), self.row('b', slice_thickness=1.25),
                              self.row('sharp', slice_thickness=.5, kernel='BONE')])
        self.assertEqual([r['series_uid'] for r in rows if r['selected']], ['b'])
        self.assertFalse(rows[2]['eligible'])

    def test_single_sharp_fallback_not_ambiguous(self):
        rows = select_series([self.row(kernel='BONE')])
        self.assertTrue(rows[0]['selected'] and rows[0]['fallback'])
        self.assertFalse(any(r['selected'] for r in select_series([self.row('a', kernel='BONE'), self.row('b', kernel='B70f')])))

    def test_structural_exclusions(self):
        for changes in ({'n_instances': 99}, {'image_type': ['LOCALIZER']}, {'axial': False},
                        {'slice_thickness': 3}, {'slice_thickness': 0}, {'modality': 'MR'}):
            with self.subTest(changes=changes):
                self.assertFalse(select_series([self.row(**changes)])[0]['eligible'])

    def test_signed_iop_and_kernel_values(self):
        self.assertTrue(is_axial([-1, 0, 0, 0, -1, 0]))
        self.assertFalse(is_axial([1, 0, 0, 1, 0, 0]))
        self.assertFalse(is_axial([.8, .6, 0, -.6, .8, 0]))
        self.assertEqual(values('B30f'), ['B30f'])
        self.assertEqual(values(['B30f', '3']), ['B30f', '3'])


class TestDicomGeometry(unittest.TestCase):
    def test_pixels_spacing_ras_and_nifti_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slices(root)
            output = root / 'volume.nii.gz'
            vol = dicom_to_volume(root, output)
            self.assertEqual(vol.hu.shape, (3, 2, 3))
            np.testing.assert_allclose(vol.spacing, [3, 2, 2])
            np.testing.assert_allclose(vol.voxel_to_ras([2, 1, 1]), [-16, -22, 2])
            self.assertEqual(vol.hu[2, 1, 1], 15 * 1.5 - 1000)
            np.testing.assert_allclose(vol.ras_to_voxel([-16, -22, 2]), [2, 1, 1])
            image = nib.load(output)
            np.testing.assert_array_equal(np.asarray(image.dataobj), vol.hu)
            np.testing.assert_allclose(image.affine, vol.affine)

    def test_negative_iop_preserves_physical_locations(self):
        with tempfile.TemporaryDirectory() as tmp:
            slices(Path(tmp), iop=(-1, 0, 0, 0, -1, 0))
            vol = dicom_to_volume(tmp)
            np.testing.assert_allclose(vol.voxel_to_ras([2, 1, 1]), [-4, -18, 2])

    def test_rejects_irregular_grid_and_duplicates(self):
        for positions in ((0, 2, 4.8), (0, 2, 2)):
            with self.subTest(positions=positions), tempfile.TemporaryDirectory() as tmp:
                slices(Path(tmp), positions=positions)
                with self.assertRaises(ValueError):
                    dicom_to_volume(tmp)


if __name__ == '__main__':
    unittest.main()
