"""Worker entry point: original DICOM -> detector -> unconfirmed A7 proposals.

Uses W's registry; never assigns an assessment or confirms a diameter. Threshold
height-based lobes are approximate; conservative lobe/position links and all
unresolved candidates are explicitly audited. Registry's solid default remains
an unverified type assumption in cache audit data.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time
import uuid

import nibabel as nib
import numpy as np

from sparkmd.registry import Registry
from .detector import detect
from .lobes import split_lungs
from .meshes import render_meshes
from .slices import render_slices
from .proposals import propose_a7
from .tracking import prepare_tracks, persist_tracks
from .volume import dicom_to_volume

# One heavyweight imaging job at a time in the host worker process.
_IMAGING_LOCK = threading.Lock()
PIPELINE_VERSION = '0.4.0'
# Demo operating point, not a validated clinical sensitivity threshold.
# Admission is independent of A7 success and never selects track identity.
MIN_NODULE_SCORE = 0.90
ADMISSION_RULE = 'det-score-ge-0.90-v1'


def _json(path, content):
    path.write_text(json.dumps(content, indent=2, allow_nan=False))


def run_analysis(study_uid, *, registry: Registry, home=None, progress=None):
    """Persist proposal-only nodules; W owns job/status/SSE and confirmation.

    A rerun cannot erase confirmed evidence. Cache directories are SeriesUID
    scoped. GPU execution checks platform and MemAvailable before model load.
    """
    home = Path(home or os.environ.get('SPARKMD_HOME', '/srv/spark-md'))
    notify = progress or (lambda stage: None)
    stage_timings, current = {}, [None, time.perf_counter()]

    def finish_stage():
        now = time.perf_counter()
        if current[0] is not None:
            stage_timings[current[0]] = round(now - current[1], 6)
        current[1] = now

    def progress(stage):
        finish_stage()
        current[0] = stage
        notify(stage)
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
        for index, candidate in enumerate(candidates):
            admitted = candidate['det_score'] >= MIN_NODULE_SCORE
            candidate.update(
                nodule_id='N' + uuid.uuid5(uuid.NAMESPACE_OID, f'{series["series_uid"]}:{index}').hex,
                admitted=admitted, admission_rule=ADMISSION_RULE,
                admission_reason=None if admitted else 'det_score_below_0.90')
        _json(cache / 'candidates.json', candidates)
        progress('segment')
        proposals = [propose_a7(volume, candidate) for candidate in candidates]
        for candidate, proposal in zip(candidates, proposals):
            candidate.update(proposal.values)
        # Retain every detector candidate, including excluded A7 failures.
        _json(cache / 'candidates.json', candidates)
        lung_split = split_lungs(volume)
        _json(cache / 'lung_geometry.json', lung_split.geometry)
        nib.save(nib.Nifti1Image(lung_split.labels, lung_split.affine), cache / 'lung_sides.nii.gz')
        progress('characterize')
        nodules = []
        for candidate, proposal in zip(candidates, proposals):
            if not candidate['admitted']:
                continue
            nid = candidate['nodule_id']
            nodule = dict(candidate,
                          long_mm=None, short_mm=None, mean_mm=None, volume_mm3=None,
                          track_id=None, lobe=None, type='solid', type_source='unverified-solid-default')
            nodule.update(lung_split.label(candidate['center_mm']))
            if proposal.mask is not None:
                translation = np.eye(4)
                translation[:3, 3] = proposal.start
                nib.save(nib.Nifti1Image(proposal.mask.astype(np.uint8), volume.affine @ translation), cache / f'{nid}_proposal_mask.nii.gz')
            nodules.append(nodule)
        progress('match')
        tracks = prepare_tracks(registry, home, study, nodules)
        progress('render')
        assets = render_meshes(lung_split, nodules, cache, study_uid)
        assets.update(render_slices(volume, nodules, cache, study_uid))
        with registry.transaction() as db:
            # Recheck within the shared write lock before replacing unconfirmed rows.
            if db.execute('SELECT 1 FROM nodules WHERE study_uid=? AND confirmed_at IS NOT NULL', (study_uid,)).fetchone():
                raise ValueError('Findings were confirmed during analysis; refusing replacement')
            db.execute('DELETE FROM assessments WHERE study_uid=?', (study_uid,))
            db.execute('DELETE FROM nodules WHERE study_uid=?', (study_uid,))
            persist_tracks(db, tracks)
            admission = {
                'rule': ADMISSION_RULE, 'min_det_score': MIN_NODULE_SCORE,
                'admitted': [c['nodule_id'] for c in candidates if c['admitted']],
                'excluded': [{k: c[k] for k in ('nodule_id', 'det_score', 'admission_reason', 'proposal_reason')}
                             for c in candidates if not c['admitted']],
            }
            db.execute('INSERT INTO agent_events(ts,study_uid,source,message,payload_json) VALUES (?,?,?,?,?)',
                       (datetime.now(timezone.utc).isoformat(), study_uid, 'system',
                        f"Candidate admission {ADMISSION_RULE}: {len(nodules)}/{len(candidates)} require confirmation; excluded candidates retained in cache",
                        json.dumps(admission)))
            for nodule in nodules:
                db.execute('''INSERT INTO nodules
                    (nodule_id,study_uid,series_uid,track_id,lobe,center_mm,proposed_long_mm,proposed_short_mm,
                     proposed_mean_mm,proposal_source,box_mean_mm,mean_hu,type,det_score)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (nodule['nodule_id'], study_uid, series['series_uid'], nodule['track_id'], nodule['lobe'],
                     json.dumps(nodule['center_mm']), nodule['proposed_long_mm'], nodule['proposed_short_mm'],
                     nodule['proposed_mean_mm'], nodule['proposal_source'], nodule['box_mean_mm'],
                     nodule['mean_hu'], nodule['type'], nodule['det_score']))
                decision = nodule['matching']
                message = (f"Track link: {nodule['nodule_id']} <- {decision['prior_nodule_id']} (high confidence; approximate lobe)"
                           if decision['status'] == 'matched' else
                           f"LOW-CONFIDENCE TRACK UNLINKED: {nodule['nodule_id']}; {', '.join(decision['flags'])}"
                           if decision['status'] == 'unresolved' else f"New nodule track: {nodule['nodule_id']}")
                db.execute('INSERT INTO agent_events(ts,study_uid,source,message,payload_json) VALUES (?,?,?,?,?)',
                           (datetime.now(timezone.utc).isoformat(), study_uid, 'system', message, json.dumps(decision)))
        _json(cache / 'nodules.json', nodules)
        findings = {'pipeline_version': PIPELINE_VERSION,
                    'lung': {'mask_source': 'threshold', 'volume_ml': lung_split.geometry['volume_ml'],
                             'lobe_rule': lung_split.geometry['lobe_rule'], 'approximate': True},
                    'assets': assets,
                    'unverified': ['GB10 detector smoke', 'day-of A7 seed/background choices',
                                   'solid type assumption', 'height-based lobes and translation-only matching']}
        _json(cache / 'findings.json', findings)
        finish_stage()
        _json(cache / 'stage_timings.json', stage_timings)
        return {'study_uid': study_uid, 'study_status': 'awaiting_confirmation', 'nodules': nodules,
                'assessment': None, 'assets': findings['assets']}
