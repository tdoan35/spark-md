"""First real G2 run; no fixtures, automatic confirmation, or approval.

Run from the event repository with its Linux venv. See GB10-FIRST-RUN.md.
"""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

# Script execution from tests/imaging must resolve the event repo, not prep code.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

T0_SERIES = '1.2.840.113654.2.55.191672868291879989699384719070844674759'


def request(base, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def require(status, data):
    if status != 200:
        raise RuntimeError(f'Worker HTTP {status}: {data}')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Local hero DICOM root (T0 alone or all three studies)')
    parser.add_argument('--timepoint', choices=('T0', 'T1', 'T2'), default='T0')
    args = parser.parse_args()
    from sparkmd.imaging.detector import check_gpu_host, bundle_location
    from sparkmd.imaging.series import summarize_series, select_series
    import pydicom

    check_gpu_host()  # free -g + >=15 GiB; refuses the Mac before importing torch
    for key in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'NEMOCLAW_DISABLE_TELEMETRY'):
        if os.environ.get(key) != '1':
            raise RuntimeError(f'Require {key}=1')
    expected = {'torch': '2.13.0+cu130', 'monai': '1.6.1', 'numpy': '2.5.4',
                'pydicom': '3.0.2', 'nibabel': '5.4.2', 'scipy': '1.18.1', 'scikit-image': '0.26.0'}
    versions = {key: importlib.metadata.version(key) for key in expected}
    if versions != expected:
        raise RuntimeError(f'Not the locked event stack: {versions}; expected {expected}')
    import torch
    if not torch.cuda.is_available() or 'GB10' not in torch.cuda.get_device_name(0):
        raise RuntimeError('Expected CUDA NVIDIA GB10')
    print(json.dumps({'preflight': 'OK', 'versions': versions, 'bundle': str(bundle_location())}), flush=True)
    base = 'http://127.0.0.1:' + os.environ.get('SPARKMD_PORT', '8100')
    health = require(*request(base, '/api/health'))
    if health.get('placeholder'):
        raise RuntimeError('Worker uses fake imaging; restart without SPARKMD_FAKE_IMAGING')
    rows = [summarize_series(path) for path in sorted({p.parent for p in args.source.rglob('*.dcm')})]
    studies = sorted({(r['study_date'], r['study_uid']) for r in rows})
    rank = int(args.timepoint[1])
    if rank >= len(studies):
        raise RuntimeError(f'Source lacks {args.timepoint}; provide the complete hero root')
    study_uid = studies[rank][1]
    rows = select_series([r for r in rows if r['study_uid'] == study_uid])
    selected = next(r for r in rows if r['selected'])
    series_uid = selected['series_uid']
    if args.timepoint == 'T0' and series_uid != T0_SERIES:
        raise RuntimeError(f'Unexpected T0 series selection: {selected}')
    hero = selected
    header = pydicom.dcmread(next(Path(hero['path']).glob('*.dcm')), stop_before_pixels=True)
    if str(header.PatientID) != '134503':
        raise RuntimeError('Hero PatientID mismatch')
    if selected['kernel'].upper() != 'B30F':
        raise RuntimeError(f'Unexpected hero series selection: {selected}')
    uid = hero['study_uid']
    home = Path(os.environ.get('SPARKMD_HOME', '/srv/spark-md'))
    status, study = request(base, '/api/studies/' + uid)
    if status == 404:
        # Assemble outside the watched inbox, then atomically publish a complete copy.
        home.mkdir(parents=True, exist_ok=True)
        (home / 'inbox').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='g2-stage-', dir=home) as tmp:
            staging = Path(tmp) / 'study'
            for row in rows:
                shutil.copytree(row['path'], staging / row['series_uid'])
            staging.rename(home / 'inbox' / ('g2-' + uuid.uuid4().hex))
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            status, study = request(base, '/api/studies/' + uid)
            if status == 200 and study['status'] in ('organized', 'failed'):
                break
            time.sleep(1)
        else:
            raise RuntimeError(f'Intake did not organize {args.timepoint} within 45 s; inspect worker log')
    study = require(status, study)
    if study['status'] == 'failed':
        raise RuntimeError(f'Existing study failed: {study.get("failure_reason")}; inspect before rerunning')
    if study['status'] != 'organized':
        raise RuntimeError(f'First-run check requires organized {args.timepoint}, got {study["status"]}; no reset or overwrite performed')
    require(*request(base, f'/api/studies/{uid}/select-series', {'series_uid': series_uid, 'reason': f'G2 first real hero {args.timepoint} run; B30f 2 mm'}))
    print(json.dumps({'selected': series_uid, 'study_uid': uid, 'kernel': selected['kernel'], 'instances': selected['n_instances']}), flush=True)
    deadline, previous = time.monotonic() + 300, None
    while time.monotonic() < deadline:
        job = require(*request(base, f'/api/studies/{uid}/analyze', {'wait_s': 1}))
        if (job['stage'], job['state']) != previous:
            print(json.dumps({'job': job}), flush=True)
            previous = job['stage'], job['state']
        if job['state'] == 'failed':
            raise RuntimeError(f'Analysis failed: {job}')
        if job['state'] == 'done':
            break
    else:
        raise RuntimeError('Analysis exceeded 300 s; job is NOT cancelled; inspect /api/jobs before rerunning')
    findings = require(*request(base, f'/api/studies/{uid}/findings'))
    nodules = findings['nodules']
    if not nodules or findings['assessment'] is not None or job.get('study_status') != 'awaiting_confirmation':
        raise RuntimeError(f'G2 contract failed: {findings}')
    if set(findings['pending_confirmation']) != {n['nodule_id'] for n in nodules}:
        raise RuntimeError('Every detected nodule must remain pending human confirmation')
    if any(n.get(key) is not None for n in nodules for key in ('long_mm', 'short_mm', 'mean_mm', 'volume_mm3')):
        raise RuntimeError('Pipeline populated accepted sizes before confirmation')
    if not any(n['proposal']['mean_mm'] is not None for n in nodules):
        raise RuntimeError('No A7 diameter proposal: inspect cache nodules.json reasons; candidates must stay visible')
    slices = findings['assets']['key_slices']
    if {s['nodule_id'] for s in slices} != {n['nodule_id'] for n in nodules}:
        raise RuntimeError('A candidate has no key slice')
    for item in slices:
        with urllib.request.urlopen(base + item['url'], timeout=15) as response:
            if response.read(8) != b'\x89PNG\r\n\x1a\n':
                raise RuntimeError(f'Key slice is not PNG: {item}')
    print(json.dumps({'G2': 'PASS', 'timepoint': args.timepoint, 'study_uid': uid, 'series_uid': series_uid, 'elapsed_s': job['elapsed_s'],
                      'pending_confirmation': findings['pending_confirmation'],
                      'proposals': [{'nodule_id': n['nodule_id'], 'det_score': n['det_score'], **n['proposal']} for n in nodules],
                      'lobes': [n['lobe'] for n in nodules], 'assessment': None,
                      'next': f'Open {base}; research demo, not for clinical use. Review proposals and click Confirm manually.'}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, StopIteration) as exc:
        print(f'G2 FAIL: {exc}', file=sys.stderr)
        sys.exit(1)
