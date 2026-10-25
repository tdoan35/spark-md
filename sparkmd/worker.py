import asyncio
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import threading
import time
import urllib.request
import uuid

from .config import Config
from .events import Events
from .findings import findings, recompute, rules_module
from .intake import Intake
from .registry import Registry

STAGES = ['organize', 'select', 'volume', 'detect', 'segment', 'characterize', 'match', 'rules', 'render']


def now():
    return datetime.now(timezone.utc).isoformat()


class Worker:
    def __init__(self, config=None):
        self.config = config or Config()
        self.config.prepare()
        self.registry = Registry(os.environ.get('SPARKMD_DB', str(self.config.home/'registry.sqlite')))
        self.events = Events()
        self.jobs = {}
        self.jobs_lock = threading.RLock()
        self.analysis_lock = threading.Lock()
        self.stop = threading.Event()
        self.intake = Intake(self.registry, self.config.home, self.status, self.organized, self.log)
        self.threads = []
        if self.config.fake_seed:
            self.seed()

    def log(self, source, message, uid=None, payload=None):
        with self.registry.transaction() as db:
            cur = db.execute('INSERT INTO agent_events(ts,study_uid,source,message,payload_json) VALUES (?,?,?,?,?)',
                             (now(), uid, source, message, json.dumps(payload or {})))
            event = dict(db.execute('SELECT * FROM agent_events WHERE id=?', (cur.lastrowid,)).fetchone())
        event.update(payload or {})
        self.events.emit('agent_log', event)
        return event

    def status(self, uid, status):
        with self.registry.transaction() as db:
            previous = db.execute('SELECT status FROM studies WHERE study_uid=?', (uid,)).fetchone()
            db.execute('UPDATE studies SET status=? WHERE study_uid=?', (status, uid))
        if previous and (previous['status'] != status or status == 'received'):
            self.events.emit('study_updated', {'study_uid': uid, 'status': status})
            self.events.emit('worklist_changed', {'reason': 'status', 'study_uid': uid})
            if status == 'received':
                self.events.emit('worklist_changed', {'reason': 'received', 'study_uid': uid})

    def organized(self, uid):
        with self.jobs_lock:
            self.jobs = {key: job for key, job in self.jobs.items() if job['study_uid'] != uid}
        self.log('system', 'Study organized; agent triage requested', uid)
        self.trigger(uid)

    def trigger(self, uid, confirmed=False):
        key = f'study-{uid}' + ('-confirmed' if confirmed else '')
        if not self.config.hook_url:
            self.log('system', 'Agent hook not configured; triage not dispatched', uid)
            return
        def send():
            message = (f'Study {uid} has radiologist-confirmed measurements. Fetch findings and draft radiology and PCP reports.' if confirmed else
                       f'Study {uid} is organized. Inspect and select an eligible series, run analysis, then stop for radiologist confirmation. Do not draft reports before confirmation.')
            request = urllib.request.Request(self.config.hook_url, json.dumps({'message': message, 'name': 'spark-md', 'agentId': 'main', 'deliver': False}).encode(),
                      {'Content-Type': 'application/json', 'Authorization': f'Bearer {self.config.hook_token}', 'Idempotency-Key': key})
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    self.log('system', f'Agent hook accepted: HTTP {response.status}', uid, {'idempotency_key': key})
            except Exception as exc:
                self.log('system', f'Agent hook failed: {exc}', uid)
        thread = threading.Thread(target=send, daemon=True)
        self.threads.append(thread)
        thread.start()

    def seed(self):
        fixture = json.loads((Path(__file__).parent.parent/'fixtures'/'studies.json').read_text())
        with self.registry.transaction() as db:
            for patient in fixture['patients']:
                pid = patient['patient_id']
                db.execute('INSERT OR IGNORE INTO patients(patient_id,cohort) VALUES (?,?)', (pid, 'fixture'))
                for rank, study in enumerate(patient['studies']):
                    uid = study['study_uid']
                    db.execute('''INSERT OR IGNORE INTO studies(study_uid,patient_id,rank,timepoint,day_offset,day_offset_source,status,received_at)
                                  VALUES (?,?,?,?,?,?,'received',?)''', (uid, pid, rank, study['timepoint'], study['day_offset'], 'fixture', now()))
                    for suffix, eligible, kernel in [('soft', 1, 'B30f'), ('sharp', 0, 'B50f')]:
                        sid = f'{uid}-{suffix}'
                        db.execute('''INSERT OR IGNORE INTO series(series_uid,study_uid,modality,kernel,slice_thickness,n_instances,axial,path,eligible,eligible_reason)
                                      VALUES (?,?,'CT',?,2,150,1,?,?,?)''', (sid, uid, kernel, str(self.config.home/'studies'/uid/sid), eligible, 'soft kernel' if eligible else 'ineligible: sharp kernel'))

    def worklist(self, status=None):
        rows = self.registry.all('''SELECT s.*,a.lung_rads,(SELECT COUNT(*) FROM reports r WHERE r.study_uid=s.study_uid
            AND r.status='draft' AND r.version=(SELECT MAX(rr.version) FROM reports rr WHERE rr.study_uid=r.study_uid AND rr.kind=r.kind)) AS reports_awaiting
            FROM studies s LEFT JOIN assessments a USING(study_uid)''')
        priorities = {'urgent': 0, 'elevated': 1, 'routine': 2}
        categories = {'4X': 0, '4B': 1, '4A': 2, '3': 3, '2': 4, '1': 5}
        return sorted([r for r in rows if status is None or r['status'] == status],
                      key=lambda r: (priorities.get(r['priority'], 3), categories.get(r['lung_rads'], 6), r['received_at'], r['study_uid']))

    def study(self, uid):
        row = next((r for r in self.worklist() if r['study_uid'] == uid), None)
        if row is None:
            return {'error': 'study not found'}, 404
        row['series'] = self.registry.all('SELECT * FROM series WHERE study_uid=? ORDER BY series_uid', (uid,))
        for series in row['series']:
            for field in ('kernel_list', 'image_type'):
                series[field] = json.loads(series[field] or '[]')
        row['priors'] = self.registry.all('''SELECT s.study_uid,s.timepoint,s.day_offset,s.status,a.lung_rads FROM studies s
            LEFT JOIN assessments a USING(study_uid) WHERE s.patient_id=? AND s.rank<? ORDER BY s.rank DESC''', (row['patient_id'], row['rank']))
        with self.jobs_lock:
            row['job'] = next((self.job_payload(j) for j in self.jobs.values() if j['study_uid'] == uid), None)
        return row, 200

    def job_payload(self, job):
        study = self.registry.one('SELECT status FROM studies WHERE study_uid=?', (job['study_uid'],))
        return {k: job[k] for k in ('job_id', 'study_uid', 'state', 'stage', 'stage_index', 'error')} | {
            'elapsed_s': round((job.get('ended', time.monotonic()) - job['started']), 3), 'study_status': study['status'] if study else None}

    def progress(self, job, stage):
        with self.jobs_lock:
            job.update(stage=stage, stage_index=STAGES.index(stage), state='running')
            payload = self.job_payload(job)
        self.events.emit('job_progress', payload)

    def run_job(self, job, series):
        # GB10 imaging jobs share unified memory; never run two GPU pipelines together.
        with self.analysis_lock:
            self._execute_job(job, series)

    def _execute_job(self, job, series):
        uid = job['study_uid']
        try:
            self.status(uid, 'analyzing')
            cache = self.config.home/'cache'/series['series_uid']
            cache.mkdir(parents=True, exist_ok=True)
            if self.config.fake:
                for stage in STAGES:
                    self.progress(job, stage)
                    if self.stop.wait(max(0, self.config.fake_seconds) / len(STAGES)):
                        raise RuntimeError('worker shutting down')
                study = self.registry.one('SELECT * FROM studies WHERE study_uid=?', (uid,))
                fixture = json.loads((Path(__file__).parent.parent/'fixtures'/'studies.json').read_text())
                proposal = next((s for p in fixture['patients'] for s in p['studies'] if s['study_uid'] == uid), {'long_mm': 10, 'short_mm': 10})
                with self.registry.transaction() as db:
                    track = study['patient_id']+'-track-1'
                    db.execute('INSERT OR IGNORE INTO tracks(track_id,patient_id,first_study_uid) VALUES (?,?,?)', (track, study['patient_id'], uid))
                    db.execute('''INSERT OR IGNORE INTO nodules(nodule_id,study_uid,series_uid,track_id,lobe,center_mm,
                        proposed_long_mm,proposed_short_mm,proposed_mean_mm,proposal_source,box_mean_mm,type,det_score,mean_hu)
                        VALUES (?,?,?,?,?,?,?,?,?,'fixture',?,'solid',1,40)''',
                        (uid+'-N1', uid, series['series_uid'], track, 'LUL', '[0,0,0]', proposal['long_mm'], proposal['short_mm'],
                         round((proposal['long_mm']+proposal['short_mm'])/2, 1), proposal['long_mm']))
            else:
                from sparkmd.imaging import run_analysis
                run_analysis(uid, registry=self.registry, home=self.config.home, progress=lambda stage: self.progress(job, stage))
            self.status(uid, 'awaiting_confirmation')
            if not self.registry.one('SELECT nodule_id FROM nodules WHERE study_uid=?', (uid,)):
                if recompute(self, uid):
                    self.trigger(uid, confirmed=True)
            with self.jobs_lock:
                job.update(state='done', ended=time.monotonic())
            self.events.emit('job_progress', self.job_payload(job))
        except Exception as exc:
            with self.registry.transaction() as db:
                db.execute('UPDATE studies SET failure_reason=? WHERE study_uid=?', (str(exc), uid))
            self.status(uid, 'failed')
            with self.jobs_lock:
                job.update(state='failed', error=f'{type(exc).__name__}: {exc}', ended=time.monotonic())
            self.events.emit('job_progress', self.job_payload(job))
            self.log('system', f'Analysis failed: {exc}', uid)

    async def analyze(self, uid, wait):
        series = self.registry.one('SELECT * FROM series WHERE study_uid=? AND selected=1 AND select_reason IS NOT NULL', (uid,))
        if not series:
            return {'error': 'select a series first'}, 409
        with self.jobs_lock:
            job = next((j for j in self.jobs.values() if j['study_uid'] == uid and j['state'] != 'failed'), None)
            if job is None:
                job = {'job_id': uuid.uuid4().hex, 'study_uid': uid, 'state': 'queued', 'stage': 'organize', 'stage_index': 0,
                       'started': time.monotonic(), 'error': None}
                self.jobs[job['job_id']] = job
                thread = threading.Thread(target=self.run_job, args=(job, series), daemon=True)
                self.threads.append(thread)
                thread.start()
        deadline = time.monotonic() + max(0, min(300, wait))
        while job['state'] in ('queued', 'running') and time.monotonic() < deadline:
            await asyncio.sleep(.05)
        return self.job_payload(job), 200

    async def call_tool(self, name, args, agent=True):
        uid = args.get('study_uid')
        if name == 'list_studies':
            return self.worklist(args.get('status')), 200
        if name == 'get_study':
            return self.study(uid)
        if name == 'get_findings':
            return findings(self, uid, agent)
        if name == 'run_analysis':
            return await self.analyze(uid, float(args.get('wait_s', self.config.mcp_wait)))
        if name == 'select_series':
            with self.registry.transaction() as db:
                row = db.execute('SELECT * FROM series WHERE series_uid=? AND study_uid=?', (args.get('series_uid'), uid)).fetchone()
                if not row: return {'error': 'series not found'}, 404
                if not row['eligible']: return {'error': row['eligible_reason']}, 422
                study = db.execute('SELECT status FROM studies WHERE study_uid=?', (uid,)).fetchone()
                if study['status'] not in ('received', 'organized', 'failed'):
                    return {'error': 'analysis already started'}, 409
                db.execute('UPDATE series SET selected=0 WHERE study_uid=?', (uid,))
                db.execute('UPDATE series SET selected=1,select_reason=? WHERE series_uid=?', (args.get('reason', 'agent selection'), row['series_uid']))
            return {'series_uid': row['series_uid'], 'selected': True, 'fallback': bool(row['fallback'])}, 200
        if name == 'save_report':
            if args.get('kind') not in ('radiology', 'pcp_letter') or not isinstance(args.get('markdown'), str) or not args['markdown'].strip():
                return {'error': 'kind and nonempty markdown required'}, 422
            with self.registry.transaction() as db:
                study = db.execute('SELECT * FROM studies WHERE study_uid=?', (uid,)).fetchone()
                if not study: return {'error': 'study not found'}, 404
                if not db.execute('SELECT 1 FROM assessments WHERE study_uid=?', (uid,)).fetchone():
                    return {'error': 'confirm_all_first'}, 409
                version = db.execute('SELECT COALESCE(MAX(version),0)+1 FROM reports WHERE study_uid=? AND kind=?', (uid, args['kind'])).fetchone()[0]
                rid = uuid.uuid4().hex
                db.execute('INSERT INTO reports(report_id,study_uid,kind,markdown,version) VALUES (?,?,?,?,?)', (rid, uid, args['kind'], args['markdown'], version))
            self.status(uid, 'reported')
            report = self.registry.one('SELECT * FROM reports WHERE report_id=?', (rid,))
            self.events.emit('report_saved', report)
            return report, 200
        if name == 'set_priority':
            if args.get('priority') not in ('routine', 'elevated', 'urgent'):
                return {'error': 'invalid priority'}, 422
            with self.registry.transaction() as db:
                cur = db.execute('UPDATE studies SET priority=?,priority_reason=? WHERE study_uid=?', (args['priority'], args.get('reason'), uid))
                if not cur.rowcount: return {'error': 'study not found'}, 404
            self.events.emit('worklist_changed', {'reason': 'priority', 'study_uid': uid})
            return {'study_uid': uid, 'priority': args['priority'], 'reason': args.get('reason')}, 200
        if name == 'viewer_command':
            if args.get('command') not in ('show_nodule', 'compare_prior', 'reset_view', 'show_extras'):
                return {'error': 'invalid viewer command'}, 422
            if not self.registry.one('SELECT study_uid FROM studies WHERE study_uid=?', (uid,)):
                return {'error': 'study not found'}, 404
            self.events.emit('viewer_command', args)
            return args, 200
        if name == 'log_event':
            if not isinstance(args.get('message'), str) or not args['message'].strip():
                return {'error': 'message required'}, 422
            return self.log('agent_note', args['message'], uid), 200
        return {'error': 'unknown tool'}, 404

    def confirm(self, nid, body):
        rules_module()  # Refuse confirmation if the deterministic rule layer is unavailable.
        from sparkmd.rules.measurements import confirmed_measurement
        with self.registry.transaction() as db:
            row = db.execute('SELECT * FROM nodules WHERE nodule_id=?', (nid,)).fetchone()
            if not row: return {'error': 'nodule not found'}, 404
            uid = row['study_uid']
            if db.execute("SELECT 1 FROM reports WHERE study_uid=? AND status='approved'", (uid,)).fetchone():
                return {'error': 'approved study is immutable'}, 409
            try:
                long = float(body['long_mm'])
                short = float(body.get('short_mm', row['proposed_short_mm'] if row['proposed_short_mm'] is not None else long))
                by = body['by'].strip()
                measurement = confirmed_measurement(long, short)
                if not by:
                    raise ValueError()
            except (KeyError, TypeError, ValueError, AttributeError):
                return {'error': 'require 0 < short_mm <= long_mm <= 100 and by'}, 422
            mean = measurement['mean_mm']
            edited = long != row['proposed_long_mm'] or short != row['proposed_short_mm']
            db.execute('''UPDATE nodules SET long_mm=?,short_mm=?,mean_mm=?,volume_mm3=?,confirmed_by=?,confirmed_at=?,edited=? WHERE nodule_id=?''',
                       (long, short, mean, measurement['volume_mm3'], by, now(), int(edited), nid))
            # Changing confirmed inputs invalidates all downstream draft assessments/reports.
            study = db.execute('SELECT * FROM studies WHERE study_uid=?', (uid,)).fetchone()
            affected = db.execute('SELECT study_uid FROM studies WHERE patient_id=? AND rank>=? ORDER BY rank', (study['patient_id'], study['rank'])).fetchall()
            for downstream in affected:
                target = downstream['study_uid']
                if db.execute("SELECT 1 FROM reports WHERE study_uid=? AND status='approved'", (target,)).fetchone():
                    raise ValueError('a downstream approved report prevents measurement edits')
                db.execute('DELETE FROM reports WHERE study_uid=?', (target,))
                db.execute('DELETE FROM assessments WHERE study_uid=?', (target,))
        self.log('system', f'Confirmed by {by}; deterministic assessment recomputed before drafting reports', uid)
        for downstream in affected:
            target = downstream['study_uid']
            if self.registry.one('SELECT 1 FROM nodules WHERE study_uid=?', (target,)) and recompute(self, target):
                self.trigger(target, confirmed=True)
        return findings(self, uid, False)

    def approve(self, rid, body):
        with self.registry.transaction() as db:
            row = db.execute('SELECT * FROM reports WHERE report_id=?', (rid,)).fetchone()
            if not row: return {'error': 'report not found'}, 404
            report = dict(row)
            uid = report['study_uid']
            existing = db.execute('SELECT id FROM outbox WHERE report_id=?', (rid,)).fetchone()
            if report['status'] == 'approved':
                return {'report': report, 'outbox_id': existing['id'] if existing else None, 'already_approved': True}, 409
            if db.execute('SELECT 1 FROM nodules WHERE study_uid=? AND confirmed_at IS NULL', (uid,)).fetchone() or not db.execute('SELECT 1 FROM assessments WHERE study_uid=?', (uid,)).fetchone():
                return {'error': 'confirm_all_first', 'already_approved': False}, 409
            latest = db.execute('SELECT MAX(version) FROM reports WHERE study_uid=? AND kind=?', (uid, report['kind'])).fetchone()[0]
            if latest != report['version']: return {'error': 'superseded report'}, 409
            approver = body.get('approver')
            if not isinstance(approver, str) or not approver.strip(): return {'error': 'approver required'}, 422
            report.update(status='approved', approved_by=approver.strip(), approved_at=now())
            outbox_id = None
            if report['kind'] == 'pcp_letter':
                cur = db.execute('INSERT INTO outbox(ts,report_id,recipient,payload_json) VALUES (?,?,?,?)', (now(), rid, 'Primary care physician', json.dumps(report)))
                outbox_id = cur.lastrowid
                # Atomic file replacement; DB transaction rolls back if delivery cannot be written.
                for extension, content in [('json', json.dumps(report, indent=2)), ('html', '<!doctype html><meta charset="utf-8"><pre>'+html.escape(report['markdown'])+'</pre>')]:
                    target = self.config.home/'outbox'/f'{outbox_id}.{extension}'
                    temporary = target.with_suffix('.tmp')
                    temporary.write_text(content)
                    temporary.replace(target)
            db.execute('UPDATE reports SET status=?,approved_by=?,approved_at=? WHERE report_id=?', ('approved', report['approved_by'], report['approved_at'], rid))
            pending = db.execute('''SELECT 1 FROM reports r WHERE study_uid=? AND status!='approved' AND version=(
                SELECT MAX(rr.version) FROM reports rr WHERE rr.study_uid=r.study_uid AND rr.kind=r.kind) LIMIT 1''', (uid,)).fetchone()
        if not pending:
            self.status(uid, 'approved')
        if outbox_id is not None:
            study = self.registry.one('SELECT patient_id FROM studies WHERE study_uid=?', (uid,))
            self.events.emit('outbox_delivered', {'outbox_id': outbox_id, 'report_id': rid, 'study_uid': uid, 'patient_id': study['patient_id'], 'recipient': 'Primary care physician', 'subject': 'Lung CT screening follow-up'})
        return {'report': report, 'outbox_id': outbox_id, 'already_approved': False}, 200
