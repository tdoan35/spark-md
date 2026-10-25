"""Precompute Sybil 1-6 year lung-cancer risk for the demo patients -> fixtures/sybil_risk.json.

Demo-only research display (docs/plans/2026-10-25-sybil-demo-risk.md). Not used by the worker.

Setup (spike, Oct 25): Sybil's pins (python<3.11, torch 1.13) do not install on the GB10, so run it from a
venv that sees the project's torch and a clone of https://github.com/reginabarzilaygroup/Sybil on sys.path
(the PyPI package named "sybil" is an unrelated doctest tool). First run downloads ~730 MB of checkpoints to ~/.sybil.

    python scripts/sybil_precompute.py --dicom ~/spark-md/data/dicom/nlst --out fixtures/sybil_risk.json
    python scripts/sybil_precompute.py --from-rows rows.jsonl --out fixtures/sybil_risk.json   # no model needed
"""
import argparse
import datetime
import glob
import json
import os
import time

GROUPS = {'hero_cancer': '134503 113820 109965 106194 106000',
          'neg_neg_pos': '102537 117502 113918 131156',
          'control': '100285 100288 100005'}
NOTES = 'NLST-trained model; demo patients may overlap its training set. Research display, not a diagnosis.'


def score(dicom_root, pids):
    import pydicom
    import torch
    _load = torch.load  # Sybil checkpoints are full pickles from a trusted release; torch>=2.6 defaults to weights_only
    torch.load = lambda *a, **k: _load(*a, **{**k, 'weights_only': False})
    from sybil import Serie, Sybil
    label = {p: g for g, v in GROUPS.items() for p in v.split()}
    model = Sybil('sybil_ensemble')
    rows = []
    for pid in pids:
        studies = {}
        for d in glob.glob(f'{dicom_root}/{pid}/*/CT_*'):
            files = sorted(glob.glob(d + '/*.dcm'))
            if len(files) < 50:
                continue
            h = pydicom.dcmread(files[0], stop_before_pixels=True)
            studies.setdefault(h.StudyDate, []).append((len(files), d, files, str(getattr(h, 'ConvolutionKernel', '?'))))
        for i, date in enumerate(sorted(studies)):
            n, d, files, kernel = max(studies[date])
            t = time.time()
            risk = [round(float(x), 4) for x in model.predict([Serie(files)]).scores[0]]
            rows.append(dict(pid=pid, group=label[pid], screen=f'T{i}', date=date, slices=n, kernel=kernel,
                             study_uid=os.path.basename(os.path.dirname(d)), series_uid=os.path.basename(d)[3:],
                             risk_1_to_6yr=risk, sec=round(time.time() - t, 1)))
            print(json.dumps(rows[-1]), flush=True)
    return rows


def build_fixture(rows, sybil_commit):
    patients = {}
    for r in rows:
        p = patients.setdefault(r['pid'], {'group': r['group'], 'screens': []})
        p['screens'].append({'timepoint': r['screen'], 'study_uid': r['study_uid'], 'series_uid': r['series_uid'],
                             'study_date': r['date'], 'kernel': r['kernel'], 'slices': r['slices'],
                             'risk_1_to_6yr': r['risk_1_to_6yr']})
    for p in patients.values():
        p['screens'].sort(key=lambda s: s['timepoint'])
    return {'model': 'sybil_ensemble', 'sybil_commit': sybil_commit, 'generated': datetime.date.today().isoformat(),
            'host': 'GB10', 'notes': NOTES, 'patients': patients}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dicom', default=os.path.expanduser('~/spark-md/data/dicom/nlst'))
    ap.add_argument('--out', default='fixtures/sybil_risk.json')
    ap.add_argument('--from-rows', help='JSONL rows from a previous run; skips scoring')
    ap.add_argument('--sybil-commit', default='unknown')
    ap.add_argument('pids', nargs='*')
    a = ap.parse_args()
    if a.from_rows:
        rows = [json.loads(line) for line in open(a.from_rows) if line.startswith('{')]
    else:
        rows = score(a.dicom, a.pids or [p for v in GROUPS.values() for p in v.split()])
    with open(a.out, 'w') as f:
        json.dump(build_fixture(rows, a.sybil_commit), f, indent=1)
        f.write('\n')


if __name__ == '__main__':
    main()
