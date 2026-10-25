"""Build/10 reset seeds use audited local caches, never detector fallback or human gates.

fixtures/demo-seeds.json selects three NLST controls and one LIDC baseline. Prepared
proposal/render caches live in SPARKMD_HOME/seed-cache so an explicit cold reset
can clear active caches without losing the offline background seed inputs.
Admitted A7 failures stay pending with their audit reason for manual measurement.
"""
import asyncio
import json
from pathlib import Path
import shutil


MANIFEST = Path(__file__).parent.parent/'fixtures'/'demo-seeds.json'
HERO = '134503'


def seed_plan(home):
    entries = json.loads(MANIFEST.read_text())
    if len(entries) != 4 or len({entry['patient_id'] for entry in entries}) != 4:
        raise ValueError('background seeds require four distinct patients')
    if sorted(entry['cohort'] for entry in entries) != ['lidc', 'nlst_ctrl', 'nlst_ctrl', 'nlst_ctrl']:
        raise ValueError('background seeds require three NLST controls and one LIDC case')
    for entry in entries:
        if entry['patient_id'] == HERO or entry['timepoint'] != 'T0':
            raise ValueError('the hero is replay-only; background seeds must be baselines')
        source = Path(home)/'seed-cache'/entry['series_uid']
        try:
            metadata = json.loads((source/'findings.json').read_text())
            nodes = json.loads((source/'nodules.json').read_text())
            version = tuple(int(part) for part in metadata['pipeline_version'].split('.'))
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"background seed cache unavailable: {entry['patient_id']}") from exc
        if version < (0, 3, 0) or not nodes:
            raise ValueError(f"background seed cache has no admitted proposals: {entry['patient_id']}")
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
            uid = await asyncio.to_thread(worker.intake.ingest_study, worker.config.home/'backlog'/pid/'T0')
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
        seeded.append({'patient_id': pid, 'study_uid': uid, 'timepoint': 'T0',
                       'status': 'awaiting_confirmation', 'mode': 'cached'})
    return seeded
