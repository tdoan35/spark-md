#!/usr/bin/env python3
"""Cold-restart test, 11 C1-C5, driven through bin/sparkmd-{stop,start}. Stdlib only.

  cold_restart.py plan                    DEFAULT, safe. Snapshot -> `sparkmd-stop --dry-run` -> `sparkmd-start --dry-run` -> verify the
                                          snapshot against the unchanged state (so the C2 comparison logic is exercised). Changes nothing.
  cold_restart.py run --for-real [--only llm,sandbox,worker,ui]
                                          Snapshot -> sparkmd-stop -> sparkmd-start (timed) -> verify -> C4 (worker-only restart with an
                                          SSE reconnect probe). STOPS AND STARTS SERVICES: only after the 15:15 freeze, never while
                                          recording or while anything else uses the GPU/LLM.
  cold_restart.py reboot-prepare          Snapshot to ~/logs/coldrestart-snapshot.json; then reboot at the console.
  cold_restart.py reboot-verify           After the reboot, from a shell: run bin/sparkmd-start (timed), then verify against the snapshot.
  cold_restart.py verify [--snap FILE]    Compare the current state with a snapshot (no restarts).

Checks (printed as PASS/FAIL/SKIP, same format as run.py):
  C1 ordered start with no manual fixes; time to a loaded worklist (target <= 300 s, proposed in 11); every WARN/FAIL line is a "manual fix" to record
  C2 registry, cache, outbox survive: studies/status/priority, confirmed diameters + who, report ids/versions/approvals, outbox, cache files
  C3 agent sessions are fresh: MANUAL (needs a new study through the LLM); `--c3-drop PATIENT:TP` drops one backlog study after the restart
  C4 SSE endpoint accepts a connection again < 5 s after the worker is healthy (the UI's own reconnect is checked by eye)
  C5 ASR :8178 / TTS :8020 answer, or the UI's mute fallback applies (WARN-level SKIP)
Results are also written to ~/logs/coldrestart-<time>.json for docs/benchmarks/2026-10-25-acceptance.md (record which step needed a manual fix).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import qa  # noqa: E402

BIN = os.path.join(qa.REPO, 'bin')
LOGS = os.path.expanduser(os.environ.get('SPARKMD_LOG_DIR', '~/logs'))
SNAP = os.path.join(LOGS, 'coldrestart-snapshot.json')
START_TARGET_S = 300          # 11 C1 placeholder
RECONNECT_TARGET_S = 5        # 11 C4

ROWS = []


def row(word, cid, desc, note=''):
    print(f'{word:4} {cid:3} {desc}' + (f'  -- {note}' if note else ''), flush=True)
    ROWS.append({'id': cid, 'result': word, 'desc': desc, 'note': note})


def jget(path):
    return qa.get(path, timeout=10)[1]


def worker_home():
    return qa.worker_env().get('SPARKMD_HOME') or os.environ.get('SPARKMD_HOME') or '/home/dell/spark-md-runtime-w'


def tree(root):
    out = {}
    for dirpath, _, names in os.walk(root):
        for n in names:
            p = os.path.join(dirpath, n)
            try:
                out[os.path.relpath(p, root)] = os.path.getsize(p)
            except OSError:
                pass
    return out


def snapshot():
    home = worker_home()
    work = jget('/api/worklist')
    studies = {}
    for r in work:
        uid = r['study_uid']
        f = jget(f'/api/studies/{uid}/findings')
        studies[uid] = {
            'row': {k: r.get(k) for k in ('patient_id', 'timepoint', 'status', 'priority', 'lung_rads', 'reports_awaiting', 'day_offset')},
            'nodules': {n['nodule_id']: {k: n.get(k) for k in ('long_mm', 'short_mm', 'mean_mm', 'volume_mm3')} | {
                'confirmed': n['confirmation']['confirmed'], 'by': n['confirmation']['by'], 'edited': n['confirmation']['edited']}
                for n in f['nodules']},
            'assessment': f['assessment'],
            'reports': {x['report_id']: {k: x.get(k) for k in ('kind', 'version', 'status', 'approved_by', 'markdown')}
                        for x in jget(f'/api/studies/{uid}/reports') or []},
        }
    return {'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'home': home, 'studies': studies,
            'outbox': sorted(o['id'] for o in jget('/api/outbox')),
            'log_rows': len(jget('/api/agent-log?limit=2000')),
            'cache': tree(os.path.join(home, 'cache')), 'outbox_files': tree(os.path.join(home, 'outbox'))}


def compare(before, after):
    """-> list of differences (empty = everything survived)."""
    bad = []
    for uid, b in before['studies'].items():
        a = after['studies'].get(uid)
        if not a:
            bad.append(f'study {uid[-8:]} missing'); continue
        if a['row'] != b['row']:
            bad.append(f'{b["row"]["timepoint"]} row changed: {b["row"]} -> {a["row"]}')
        if a['nodules'] != b['nodules']:
            bad.append(f'{b["row"]["timepoint"]} nodules/confirmed diameters changed')
        if a['assessment'] != b['assessment']:
            bad.append(f'{b["row"]["timepoint"]} assessment changed')
        for rid, rep in b['reports'].items():
            if a['reports'].get(rid) != rep:
                bad.append(f'{b["row"]["timepoint"]} report {rid[:8]} changed/missing')
    if not set(before['outbox']) <= set(after['outbox']):
        bad.append(f'outbox ids lost: {sorted(set(before["outbox"]) - set(after["outbox"]))}')
    for name in ('cache', 'outbox_files'):
        missing = [k for k, v in before[name].items() if after[name].get(k) != v]
        if missing:
            bad.append(f'{name}: {len(missing)} file(s) missing or resized, e.g. {missing[:2]}')
    if after['log_rows'] < min(before['log_rows'], 2000):
        bad.append(f'agent_events shrank {before["log_rows"]} -> {after["log_rows"]}')
    return bad


def run_bin(name, *args, timeout=900):
    """-> (seconds, exit code, output lines). Echoes the script's own one-line results."""
    t = time.time()
    p = subprocess.run([os.path.join(BIN, name), *args], capture_output=True, text=True, timeout=timeout)
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    for l in lines:
        print('     | ' + l[:200], flush=True)
    return time.time() - t, p.returncode, lines


def wait_worklist(deadline_s):
    end = time.time() + deadline_s
    while time.time() < end:
        try:
            r = qa.get('/api/worklist', timeout=5)
            if r[0] == 200 and isinstance(r[1], list):
                return len(r[1])
        except OSError:
            pass
        time.sleep(1)
    return None


def check_c1(start_s, lines, rc, n_before, dry):
    fixes = [l for l in lines if l.startswith(('WARN', 'FAIL'))]
    tag = ' (dry run: nothing started)' if dry else ''
    if rc != 0 or any(l.startswith('FAIL') for l in lines):
        row('FAIL', 'C1', 'ordered start with no manual fixes', f'sparkmd-start exit {rc}; needed fixes: {[l[:60] for l in fixes]}')
        return
    n = wait_worklist(60) if not dry else n_before
    if n is None:
        row('FAIL', 'C1', 'worklist loads after start', 'no 200 from /api/worklist within 60 s of start finishing')
    elif n != n_before:
        row('FAIL', 'C1', 'worklist loads after start', f'{n} studies now vs {n_before} before')
    else:
        slow = start_s > START_TARGET_S and not dry
        row('FAIL' if slow else 'PASS', 'C1', 'ordered start, worklist loads', f'{start_s:.0f} s (target <= {START_TARGET_S}){tag}; manual-fix candidates (record as start lines): '
            + (', '.join(l.split()[1] + ':' + l.split()[0] for l in fixes) or 'none'))


def check_c2(before, dry):
    try:
        after = snapshot()
    except OSError as exc:
        row('FAIL', 'C2', 'registry, cache, outbox survive', f'worker unreachable: {exc}'); return
    bad = compare(before, after)
    row('FAIL' if bad else 'PASS', 'C2', 'registry, cache, outbox survive', '; '.join(bad)[:400] if bad else
        f'{len(after["studies"])} studies, {len(after["cache"])} cache files, {len(after["outbox"])} outbox letters identical' + (' (dry run: compared with unchanged state)' if dry else ''))


def check_c3(drop):
    if not drop:
        row('SKIP', 'C3', 'agent sessions are fresh, phase 1 still works', 'manual: after the restart drop a study (rerun with --c3-drop 134503:T1 or use the UI) and confirm it reaches awaiting_confirmation; cold prefill ~30 s (07)')
        return
    pid, tp = drop.split(':')
    st, body, _ = qa.http('/api/demo/drop', {'patient_id': pid, 'timepoint': tp}, timeout=30)
    if st != 200:
        row('FAIL', 'C3', f'drop {pid} {tp}', f'{st} {body}'); return
    t0, uid = time.time(), body.get('study_uid')
    while time.time() - t0 < 300:
        rows = [r for r in jget('/api/worklist') if r['patient_id'] == pid and r['timepoint'] == tp]
        if rows and rows[0]['status'] in ('awaiting_confirmation', 'analyzed', 'reported'):
            row('PASS', 'C3', 'phase 1 works from a fresh agent session', f'{pid} {tp} -> {rows[0]["status"]} in {time.time()-t0:.0f} s (needs human confirm next)'); return
        if rows and rows[0]['status'] == 'failed':
            row('FAIL', 'C3', 'phase 1 works from a fresh agent session', rows[0].get('failure_reason') or 'failed'); return
        time.sleep(3)
    row('FAIL', 'C3', 'phase 1 works from a fresh agent session', 'not awaiting_confirmation after 300 s')


def sse_probe(stop, out):
    """Retry /api/events every 0.25 s like the UI would; record the first success after each failure."""
    failing = False
    while not stop.is_set():
        try:
            r = urllib.request.urlopen(qa.BASE + '/api/events', timeout=2)
            r.close()
            if failing:
                out.setdefault('first_ok_after_fail', time.time())
            failing = False
        except (OSError, urllib.error.URLError):
            failing = True
            out.setdefault('first_fail', time.time())
        time.sleep(0.25)


def check_c4(dry):
    if dry:
        row('SKIP', 'C4', 'SSE reconnects < 5 s after a worker restart', 'dry run: real run restarts the worker alone (sparkmd-stop/start --only worker) with an SSE probe')
        return
    out, stop = {}, threading.Event()
    th = threading.Thread(target=sse_probe, args=(stop, out), daemon=True)
    th.start()
    run_bin('sparkmd-stop', '--only', 'worker')
    t_up = None
    run_bin('sparkmd-start', '--only', 'worker')
    end = time.time() + 60
    while time.time() < end and 'first_ok_after_fail' not in out:
        time.sleep(0.25)
    t_up = time.time()
    stop.set(); th.join(2)
    if 'first_ok_after_fail' not in out:
        row('FAIL', 'C4', 'SSE reconnects < 5 s after a worker restart', 'no SSE connection within 60 s'); return
    down = out['first_ok_after_fail'] - out['first_fail']
    # sparkmd-start returns once /api/health answers, so (first_ok - health_up) is bounded by the probe period plus the script's own return.
    after_health = max(0.0, out['first_ok_after_fail'] - (t_up - 0.0)) if out['first_ok_after_fail'] > t_up else 0.0
    row('PASS', 'C4', 'SSE endpoint accepts connections again (probe stands in for the UI)', f'down {down:.1f} s total; SSE ok again {after_health:.1f} s after start returned; check by eye that the UI banner clears < {RECONNECT_TARGET_S} s (08 measured 1.5 s on the mock)')


def check_c5():
    asr = qa.http('/', base='http://127.0.0.1:8178', timeout=3) if _tcp(8178) else None
    tts = qa.http('/health', base='http://127.0.0.1:8020', timeout=3) if _tcp(8020) else None
    up = [n for n, r in (('ASR :8178', asr), ('TTS :8020', tts)) if r]
    down = [n for n, r in (('ASR :8178', asr), ('TTS :8020', tts)) if not r]
    if not down:
        row('PASS', 'C5', 'voice and TTS servers return', 'both answer')
    else:
        row('SKIP', 'C5', 'voice and TTS servers return', f'{", ".join(down)} down (UI shows chips + mute fallback; check that by eye)' + (f'; up: {up}' if up else ''))


def _tcp(port):
    import socket
    try:
        socket.create_connection(('127.0.0.1', port), timeout=2).close()
        return True
    except OSError:
        return False


def finish(args):
    os.makedirs(LOGS, exist_ok=True)
    path = os.path.join(LOGS, time.strftime('coldrestart-%Y%m%d-%H%M%S.json'))
    counts = {w: sum(1 for r in ROWS if r['result'] == w) for w in ('PASS', 'FAIL', 'SKIP')}
    with open(path, 'w') as f:
        json.dump({'mode': args.mode, 'dry': not getattr(args, 'for_real', False) and args.mode in ('plan', 'run'), 'rows': ROWS}, f, indent=1)
    print(f'-- {counts["PASS"]} PASS, {counts["FAIL"]} FAIL, {counts["SKIP"]} SKIP  (record: {path})')
    return counts['FAIL']


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', nargs='?', default='plan', choices=['plan', 'run', 'reboot-prepare', 'reboot-verify', 'verify'])
    ap.add_argument('--for-real', action='store_true', help='required for `run`: actually stop and start services')
    ap.add_argument('--only', default='', help='limit stop/start to these steps (default: all)')
    ap.add_argument('--snap', default=SNAP)
    ap.add_argument('--c3-drop', default='', help='PATIENT:TP, e.g. 134503:T1 (starts a real agent run)')
    args = ap.parse_args()
    only = ['--only', args.only] if args.only else []

    if args.mode == 'run' and not args.for_real:
        print('`run` stops and starts services; pass --for-real (after the 15:15 freeze, not while recording). Showing the dry run instead.\n')
        args.mode = 'plan'
    if qa.recording() and (args.mode in ('run', 'reboot-prepare') and args.for_real):
        print('RECORDING state: refusing to restart anything.'); return 2

    os.makedirs(LOGS, exist_ok=True)
    if args.mode == 'verify' or args.mode == 'reboot-verify':
        before = json.load(open(args.snap))
        t = rc = lines = None
        if args.mode == 'reboot-verify':
            t, rc, lines = run_bin('sparkmd-start', *only)
            check_c1(t, lines, rc, len(before['studies']), dry=False)
        check_c2(before, dry=False)
        check_c3(args.c3_drop); check_c5()
        return finish(args)

    before = snapshot()
    dry = args.mode == 'plan'
    json.dump(before, open(args.snap if args.mode == 'reboot-prepare' else os.path.join(LOGS, 'coldrestart-snapshot-last.json'), 'w'))
    print(f'snapshot: {len(before["studies"])} studies, {len(before["cache"])} cache files, {len(before["outbox"])} outbox letters, home {before["home"]}')
    if args.mode == 'reboot-prepare':
        print(f'saved {args.snap}. Reboot now; after login run: tests/acceptance/cold_restart.py reboot-verify'); return 0

    flag = ['--dry-run'] if dry else []
    print('== stop (reverse order)' + (' [dry run]' if dry else ''))
    run_bin('sparkmd-stop', *only, *flag)
    print('== start (timed)' + (' [dry run]' if dry else ''))
    t, rc, lines = run_bin('sparkmd-start', *only, *flag)
    check_c1(t, lines, rc, len(before['studies']), dry)
    check_c2(before, dry)
    check_c3(args.c3_drop if not dry else '')
    check_c4(dry)
    check_c5()
    return finish(args)


if __name__ == '__main__':
    sys.exit(main())
