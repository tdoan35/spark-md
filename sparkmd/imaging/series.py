"""Header-only series selection from build/04, independent of device and DB."""
from pathlib import Path

import numpy as np
import pydicom

SOFT_KERNELS = frozenset(("B30F", "B31F", "B20F", "STANDARD", "FC01", "FC02", "FC51", "FC52"))


def values(value):
    return [value] if isinstance(value, str) else list(value or [])


def is_axial(iop):
    """Axis-aligned and sign-insensitive; reject oblique and degenerate axes."""
    if len(iop) != 6:
        return False
    directions = np.asarray(iop, dtype=float).reshape(2, 3)
    return bool(np.allclose(np.abs(directions), [[1, 0, 0], [0, 1, 0]], atol=.01))


def summarize_series(path):
    files = sorted(Path(path).glob('*.dcm'))
    if not files:
        raise ValueError(f"No DICOM instances: {path}")
    ds = pydicom.dcmread(files[0], stop_before_pixels=True)
    kernels = [str(k) for k in values(getattr(ds, 'ConvolutionKernel', []))]
    return {"study_uid": str(ds.StudyInstanceUID), "series_uid": str(ds.SeriesInstanceUID),
            "study_date": str(getattr(ds, 'StudyDate', '')), "path": str(path),
            "modality": str(getattr(ds, 'Modality', '')), "n_instances": len(files),
            "slice_thickness": float(getattr(ds, 'SliceThickness', 0) or 0),
            "kernel": kernels[0] if kernels else '', "kernel_list": kernels,
            "image_type": [str(v) for v in values(getattr(ds, 'ImageType', []))],
            "axial": is_axial(list(getattr(ds, 'ImageOrientationPatient', [])))}


def select_series(rows):
    """Return annotated copies; exactly one selected if eligible, else none.

    Use first kernel only (Siemens MultiValue may contain a numeric suffix).
    A sharp/unknown kernel is allowed only as the sole structural candidate.
    All soft candidates remain eligible for explicit clinician/agent selection.
    """
    result, structural = [], []
    for source in rows:
        row = dict(source, eligible=False, selected=False, fallback=False, select_reason=None)
        modality = row.get('modality')
        image_type = {str(v).upper() for v in values(row.get('image_type'))}
        thickness = row.get('slice_thickness')
        if modality != 'CT':
            reason = 'not CT'
        elif row.get('n_instances', 0) < 100 or 'LOCALIZER' in image_type:
            reason = 'localizer/fewer than 100 instances'
        elif not row.get('axial'):
            reason = 'not axial'
        elif thickness is None or not 0 < thickness <= 2.5:
            reason = 'slice thickness must be >0 and <=2.5 mm'
        else:
            structural.append(row)
            kernel = str(row.get('kernel') or '').upper()
            row['eligible'] = kernel in SOFT_KERNELS
            reason = 'soft kernel' if row['eligible'] else 'sharp/unknown kernel'
        row['eligible_reason'] = reason
        result.append(row)
    eligible = [row for row in result if row['eligible']]
    if not eligible and len(structural) == 1:
        row = structural[0]
        row.update(eligible=True, fallback=True, eligible_reason='sharp-kernel fallback')
        eligible = [row]
    if eligible:
        selected = min(eligible, key=lambda row: (row['slice_thickness'], -row['n_instances'], row['series_uid']))
        selected.update(selected=True, select_reason=selected['eligible_reason'])
    return result
