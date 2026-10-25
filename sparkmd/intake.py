"""Header-only intake; StudyDate orders exams but never supplies clinical intervals."""
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time
import uuid

import pydicom

SOFT = {'b30f', 'b31f', 'b20f', 'standard', 'fc01', 'fc02', 'fc51', 'fc52'}


def now():
    return datetime.now(timezone.utc).isoformat()


def values(value):
    return [value] if isinstance(value, str) else list(value or [])


class Intake:
    def __init__(self, registry, home, status, on_organized, log):
        self.registry, self.home = registry, Path(home)
        self.status, self.on_organized, self.log = status, on_organized, log
        self.snapshots = {}

    def offsets(self):
        path = self.home / 'day_offsets.csv'
        if not path.exists():
            return {}
        with path.open(newline='') as source:
            return {(row['patient_id'], int(row['rank'])): int(row['day_offset'])
                    for row in csv.DictReader(source) if row['day_offset'].strip()}

    def rank(self, db, patient):
        offsets = self.offsets()
        rows = db.execute('SELECT study_uid FROM studies WHERE patient_id=? ORDER BY study_date, received_at, study_uid', (patient,)).fetchall()
        for rank, row in enumerate(rows):
            offset = offsets.get((patient, rank))
            db.execute('UPDATE studies SET rank=?,timepoint=?,day_offset=?,day_offset_source=? WHERE study_uid=?',
                       (rank, f'T{rank}', offset, 'sidecar' if offset is not None else 'none', row['study_uid']))

    def ingest_study(self, path):
        path = Path(path)
        groups = {}
        for file in sorted(path.rglob('*')):
            if not file.is_file():
                continue
            try:
                ds = pydicom.dcmread(file, stop_before_pixels=True, force=False)
                uid, sid, sop, patient = (str(getattr(ds, key)) for key in
                                          ('StudyInstanceUID', 'SeriesInstanceUID', 'SOPInstanceUID', 'PatientID'))
                # Header identifiers also become paths; reject path separators, not arbitrary IDs.
                if any('/' in key or '\\' in key or key in ('.', '..') for key in (uid, sid, sop, patient)):
                    raise ValueError('unsafe DICOM identifier')
                group = groups.setdefault((uid, sid), {'ds': ds, 'files': []})
                group['files'].append((file, sop))
            except (pydicom.errors.InvalidDicomError, AttributeError, EOFError, ValueError) as exc:
                self.log('system', f'Skipped non-DICOM/incomplete file: {file.name} ({type(exc).__name__})', None)
        uids = {uid for uid, _ in groups}
        if len(uids) != 1:
            reason = 'no readable DICOM images' if not uids else 'multiple studies in one intake directory'
            failed_uid = 'failed-' + uuid.uuid5(uuid.NAMESPACE_URL, str(path.resolve())).hex
            with self.registry.transaction() as db:
                db.execute("INSERT OR IGNORE INTO patients(patient_id) VALUES ('unknown')")
                db.execute("INSERT OR IGNORE INTO studies(study_uid,patient_id,received_at,inbox_path) VALUES (?,?,?,?)", (failed_uid, 'unknown', now(), str(path)))
                db.execute('UPDATE studies SET failure_reason=? WHERE study_uid=?', (reason, failed_uid))
            self.status(failed_uid, 'failed')
            raise ValueError(reason)
        uid = next(iter(uids))
        old = self.registry.one('SELECT * FROM studies WHERE study_uid=?', (uid,))
        if old:
            has_new = any(not (self.home/'studies'/uid/sid/f'{sop}.dcm').exists()
                          for (_, sid), group in groups.items() for _, sop in group['files'])
            if not has_new:
                return uid
            if old['status'] in ('analyzing', 'approved'):
                raise ValueError('cannot extend a study while analyzing or after approval')
            for series in self.registry.all('SELECT series_uid,path FROM series WHERE study_uid=?', (uid,)):
                sid = series['series_uid']
                files = sorted(Path(series['path']).glob('*.dcm'))
                if not files:
                    continue
                group = groups.setdefault((uid, sid), {'ds': pydicom.dcmread(files[0], stop_before_pixels=True), 'files': []})
                incoming_sops = {sop for _, sop in group['files']}
                group['files'].extend((file, file.stem) for file in files if file.stem not in incoming_sops)
        rows = []
        for (_, sid), group in groups.items():
            ds = group['ds']
            kernels = [str(k) for k in values(getattr(ds, 'ConvolutionKernel', []))]
            image_type = [str(k) for k in values(getattr(ds, 'ImageType', []))]
            iop = list(getattr(ds, 'ImageOrientationPatient', []))
            axial = len(iop) == 6 and all(abs(abs(float(x)) - expected) <= .05 for x, expected in zip(iop, (1, 0, 0, 0, 1, 0)))
            thickness = float(getattr(ds, 'SliceThickness', 0) or 0)
            modality = str(getattr(ds, 'Modality', ''))
            n = len(group['files'])
            # Extended deliveries are grouped with the already organized files below.
            previous = self.registry.one('SELECT n_instances,path FROM series WHERE series_uid=?', (sid,))
            if previous:
                existing_sops = {f.stem for f in Path(previous['path']).glob('*.dcm')}
                n = len(existing_sops | {sop for _, sop in group['files']})
            structural = modality == 'CT' and 'LOCALIZER' not in image_type and n >= 100 and axial and 0 < thickness <= 2.5
            if modality != 'CT': reason = 'not CT'
            elif 'LOCALIZER' in image_type or n < 100: reason = f'localizer/few ({n})'
            elif not axial: reason = 'not axial'
            elif not 0 < thickness <= 2.5: reason = f'thick ({thickness} mm)'
            elif {k.lower() for k in kernels} & SOFT: reason = 'soft kernel'
            else: reason = 'ineligible: sharp kernel / unknown kernel'
            rows.append(dict(series_uid=sid, study_uid=uid, modality=modality,
                             series_number=int(getattr(ds, 'SeriesNumber', 0) or 0), kernel=kernels[0] if kernels else '',
                             kernel_list=json.dumps(kernels), slice_thickness=thickness, n_instances=n,
                             image_type=json.dumps(image_type), axial=int(axial), path=str(self.home/'studies'/uid/sid),
                             eligible=int(reason == 'soft kernel'), eligible_reason=reason, fallback=0, selected=0,
                             select_reason=None, structural=structural))
        eligible = sorted([r for r in rows if r['eligible']], key=lambda r: (r['slice_thickness'], -r['n_instances'], r['series_uid']))
        if eligible:
            eligible[0]['selected'] = 1
            for row in eligible[1:]:
                row.update(eligible=0, eligible_reason='superseded (multiple soft candidates)')
        else:
            fallback = [r for r in rows if r['structural']]
            if len(fallback) == 1:
                fallback[0].update(eligible=1, selected=1, fallback=1, eligible_reason='only eligible series (sharp-kernel fallback)')
        first = next(iter(groups.values()))['ds']
        patient = str(first.PatientID)
        try:
            with self.registry.transaction() as db:
                db.execute('INSERT OR IGNORE INTO patients(patient_id,sex) VALUES (?,?)', (patient, str(getattr(first, 'PatientSex', ''))))
                db.execute('INSERT OR IGNORE INTO studies(study_uid,patient_id,study_date,received_at,inbox_path) VALUES (?,?,?,?,?)',
                           (uid, patient, str(getattr(first, 'StudyDate', '')), now(), str(path)))
                if old:
                    if db.execute("SELECT 1 FROM reports WHERE study_uid=? AND status='approved'", (uid,)).fetchone():
                        raise ValueError('cannot extend an approved study')
                    db.execute('DELETE FROM assessments WHERE study_uid=?', (uid,))
                    db.execute('DELETE FROM reports WHERE study_uid=?', (uid,))
                    db.execute('DELETE FROM nodules WHERE study_uid=?', (uid,))
                for row in rows:
                    row.pop('structural')
                    columns = ','.join(row)
                    updates = ','.join(f'{k}=excluded.{k}' for k in row if k != 'series_uid')
                    db.execute(f'INSERT INTO series ({columns}) VALUES ({",".join("?" for _ in row)}) ON CONFLICT(series_uid) DO UPDATE SET {updates}', tuple(row.values()))
                self.rank(db, patient)
            self.status(uid, 'received')
            for (_, sid), group in groups.items():
                destination = self.home / 'studies' / uid / sid
                destination.mkdir(parents=True, exist_ok=True)
                for source, sop in group['files']:
                    target = destination / f'{sop}.dcm'
                    if source.resolve() != target.resolve():
                        if target.exists():
                            source.unlink()
                        else:
                            shutil.move(str(source), str(target))
            if old:
                for row in rows:
                    cache = self.home/'cache'/row['series_uid']
                    if cache.exists():
                        shutil.rmtree(cache)
            self.status(uid, 'organized')
            self.on_organized(uid)
            return uid
        except Exception as exc:
            with self.registry.transaction() as db:
                db.execute('UPDATE studies SET failure_reason=? WHERE study_uid=?', (str(exc), uid))
            self.status(uid, 'failed')
            raise

    def watch(self, stop):
        while not stop.wait(2):
            for directory in (self.home/'inbox').iterdir():
                if not directory.is_dir():
                    continue
                files = [p for p in directory.rglob('*') if p.is_file()]
                if not files:
                    continue
                snapshot = tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(files))
                previous, since, processed = self.snapshots.get(directory, (None, time.monotonic(), False))
                if snapshot != previous:
                    self.snapshots[directory] = (snapshot, time.monotonic(), False)
                elif not processed and time.monotonic() - since >= 5:
                    try:
                        self.ingest_study(directory)
                    except Exception as exc:
                        self.log('system', f'Intake failed: {exc}', None)
                    self.snapshots[directory] = (snapshot, since, True)

    def reset(self, patient_ids=None, empty=False):
        """Return selected DICOM to backlog; preserve cache unless empty is requested."""
        studies = self.registry.all('SELECT * FROM studies ORDER BY patient_id,rank')
        if patient_ids is not None:
            studies = [s for s in studies if s['patient_id'] in patient_ids]
        for study in studies:
            source = self.home/'studies'/study['study_uid']
            target = self.home/'backlog'/study['patient_id']/(study['timepoint'] or 'T0')
            if source.exists():
                target.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, target, dirs_exist_ok=True)
        with self.registry.transaction() as db:
            for study in studies:
                uid = study['study_uid']
                for outbox in db.execute('SELECT o.id FROM outbox o JOIN reports r USING(report_id) WHERE r.study_uid=?', (uid,)).fetchall():
                    for extension in ('json', 'html'):
                        (self.home/'outbox'/f'{outbox["id"]}.{extension}').unlink(missing_ok=True)
                if empty:
                    for row in db.execute('SELECT series_uid FROM series WHERE study_uid=?', (uid,)).fetchall():
                        cache = self.home/'cache'/row['series_uid']
                        if cache.exists():
                            shutil.rmtree(cache)
                db.execute('UPDATE nodules SET track_id=NULL WHERE track_id IN (SELECT track_id FROM tracks WHERE first_study_uid=?)', (uid,))
                db.execute('DELETE FROM studies WHERE study_uid=?', (uid,))
        for study in studies:
            source = self.home/'studies'/study['study_uid']
            if source.exists():
                shutil.rmtree(source)
        return [study['study_uid'] for study in studies]
