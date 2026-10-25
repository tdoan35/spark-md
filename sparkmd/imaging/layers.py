"""CPU-only threshold masks for render context, never clinical measurements."""

import nibabel as nib
from nibabel.processing import resample_from_to
import numpy as np
from scipy import ndimage

from .lobes import _airway, _body_mask


def _large_components(mask, voxel_mm3, minimum_mm3):
    """Keep strictly larger 6-connected components, never label zero."""
    components, _ = ndimage.label(mask)
    sizes = np.bincount(components.ravel())
    keep = sizes * voxel_mm3 > minimum_mm3
    keep[0] = False
    if not np.any(keep):
        return None
    return keep[components]


def _layer_audit(mask, status, reason, parameters):
    voxels = int(np.count_nonzero(mask)) if mask is not None else 0
    return {'status': status, 'reason': reason, 'voxels': voxels,
            'parameters': parameters}


def build_layers(volume, lung_split):
    """Return airway/vessel/skeleton masks exactly on the existing lung grid.

    Thresholds and morphology follow build/04 B9. A missing or leak-rejected
    layer is None, with an explicit audit reason instead of invented geometry.
    Volumes describe rendering masks only and must not become measurements.
    """
    affine = np.asarray(lung_split.affine, dtype=float)
    spacing = np.linalg.norm(affine[:3, :3], axis=0)
    voxel_mm3 = float(abs(np.linalg.det(affine[:3, :3])))
    source = nib.Nifti1Image(np.asarray(volume.hu, dtype=np.float32), volume.affine)
    image = resample_from_to(source, (lung_split.labels.shape, affine),
                             order=1, mode='constant', cval=-1000)
    hu = np.asarray(image.dataobj, dtype=np.float32)
    body = _body_mask(hu)
    airway, airway_status = _airway(hu, body, voxel_mm3, spacing)

    lung_interior = ndimage.binary_erosion(lung_split.labels > 0, iterations=2)
    vessels = _large_components((hu > -600) & lung_interior, voxel_mm3, 300)
    del lung_interior
    body_interior = ndimage.binary_erosion(body, iterations=1)
    bone = ndimage.binary_closing((hu > 250) & body_interior, iterations=1)
    del hu, image, body, body_interior
    skeleton = _large_components(bone, voxel_mm3, 2000)
    del bone

    masks = {'airways': airway, 'vessels': vessels, 'skeleton': skeleton}
    layers = {
        'airways': _layer_audit(
            airway, 'present' if airway is not None else
            ('rejected' if airway_status.startswith('rejected_') else 'absent'),
            'trachea_seed_propagation' if airway is not None else airway_status,
            {'hu_below': -950, 'superior_seed_slices': 10,
             'seed_area_mm2_inclusive': [30, 800], 'seed_midline_distance_mm_max': 15,
             'dilation_iterations': 1, 'maximum_volume_mm3_exclusive': 400000,
             'connectivity': 6, 'gaussian_sigma_voxels': 1,
             'marching_cubes_level': .5, 'marching_cubes_step_size': 1}),
        'vessels': _layer_audit(
            vessels, 'present' if vessels is not None else 'absent',
            'large_components_retained' if vessels is not None else 'no_large_components',
            {'hu_above': -600, 'lung_erosion_iterations': 2,
             'minimum_component_mm3_exclusive': 300, 'connectivity': 6,
             'gaussian_sigma_voxels': .6, 'marching_cubes_level': .5,
             'marching_cubes_step_size': 1}),
        'skeleton': _layer_audit(
            skeleton, 'present' if skeleton is not None else 'absent',
            'large_components_retained' if skeleton is not None else 'no_large_components',
            {'hu_above': 250, 'body_erosion_iterations': 1,
             'closing_iterations': 1, 'minimum_component_mm3_exclusive': 2000,
             'connectivity': 6, 'gaussian_sigma_voxels': 1,
             'marching_cubes_level': .5, 'marching_cubes_step_size': 2}),
    }
    layers['airways']['extraction_status'] = airway_status
    for entry in layers.values():
        entry['volume_mm3'] = entry['voxels'] * voxel_mm3
    audit = {
        'source': 'threshold-render-only', 'clinical_measurement': False,
        'grid': {'shape': list(lung_split.labels.shape), 'affine_ras_mm': affine.tolist(),
                 'spacing_mm': spacing.tolist(), 'voxel_mm3': voxel_mm3,
                 'resampling': {'order': 1, 'mode': 'constant', 'cval_hu': -1000}},
        'body_parameters': {'hu_above': -400, 'axial_largest_component': True,
                            'axial_fill_holes': True, 'connectivity': 4},
        'layers': layers,
    }
    return masks, audit
