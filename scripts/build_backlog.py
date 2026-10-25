#!/usr/bin/env python3
"""Copy staged studies into replay backlog; clinical tables alone supply intervals.

Run once before starting intake:
  .venv/bin/python scripts/build_backlog.py --data /drive/data --home /srv/spark-md
Use --patients 134503 for the Mac hero-only smoke. Originals are never moved or
symlinked: intake moves backlog files, so links would endanger source data.
NLST: CC BY 4.0, TCIA doi:10.7937/TCIA.HMQ8-J677. LIDC-IDRI: CC BY 3.0,
TCIA doi:10.7937/K9/TCIA.2015.LO9QL9SX. Download source: NCI IDC.
"""
import argparse
import csv
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import shutil
import sys

import pydicom


def integer_day(value):
    if not value or value.strip().lower() in ('nan', 'na'):
        return None
    try:
        day = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f'invalid clinical day offset: {value!r}') from exc
    if not day.is_finite() or day != day.to_integral_value():
        raise ValueError(f'clinical day offset must be an integer: {value!r}')
    return int(day)


def clinical_offsets(data):
    offsets = {}

    def store(patient, rank, value):
        day = integer_day(value)
        if day is None:
            return
        key = (patient, rank)
        if key in offsets and offsets[key] != day:
            raise ValueError(f'conflicting clinical offsets for {patient} T{rank}')
        offsets[key] = day

    picked = data/'nlst'/'nlst_picked_prsn.csv'
    negative = data/'nlst'/'nlst_neg_neg_pos.csv'
    for path in (picked, negative):
        if not path.is_file():
            raise FileNotFoundError(f'clinical table missing: {path}')
        with path.open(newline='') as source:
            for row in csv.DictReader(source):
                pid = row['pid'].strip()
                days = [row.get(f'scr_days{rank}', '') for rank in range(3)] if path == picked else row['days'].split('/')
                for rank, value in enumerate(days):
                    store(pid, rank, value)
    return offsets


def ordered_studies(patient_dir):
    studies = []
    for directory in sorted(patient_dir.iterdir()):
        if not directory.is_dir():
            continue
        sample = next(directory.rglob('*.dcm'), None)
        if sample is None:
            continue
        ds = pydicom.dcmread(sample, stop_before_pixels=True)
        if str(ds.PatientID) != patient_dir.name:
            raise ValueError(f'patient directory/header mismatch: {patient_dir.name}')
        date = str(getattr(ds, 'StudyDate', ''))
        studies.append((date, str(ds.StudyInstanceUID), directory))
    return sorted(studies)


def build(data, home, patients=None):
    data, home = Path(data).resolve(), Path(home).resolve()
    if home == data or home.is_relative_to(data):
        raise ValueError('SPARKMD_HOME must be outside the source data directory')
    offsets = clinical_offsets(data)
    selected = set(patients) if patients else None
    rows = []
    found = set()
    plans = []
    for collection in ('nlst', 'lidc_idri'):
        source = data/'dicom'/collection
        if not source.is_dir():
            continue
        for patient_dir in sorted(source.iterdir()):
            if not patient_dir.is_dir() or (selected is not None and patient_dir.name not in selected):
                continue
            patient = patient_dir.name
            studies = ordered_studies(patient_dir)
            if studies:
                found.add(patient)
            for rank, (date, uid, directory) in enumerate(studies):
                destination = home/'backlog'/patient/f'T{rank}'
                plans.append((patient, rank, date, uid, directory, destination))
                day = offsets.get((patient, rank)) if collection == 'nlst' else None
                if day is not None:
                    rows.append((patient, rank, day))
    if selected is not None and selected - found:
        raise ValueError('no staged DICOM for requested patients: '+', '.join(sorted(selected-found)))
    if not plans:
        raise ValueError(f'no staged studies under {data}/dicom')
    home.mkdir(parents=True, exist_ok=True)
    summary = []
    for patient, rank, date, uid, source, destination in plans:
        # Merging the same source is safe on rerun; reject another study at this rank.
        existing = next(destination.rglob('*.dcm'), None) if destination.is_dir() else None
        if existing is not None:
            ds = pydicom.dcmread(existing, stop_before_pixels=True)
            if str(ds.StudyInstanceUID) != uid:
                raise ValueError(f'backlog already contains a different study: {destination}')
        shutil.copytree(source, destination, dirs_exist_ok=True)
        summary.append({'patient_id': patient, 'timepoint': f'T{rank}', 'study_uid': uid,
                        'study_date': date, 'day_offset': offsets.get((patient, rank)) if not patient.startswith('LIDC-') else None,
                        'dicom_files': sum(1 for _ in destination.rglob('*.dcm'))})
    target = home/'day_offsets.csv'
    temporary = target.with_suffix('.csv.tmp')
    with temporary.open('w', newline='') as output:
        writer = csv.writer(output)
        writer.writerow(('patient_id', 'rank', 'day_offset'))
        writer.writerows(sorted(rows))
    temporary.replace(target)
    return {'home': str(home), 'studies': summary, 'day_offset_rows': len(rows),
            'source': 'NCI IDC / TCIA; dates order studies only; intervals from NLST clinical tables'}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data', type=Path, required=True, help='staged data/ root, not dicom/ or a patient directory')
    parser.add_argument('--home', type=Path, default=Path(os.environ.get('SPARKMD_HOME', '/srv/spark-md')))
    parser.add_argument('--patients', nargs='+', help='optional patient IDs; default all staged NLST/LIDC patients')
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.data, args.home, args.patients), indent=2))
    except (OSError, ValueError, KeyError, pydicom.errors.InvalidDicomError) as exc:
        print(f'build_backlog: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
