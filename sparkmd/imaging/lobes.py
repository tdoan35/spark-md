"""Threshold right/left lungs from build/04; height-based lobes are APPROXIMATE.

04 specifies body HU>-400, filled axial body outline, lung HU<-400 inside body,
3-D components >300 mL, erosion to two seeds (second >=15% of first), watershed
on -EDT, and per-lung largest component / axial hole filling. It specifies no
fissure detector. Day-of lobe rule: right lung superior/inferior thirds =
RUL/RML/RLL; left superior/inferior halves = LUL/LLL (lingula stays in LUL).
Boundaries are lung-relative S coordinates, NOT anatomical fissures. All labels
carry '(approximate)'; within 5 mm of a height boundary, outside-mask nearest
assignment, or missing lung geometry prevents confident track linking.

Lung-relative matching position is RAS center minus its side's bounding-box
center, removing scan-origin translation without claiming image registration.
"""
from dataclasses import dataclass

import nibabel as nib
from nibabel.processing import resample_to_output
import numpy as np
from scipy import ndimage
from skimage.segmentation import watershed

LOBE_RULE = 'threshold-height-lobes-v1-approximate'


def _largest(mask):
    labels, count = ndimage.label(mask)
    if count == 0:
        return np.zeros(mask.shape, dtype=bool)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    return labels == int(np.argmax(sizes))


def _body_mask(hu):
    body = np.empty(hu.shape, dtype=bool)
    for k in range(hu.shape[2]):
        body[:, :, k] = ndimage.binary_fill_holes(_largest(hu[:, :, k] > -400))
    return body


def _bounds(mask, affine):
    # Axis projections avoid materializing coordinates for every lung voxel.
    ends = []
    for axis in range(3):
        indices = np.flatnonzero(np.any(mask, axis=tuple(i for i in range(3) if i != axis)))
        ends.append((int(indices[0]), int(indices[-1])))
    low = (affine @ np.r_[[v[0] for v in ends], 1])[:3]
    high = (affine @ np.r_[[v[1] for v in ends], 1])[:3]
    return {'min_ras_mm': low.tolist(), 'max_ras_mm': high.tolist()}


def label_from_geometry(center_ras_mm, side, bounds, *, inside_mask=True):
    """Pure height rule; reusable for cached prior geometry and synthetic tests."""
    if side not in ('R', 'L') or bounds is None:
        return {'lobe': None, 'lobe_rule': LOBE_RULE, 'approximate': True,
                'match_position_mm': None, 'match_eligible': False, 'match_flags': ['missing_lung_geometry']}
    point = np.asarray(center_ras_mm, dtype=float)
    low, high = np.array(bounds['min_ras_mm']), np.array(bounds['max_ras_mm'])
    extent = high - low
    if point.shape != (3,) or not np.isfinite(point).all() or np.any(extent <= 0):
        raise ValueError('Invalid point or lung bounding box')
    fraction = float((point[2] - low[2]) / extent[2])
    levels = (1 / 3, 2 / 3) if side == 'R' else (.5,)
    codes = ('RLL', 'RML', 'RUL') if side == 'R' else ('LLL', 'LUL')
    index = sum(fraction >= level for level in levels)
    flags = []
    if any(abs(point[2] - (low[2] + level * extent[2])) <= 5 for level in levels):
        flags.append('approximate_lobe_boundary')
    if not inside_mask:
        flags.append('nearest_lung_outside_mask')
    if np.any(point < low) or np.any(point > high):
        flags.append('outside_lung_bounds')
    return {'lobe': codes[index] + ' (approximate)', 'lobe_rule': LOBE_RULE, 'approximate': True,
            'side': side, 'height_fraction': fraction,
            'match_position_mm': (point - (low + high) / 2).tolist(),
            'match_eligible': not flags, 'match_flags': flags}


@dataclass
class LungSplit:
    labels: np.ndarray  # 0 background, 1 right, 2 left, on canonical 1.5 mm RAS grid
    affine: np.ndarray
    geometry: dict

    def label(self, center_ras_mm):
        xyz = np.linalg.solve(self.affine, np.r_[center_ras_mm, 1])[:3]
        voxel = np.round(xyz).astype(int)
        inside = np.all(voxel >= 0) and np.all(voxel < self.labels.shape)
        side_id = int(self.labels[tuple(voxel)]) if inside else 0
        inside_mask = side_id != 0
        if not side_id:
            # Only a bounded 5 mm neighborhood, never a distant opposite lung.
            spacing = np.linalg.norm(self.affine[:3, :3], axis=0)
            radius = np.ceil(5 / spacing).astype(int)
            start = np.maximum(0, voxel - radius)
            stop = np.minimum(self.labels.shape, voxel + radius + 1)
            if np.all(stop > start):
                local = self.labels[tuple(slice(a, b) for a, b in zip(start, stop))]
                coords = np.argwhere(local > 0)
                if len(coords):
                    distances = np.linalg.norm((coords + start - xyz) * spacing, axis=1)
                    best = int(np.argmin(distances))
                    if distances[best] <= 5:
                        side_id = int(local[tuple(coords[best])])
        side = {1: 'R', 2: 'L'}.get(side_id)
        return label_from_geometry(center_ras_mm, side, self.geometry['sides'].get(side), inside_mask=inside_mask)


def _airway(hu, body, voxel_mm3, spacing):
    air = (hu < -950) & body
    for k in range(hu.shape[2] - 1, max(-1, hu.shape[2] - 11), -1):
        outline = np.flatnonzero(body[:, :, k].any(axis=1))
        if not len(outline):
            continue
        midline = (outline[0] + outline[-1]) / 2
        labels, count = ndimage.label(air[:, :, k])
        candidates = []
        for label in range(1, count + 1):
            coords = np.argwhere(labels == label)
            if 30 <= len(coords) * spacing[0] * spacing[1] <= 800:
                offset = abs(float(coords[:, 0].mean()) - midline) * spacing[0]
                if offset <= 15:  # explicit day-of definition of \"midline\"
                    candidates.append((offset, label))
        if candidates:
            seed = np.zeros(hu.shape, dtype=bool)
            seed[:, :, k] = labels == min(candidates)[1]
            airway = ndimage.binary_dilation(ndimage.binary_propagation(seed, mask=air))
            if airway.sum() * voxel_mm3 < 400000:
                return airway, 'removed'
            return None, 'rejected_leak_over_400ml'
    return None, 'no_trachea_seed'


def split_lungs(volume):
    image = nib.as_closest_canonical(nib.Nifti1Image(volume.hu, volume.affine))
    image = resample_to_output(image, voxel_sizes=(1.5, 1.5, 1.5), order=1, cval=-1000)
    hu = np.asarray(image.dataobj, dtype=np.float32)
    body = _body_mask(hu)
    mask = (hu < -400) & body
    components, count = ndimage.label(mask)
    sizes = np.bincount(components.ravel())
    voxel_mm3 = abs(np.linalg.det(image.affine[:3, :3]))
    keep = np.flatnonzero(sizes * voxel_mm3 > 300000)
    keep = keep[keep != 0]
    mask = np.isin(components, keep)
    if not np.any(mask):
        raise ValueError('Threshold lung split failed: no >300 mL intrathoracic component')
    airway, airway_status = _airway(hu, body, voxel_mm3, np.linalg.norm(image.affine[:3, :3], axis=0))
    if airway is not None:
        mask &= ~airway
    del hu, body, components
    eroded = mask.copy()
    seeds = None
    # 15 mm cap is a fail-closed limit, not an alternate lobe segmentation.
    for _ in range(11):
        components, count = ndimage.label(eroded)
        sizes = np.bincount(components.ravel())
        sizes[0] = 0
        largest = np.argsort(sizes[1:])[::-1][:2] + 1
        if len(largest) == 2 and sizes[largest[1]] >= .15 * sizes[largest[0]]:
            centers = [ndimage.center_of_mass(eroded, components, int(label))[0] for label in largest]
            if abs(centers[0] - centers[1]) * 1.5 >= 20:
                seeds = np.zeros(mask.shape, dtype=np.uint8)
                for marker, component in enumerate(largest, 1):
                    seeds[components == component] = marker
                break
        eroded = ndimage.binary_erosion(eroded)
        if not np.any(eroded):
            break
    if seeds is None:
        raise ValueError('Threshold lung split failed: no separable bilateral seeds')
    separated = watershed(-ndimage.distance_transform_edt(mask), seeds, mask=mask)
    lungs = []
    for label in (1, 2):
        lung = _largest(separated == label)
        for k in range(lung.shape[2]):
            lung[:, :, k] = ndimage.binary_fill_holes(lung[:, :, k])
        lungs.append(lung)
    centers = [ndimage.center_of_mass(lung)[0] for lung in lungs]
    right_index = int(np.argmax(centers))  # canonical RAS x increases toward patient right
    labels = np.zeros(mask.shape, dtype=np.uint8)
    geometry = {'source': 'threshold', 'lobe_rule': LOBE_RULE, 'approximate': True,
                'airway_status': airway_status, 'sides': {}}
    for index, lung in enumerate(lungs):
        side, number = ('R', 1) if index == right_index else ('L', 2)
        labels[lung] = number
        geometry['sides'][side] = dict(_bounds(lung, image.affine), volume_ml=float(lung.sum() * voxel_mm3 / 1000))
    geometry['volume_ml'] = sum(side['volume_ml'] for side in geometry['sides'].values())
    return LungSplit(labels, image.affine, geometry)
