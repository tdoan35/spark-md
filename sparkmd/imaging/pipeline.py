"""Worker entry point: original DICOM -> detector -> unconfirmed A7 proposals.

Uses W's registry; never assigns an assessment or confirms a diameter. General
longitudinal/lobe matching remains open in build/04: track_id and lobe remain
null rather than inventing identity. Registry's solid default is retained and
recorded as an unverified type assumption in cache audit data.
"""
import json
import os
from pathlib import Path
import threading
import uuid

import nibabel as nib
import numpy as np
from PIL import Image

from sparkmd.registry import Registry
from .detector import detect
from .proposals import propose_a7
from .volume import dicom_to_volume

# One heavyweight imaging job at a time in the host worker process.
_IMAGING_LOCK = threading.Lock()
PIPELINE_VERSION = '0.1.0'


def _json(path, content):
    path.write_text(json.dumps(content, indent=2, allow_nan=False))


def save_key_slice(volume, candidate, nodule_id, output, study_uid):
    image = nib.as_closest_canonical(nib.Nifti1Image(volume.hu, volume.affine))
    xyz = np.linalg.solve(image.affine, np.r_[candidate['center_mm'], 1])[:3]
    k = int(np.clip(round(xyz[2]), 0, image.shape[2] - 1))
    axial = np.asarray(image.dataobj)[:, :, k]
    grayscale = (np.clip((axial + 1350) / 1500, 0, 1) * 255).astype(np.uint8)
    pixels = np.flipud(grayscale.T)[:, ::-1]
    name = f'key_axial_{nodule_id}.png'
    Image.fromarray(pixels).save(output / name)
    spacing = np.linalg.norm(image.affine[:3, :3], axis=0)
    w, h = np.asarray(candidate['size_mm'][:2]) / spacing[:2]
    x, y = image.shape[0] - 1 - xyz[0], image.shape[1] - 1 - xyz[1]
    return {'name': name, 'url': f'/api/studies/{study_uid}/assets/{name}', 'plane': 'axial',
            'nodule_id': nodule_id, 'box_px': [float(x - w / 2), float(y - h / 2), float(w), float(h)]}


def run_analysis(study_uid, *, registry: Registry, home=None, progress=None):
    """Persist proposal-only nodules; W owns job/status/SSE and confirmation.

    A rerun cannot erase confirmed evidence. Cache directories are SeriesUID
    scoped. GPU execution checks platform and MemAvailable before model load.
    """
    home = Path(home or os.environ.get('SPARKMD_HOME', '/srv/spark-md'))
    progress = progress or (lambda stage: None)
    with _IMAGING_LOCK:
        progress('organize')
        study = registry.one('SELECT * FROM studies WHERE study_uid=?', (study_uid,))
        if study is None:
            raise ValueError('Study not found')
        if registry.one('SELECT nodule_id FROM nodules WHERE study_uid=? AND confirmed_at IS NOT NULL', (study_uid,)):
            raise ValueError('Cannot replace radiologist-confirmed findings')
        progress('select')
        series = registry.one('SELECT * FROM series WHERE study_uid=? AND selected=1 AND eligible=1', (study_uid,))
        if series is None:
            raise ValueError('Select an eligible series first')
        cache = home / 'cache' / series['series_uid']
        cache.mkdir(parents=True, exist_ok=True)
        progress('volume')
        volume_path = cache / 'volume.nii.gz'
        volume = dicom_to_volume(series['path'], volume_path)
        progress('detect')
        candidates = detect(volume_path)
        _json(cache / 'candidates.json', candidates)
        progress('segment')
        proposals = [propose_a7(volume, candidate) for candidate in candidates]
        progress('characterize')
        nodules, slices = [], []
        for index, (candidate, proposal) in enumerate(zip(candidates, proposals)):
            nid = 'N' + uuid.uuid5(uuid.NAMESPACE_OID, f'{series["series_uid"]}:{index}').hex
            nodule = dict(candidate, **proposal.values, nodule_id=nid,
                          long_mm=None, short_mm=None, mean_mm=None, volume_mm3=None,
                          track_id=None, lobe=None, type='solid', type_source='unverified-solid-default')
            if proposal.mask is not None:
                translation = np.eye(4)
                translation[:3, 3] = proposal.start
                nib.save(nib.Nifti1Image(proposal.mask.astype(np.uint8), volume.affine @ translation), cache / f'{nid}_proposal_mask.nii.gz')
            nodules.append(nodule)
        progress('render')
        for nodule in nodules:
            slices.append(save_key_slice(volume, nodule, nodule['nodule_id'], cache, study_uid))
        with registry.transaction() as db:
            # Recheck within the shared write lock before replacing unconfirmed rows.
            if db.execute('SELECT 1 FROM nodules WHERE study_uid=? AND confirmed_at IS NOT NULL', (study_uid,)).fetchone():
                raise ValueError('Findings were confirmed during analysis; refusing replacement')
            db.execute('DELETE FROM assessments WHERE study_uid=?', (study_uid,))
            db.execute('DELETE FROM nodules WHERE study_uid=?', (study_uid,))
            for nodule in nodules:
                db.execute('''INSERT INTO nodules
                    (nodule_id,study_uid,series_uid,center_mm,proposed_long_mm,proposed_short_mm,
                     proposed_mean_mm,proposal_source,box_mean_mm,mean_hu,type,det_score)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (nodule['nodule_id'], study_uid, series['series_uid'], json.dumps(nodule['center_mm']),
                     nodule['proposed_long_mm'], nodule['proposed_short_mm'], nodule['proposed_mean_mm'],
                     nodule['proposal_source'], nodule['box_mean_mm'], nodule['mean_hu'], nodule['type'], nodule['det_score']))
        _json(cache / 'nodules.json', nodules)
        findings = {'pipeline_version': PIPELINE_VERSION, 'lung': None,
                    'assets': {'lung_mesh': None, 'nodule_mesh': None, 'key_slices': slices},
                    'unverified': ['GB10 detector smoke', 'day-of A7 seed/background choices',
                                   'solid type assumption', 'general lobe/track matching']}
        _json(cache / 'findings.json', findings)
        return {'study_uid': study_uid, 'study_status': 'awaiting_confirmation', 'nodules': nodules,
                'assessment': None, 'assets': findings['assets']}
