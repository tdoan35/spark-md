"""Build/10 reset seeds use audited local caches, never detector fallback or human gates.

fixtures/demo-seeds.json selects all three screens for three NLST controls plus one LIDC study. Prepared
proposal/render caches live in SPARKMD_HOME/seed-cache so an explicit cold reset
can clear active caches without losing the offline background seed inputs.
Admitted A7 failures stay pending with their audit reason for manual measurement.
NLST histories are restored T0 -> T1 -> T2 with clinical day_offsets.csv intervals.
All ten studies remain awaiting_confirmation, including negative follow-ups.
"""
import asyncio
import json
from pathlib import Path
import shutil


MANIFEST = Path(__file__).parent.parent/'fixtures'/'demo-seeds.json'
HERO = '134503'


def seed_plan(home, offsets):
    entries = json.loads(MANIFEST.read_text())
    patients = {}
    for entry in entries:
        pid = entry['patient_id']
        if pid == HERO:
            raise ValueError('the hero is replay-only')
        cohort, timepoints = patients.setdefault(pid, (entry['cohort'], set()))
        if cohort != entry['cohort'] or entry['timepoint'] in timepoints:
            raise ValueError('inconsistent or duplicate background seed study')
        timepoints.add(entry['timepoint'])
    if sorted(cohort for cohort, _ in patients.values()) != ['lidc', 'nlst_ctrl', 'nlst_ctrl', 'nlst_ctrl']:
        raise ValueError('background seeds require three NLST controls and one LIDC case')
    for cohort, timepoints in patients.values():
        if timepoints != ({'T0', 'T1', 'T2'} if cohort == 'nlst_ctrl' else {'T0'}):
            raise ValueError('seed every control screen and the single LIDC baseline')
    entries.sort(key=lambda entry: (entry['patient_id'], entry['timepoint']))
    for entry in entries:
        if entry['cohort'] == 'nlst_ctrl' and (entry['patient_id'], int(entry['timepoint'][1:])) not in offsets:
            raise ValueError(f"clinical day offset missing: {entry['patient_id']} {entry['timepoint']}")
        source = Path(home)/'seed-cache'/entry['series_uid']
        try:
            metadata = json.loads((source/'findings.json').read_text())
            nodes = json.loads((source/'nodules.json').read_text())
            version = tuple(int(part) for part in metadata['pipeline_version'].split('.'))
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"background seed cache unavailable: {entry['patient_id']}") from exc
        if version < (0, 3, 0) or not isinstance(nodes, list):
            raise ValueError(f"background seed cache has no audited proposal list: {entry['patient_id']}")
    return entries


async def seed_background(worker, entries):
    """Ingest and analyze sequentially; every analysis is strictly cache-only."""
    seeded = []
    for entry in entries:
        pid, sid = entry['patient_id'], entry['series_uid']
        source = worker.config.home/'seed-cache'/sid
        await asyncio.to_thread(shutil.copytree, source, worker.config.home/'cache'/sid, dirs_exist_ok=True)
        worker.seeding_patient = pid
        try:
            uid = await asyncio.to_thread(worker.intake.ingest_study, worker.config.home/'backlog'/pid/entry['timepoint'])
        finally:
            worker.seeding_patient = None
        if uid != entry['study_uid']:
            raise ValueError(f'background seed study/header mismatch: {pid}')
        with worker.registry.transaction() as db:
            db.execute('UPDATE patients SET cohort=? WHERE patient_id=?', (entry['cohort'], pid))
        selected, code = await worker.call_tool('select_series', {
            'study_uid': uid, 'series_uid': sid, 'reason': 'background cohort seed; recorded proposals only'}, False)
        if code != 200:
            raise ValueError(f'background seed series unavailable: {pid}: {selected}')
        job, _ = await worker.analyze(uid, 300)
        if job['state'] != 'done' or job['study_status'] != 'awaiting_confirmation':
            raise ValueError(f'background seed analysis failed: {pid}: {job}')
        worker.log('system', 'Background cohort seed ready; cached proposals require radiologist confirmation', uid,
                   {'patient_id': pid, 'mode': 'cached'})
        seeded.append({'patient_id': pid, 'study_uid': uid, 'timepoint': entry['timepoint'],
                       'status': 'awaiting_confirmation', 'mode': 'cached'})
    return seeded
