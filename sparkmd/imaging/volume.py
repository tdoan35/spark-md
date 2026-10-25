"""Original-grid HU volume, xyz array and RAS affine (build/04)."""
from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np
import pydicom

from .series import is_axial

LPS_TO_RAS = np.diag([-1., -1., 1., 1.])


@dataclass
class Volume:
    hu: np.ndarray
    affine: np.ndarray
    series_uid: str

    @property
    def spacing(self):
        return np.linalg.norm(self.affine[:3, :3], axis=0)

    def voxel_to_ras(self, xyz):
        return (self.affine @ np.r_[xyz, 1.])[:3]

    def ras_to_voxel(self, ras):
        return np.linalg.solve(self.affine, np.r_[ras, 1.])[:3]

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        image = nib.Nifti1Image(self.hu, self.affine)
        image.header.set_xyzt_units('mm')
        image.set_sform(self.affine, code=1)
        image.set_qform(self.affine, code=1)
        nib.save(image, path)


def dicom_to_volume(series_path, output_path=None):
    """Sort by physical slice position; refuse mixed/nonuniform geometries.

    Per-instance rescale is applied before transposing pixels (row,col) to
    (col,row,z). No resampling, integer-HU rounding or InstanceNumber ordering.
    """
    paths = sorted(Path(series_path).glob('*.dcm'))
    headers = [(path, pydicom.dcmread(path, stop_before_pixels=True)) for path in paths]
    if len(headers) < 2:
        raise ValueError('At least two single-frame CT slices are required')
    first = headers[0][1]
    iop = np.asarray(first.ImageOrientationPatient, dtype=float)
    if not is_axial(iop):
        raise ValueError('Only axis-aligned axial CT is supported')
    normal = np.cross(iop[:3], iop[3:])
    pixel_spacing = np.asarray(first.PixelSpacing, dtype=float)
    if pixel_spacing.shape != (2,) or np.any(pixel_spacing <= 0) or not np.isfinite(pixel_spacing).all():
        raise ValueError('Invalid PixelSpacing')
    series_uid = str(first.SeriesInstanceUID)
    sops = set()
    for _, ds in headers:
        if (str(ds.SeriesInstanceUID) != series_uid or str(ds.StudyInstanceUID) != str(first.StudyInstanceUID)
                or ds.Modality != 'CT' or int(getattr(ds, 'NumberOfFrames', 1)) != 1):
            raise ValueError('Mixed series/studies or non-single-frame CT')
        if str(ds.SOPInstanceUID) in sops:
            raise ValueError('Duplicate SOP instance')
        sops.add(str(ds.SOPInstanceUID))
        if (ds.Rows != first.Rows or ds.Columns != first.Columns
                or not np.allclose(ds.ImageOrientationPatient, iop, atol=1e-5)
                or not np.allclose(ds.PixelSpacing, pixel_spacing, atol=1e-5)):
            raise ValueError('Inconsistent slice orientation, shape or pixel spacing')
    headers.sort(key=lambda item: float(np.dot(item[1].ImagePositionPatient, normal)))
    positions = np.asarray([ds.ImagePositionPatient for _, ds in headers], dtype=float)
    projections = positions @ normal
    step = float(np.median(np.diff(projections)))
    if not np.isfinite(positions).all() or not np.isfinite(step) or step <= 0:
        raise ValueError('Invalid/duplicate slice positions')
    expected = positions[0] + np.arange(len(headers))[:, None] * step * normal
    if not np.allclose(positions, expected, atol=max(.01, step * .05), rtol=0):
        raise ValueError('Nonuniform slice grid or gantry tilt; cannot preserve geometry')
    hu = np.empty((int(first.Columns), int(first.Rows), len(headers)), dtype=np.float32)
    for index, (path, _) in enumerate(headers):
        ds = pydicom.dcmread(path)
        slope, intercept = float(getattr(ds, 'RescaleSlope', 1)), float(getattr(ds, 'RescaleIntercept', 0))
        if not np.isfinite([slope, intercept]).all() or slope == 0:
            raise ValueError('Invalid HU rescale')
        hu[:, :, index] = ds.pixel_array.T.astype(np.float32) * slope + intercept
    affine = np.eye(4)
    affine[:3, 0] = iop[:3] * pixel_spacing[1]
    affine[:3, 1] = iop[3:] * pixel_spacing[0]
    affine[:3, 2] = normal * step
    affine[:3, 3] = positions[0]
    volume = Volume(hu, LPS_TO_RAS @ affine, series_uid)
    if output_path is not None:
        volume.save(output_path)
    return volume
