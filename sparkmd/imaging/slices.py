"""Native-grid lung-window images and display-only detector-box overlays.

Boxes are metadata, never burned into pixels. Canonicalization only permutes and
flips the original voxel grid: it does not resample or recenter the study.
"""
import json
from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image


def _axial_pixels(data, k):
    """W1500/L-600; anterior up, patient-right on screen-left."""
    axial = np.asarray(data[:, :, k], dtype=np.float32)
    grayscale = (np.clip((axial + 1350) / 1500, 0, 1) * 255).astype(np.uint8)
    return np.flipud(grayscale.T)[:, ::-1]


def render_slices(volume, nodules, output, study_uid, *, stack=True):
    """Render admitted nodules and optionally the complete superior-first stack.

    ``center_mm`` and ``size_mm`` are RAS detector coordinates/dimensions, not
    accepted or proposed measurements. Off-grid centers retain their exact box
    coordinates; only the chosen image index is clamped to the available grid.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    image = nib.as_closest_canonical(nib.Nifti1Image(volume.hu, volume.affine))
    data = image.dataobj
    width, height, count = image.shape
    spacing = np.linalg.norm(image.affine[:3, :3], axis=0)
    base_url = f'/api/studies/{study_uid}/assets/'
    key_slices, nodule_slices = [], []
    for nodule in nodules:
        xyz = np.linalg.solve(image.affine, np.r_[nodule['center_mm'], 1.])[:3]
        k = int(np.clip(round(float(xyz[2])), 0, count - 1))
        box_width, box_height = np.asarray(nodule['size_mm'][:2]) / spacing[:2]
        x, y = width - 1 - xyz[0], height - 1 - xyz[1]
        box_px = [float(x - box_width / 2), float(y - box_height / 2),
                  float(box_width), float(box_height)]
        nodule_id = nodule['nodule_id']
        name = f'key_axial_{nodule_id}.png'
        Image.fromarray(_axial_pixels(data, k)).save(output / name)
        key_slices.append({'name': name, 'url': base_url + name, 'plane': 'axial',
                           'nodule_id': nodule_id, 'box_px': box_px})
        # Detector depth is a display-only localization extent. Never substitute
        # an unconfirmed proposed diameter or an accepted clinical measurement.
        half_range = max(1, round(float(nodule['size_mm'][2]) / 2 / spacing[2]))
        nodule_slices.append({'nodule_id': nodule_id, 'index': count - 1 - k,
                              'box_px': box_px, 'half_range': half_range})

    slice_stack = None
    if stack:
        index_digits = max(3, len(str(count - 1)))
        # Hold only one grayscale slice at a time, not an expanded RGB volume.
        for index, k in enumerate(range(count - 1, -1, -1)):
            name = f'stack_{index:0{index_digits}d}.jpg'
            Image.fromarray(_axial_pixels(data, k)).save(output / name, quality=90)
        slice_stack = {
            'count': count, 'spacing_mm': float(spacing[2]),
            'z_mm': [float(image.affine[2, 3] + k * image.affine[2, 2])
                     for k in range(count - 1, -1, -1)],
            'size': [width, height], 'url_pattern': base_url + 'stack_{i}.jpg',
            'index_digits': index_digits, 'nodule_slices': nodule_slices,
        }
        (output / 'stack.json').write_text(json.dumps(slice_stack, indent=2, allow_nan=False))
    return {'key_slices': key_slices, 'slice_stack': slice_stack}
