"""MONAI lung_nodule_ct_detection v0.5.9; GPU execution is box-only.

The public bundle config defines the network, anchors, thresholds, patch size,
normalization and postprocessing. Native MONAI inference avoids the old bundle's
Ignite evaluator/saver imports and its removed image_meta_dict convention.
"""
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import zipfile

import numpy as np


def check_gpu_host():
    if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64'):
        raise RuntimeError('Detector requires the Linux aarch64 GB10 box; do not run on the Mac')
    subprocess.run(['free', '-g'], check=True)
    available = next(int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines()
                     if line.startswith('MemAvailable:'))
    if available < 15 * 1024 ** 3:
        raise RuntimeError(f'MemAvailable {available / 1024 ** 3:.2f} GiB is below the 15 GiB floor')


def bundle_location(models=None):
    root = Path(models or os.environ.get('SPARKMD_MODELS', str(Path(os.environ.get('SPARKMD_HOME', '/srv/spark-md')) / 'models')))
    candidates = (root / 'lung_nodule_ct_detection', root)
    for path in candidates:
        if (path / 'configs' / 'inference.json').is_file() and (path / 'models' / 'model.pt').is_file():
            return path
        archives = sorted(path.glob('lung_nodule_ct_detection_v0.5.9.zip'))
        if archives:
            return archives[0]
    raise FileNotFoundError(f'Expected lung_nodule_ct_detection v0.5.9 bundle under SPARKMD_MODELS={root}')


def decode_candidates(boxes, scores):
    """Bundle cccwhd in LPS mm -> public RAS centers; do not swap i/j."""
    boxes = np.asarray(boxes, dtype=float).reshape(-1, 6)
    scores = np.asarray(scores, dtype=float).reshape(-1)
    if len(boxes) != len(scores):
        raise ValueError('Detector box/score count mismatch')
    candidates = []
    for box, score in zip(boxes, scores):
        if not np.isfinite(box).all() or not np.isfinite(score) or np.any(box[3:] <= 0) or not 0 <= score <= 1:
            raise ValueError('Invalid detector box or score')
        candidates.append({'center_mm': (box[:3] * [-1, -1, 1]).tolist(),
                           'size_mm': box[3:].tolist(), 'box_lps': box.tolist(),
                           'det_score': float(score), 'box_mean_mm': round(float(np.mean(box[3:5])), 1)})
    return sorted(candidates, key=lambda item: -item['det_score'])


def detect(volume_path, models=None):
    """One full series, releasing the GPU model before returning CPU candidates.

    No CPU fallback. Original HU/RAS NIfTI uses NibabelReader (in the lock), not
    the optional ITK reader. Raw-image spacing is the bundle's 0.703125/1.25 mm.
    This exact event-stack path requires GB10 smoke validation before demo use.
    """
    check_gpu_host()
    import torch
    from monai.bundle import ConfigParser
    from monai.transforms import (Compose, EnsureChannelFirstd, EnsureTyped, LoadImaged,
                                  Orientationd, ScaleIntensityRanged, Spacingd)

    if not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable; detector is GB10-only')
    source = bundle_location(models)
    with tempfile.TemporaryDirectory(prefix='sparkmd-detector-') as tmp:
        if source.is_file():
            root = Path(tmp) / 'lung_nodule_ct_detection'
            # Extract only public config and checkpoint, never executable bundle scripts.
            with zipfile.ZipFile(source) as archive:
                for member in ('configs/inference.json', 'models/model.pt'):
                    target = root / member
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open('lung_nodule_ct_detection/' + member) as inp, target.open('wb') as out:
                        import shutil
                        shutil.copyfileobj(inp, out)
        else:
            root = source
        config = json.loads((root / 'configs' / 'inference.json').read_text())
        parser = ConfigParser()
        parser.read_config(str(root / 'configs' / 'inference.json'))
        parser['device'] = "$torch.device('cuda:0')"
        network = parser.get_parsed_content('network')
        detector = parser.get_parsed_content('detector')
        parser.get_parsed_content('detector_ops')
        checkpoint = torch.load(root / 'models' / 'model.pt', map_location='cpu', weights_only=True)
        network.load_state_dict(checkpoint.get('model', checkpoint), strict=True)
        del checkpoint
        network.eval()
        # Use shipped raw-volume transform parameters, without the optional ITK dependency.
        transforms = config['preprocessing']['transforms']
        spacing = next(t['pixdim'] for t in transforms if t['_target_'] == 'Spacingd')
        scale = next(t for t in transforms if t['_target_'] == 'ScaleIntensityRanged')
        preprocessing = Compose([
            LoadImaged(keys='image', reader='NibabelReader'),
            EnsureChannelFirstd(keys='image'), Orientationd(keys='image', axcodes='RAS'),
            Spacingd(keys='image', pixdim=spacing),
            ScaleIntensityRanged(keys='image', **{k: scale[k] for k in ('a_min', 'a_max', 'b_min', 'b_max', 'clip')}),
            EnsureTyped(keys='image'),
        ])
        image = preprocessing({'image': str(volume_path)})['image']
        try:
            with torch.inference_mode(), torch.autocast(device_type='cuda', enabled=bool(config['amp'])):
                patch_voxels = int(np.prod(config['infer_patch_size']))
                prediction = detector([image.to('cuda')], use_inferer=image[0].numel() >= patch_voxels)[0]
            prediction = {key: value.detach().cpu() for key, value in prediction.items()}
            postprocess = parser.get_parsed_content('postprocessing')
            result = postprocess(dict(prediction, image=image))
            return decode_candidates(result['box'], result['label_scores'])
        finally:
            del image, detector, network, parser
            torch.cuda.empty_cache()
