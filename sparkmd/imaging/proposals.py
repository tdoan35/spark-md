"""Day-of A7 diameter/mask proposals, NEVER accepted clinical measurements.

Build/04 fixes 1 mm smoothing/opening, adaptive half-core contrast threshold,
1.5x detector-radius cap and -600 HU core floor. It does not specify the seed
search extent or background estimator: this rebuild uses the central half-box
and median <-600 HU in the outer cap shell. These choices are UNVERIFIED and
must not inherit the prep implementation's benchmark accuracy claims.
"""
from dataclasses import dataclass

import numpy as np
from scipy import ndimage
from scipy.spatial import ConvexHull, distance


@dataclass
class Proposal:
    values: dict
    mask: np.ndarray | None = None
    start: np.ndarray | None = None


def axial_diameters(mask, spacing):
    """Longest Feret diameter + perpendicular width on maximal-area axial slice.

    Voxel corners, not centers, preserve physical pixel support on anisotropic
    grids. This is proposal geometry, not a validated boundary measurement.
    """
    area = mask.sum(axis=(0, 1))
    if area.max() == 0:
        raise ValueError('Empty mask')
    xy = np.argwhere(mask[:, :, int(np.argmax(area))])
    edge = np.concatenate([xy + offset for offset in ((-.5, -.5), (-.5, .5), (.5, -.5), (.5, .5))])
    points = np.unique(edge * np.asarray(spacing[:2]), axis=0)
    hull = points[ConvexHull(points).vertices]
    distances = distance.cdist(hull, hull)
    first, second = np.unravel_index(np.argmax(distances), distances.shape)
    long_mm = float(distances[first, second])
    direction = (hull[second] - hull[first]) / long_mm
    perpendicular = np.array([-direction[1], direction[0]])
    projected = hull @ perpendicular
    short_mm = min(long_mm, float(np.ptp(projected)))
    return round(long_mm, 1), round(short_mm, 1)


def propose_a7(volume, candidate):
    """Return proposed_* and local mask; failures retain the visible candidate."""
    result = {"proposed_long_mm": None, "proposed_short_mm": None, "proposed_mean_mm": None,
              "proposal_source": "A7", "proposal_version": "dayof-a7-v1-unverified",
              "proposal_reason": None, "mean_hu": None,
              "box_mean_mm": candidate['box_mean_mm']}

    def fail(reason):
        return Proposal(dict(result, proposal_reason=reason))

    spacing = volume.spacing
    center = volume.ras_to_voxel(candidate['center_mm'])
    size = np.asarray(candidate['size_mm'], dtype=float)
    if size.shape != (3,) or not np.isfinite(size).all() or np.any(size <= 0) or not np.isfinite(center).all():
        return fail('invalid_detector_geometry')
    if np.any(center < 0) or np.any(center > np.array(volume.hu.shape) - 1):
        return fail('detector_center_outside_volume')
    radius = float(np.max(size) / 2)
    cap_radius = 1.5 * radius
    padding = (cap_radius + 3) / spacing
    start = np.maximum(0, np.floor(center - padding).astype(int))
    stop = np.minimum(volume.hu.shape, np.ceil(center + padding).astype(int) + 1)
    crop = volume.hu[tuple(slice(a, b) for a, b in zip(start, stop))]
    grid = np.ogrid[tuple(slice(0, n) for n in crop.shape)]
    relative = [(grid[axis] + start[axis] - center[axis]) * spacing[axis] for axis in range(3)]
    radial2 = sum(axis ** 2 for axis in relative)
    # Search is within the detector box, not an unconstrained heart-boundary ROI.
    search = np.ones(crop.shape, dtype=bool)
    for axis in range(3):
        search &= np.abs(relative[axis]) <= max(size[axis] / 4, spacing[axis] / 2)
    smooth = ndimage.gaussian_filter(crop, sigma=1 / spacing)
    seed = np.unravel_index(np.argmax(np.where(search, smooth, -np.inf)), crop.shape)
    seed_offset = np.array([(seed[a] + start[a] - center[a]) * spacing[a] for a in range(3)])
    if np.any(np.abs(seed_offset) > size / 2):
        return fail('seed_outside_detector_box')
    core = float(smooth[seed])
    if core < -600:
        return fail('core_below_minus600_hu')
    shell = (radial2 >= radius ** 2) & (radial2 <= cap_radius ** 2) & (crop < -600)
    if not np.any(shell):
        return fail('no_local_parenchyma_reference')
    background = float(np.median(crop[shell]))
    threshold = background + .5 * (core - background)
    mask = (crop >= threshold) & (radial2 <= cap_radius ** 2)
    extent = np.ceil(1 / spacing).astype(int)
    axes = np.ogrid[tuple(slice(-n, n + 1) for n in extent)]
    opening = sum((axes[a] * spacing[a]) ** 2 for a in range(3)) <= 1.0
    mask = ndimage.binary_opening(mask, structure=opening)
    labels, _ = ndimage.label(mask)
    component = int(labels[seed])
    if not component:
        return fail('empty_seed_component_after_opening')
    mask = labels == component
    long_mm, short_mm = axial_diameters(mask, spacing)
    if short_mm <= 0 or long_mm > 100:
        return fail('proposal_diameter_out_of_range')
    result.update(proposed_long_mm=long_mm, proposed_short_mm=short_mm,
                  proposed_mean_mm=round((long_mm + short_mm) / 2, 1),
                  mean_hu=float(np.mean(crop[mask])), threshold_hu=threshold, core_hu=core,
                  seed_voxel=(np.asarray(seed) + start).tolist())
    return Proposal(result, mask, start)
