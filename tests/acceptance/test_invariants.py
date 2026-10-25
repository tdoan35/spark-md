"""Invariants V1-V8 (11), checked through the REST API and /api/agent-log only (never the UI, never the DB).

V3 is the weakest check: a FAIL there means "review the printed numbers", never loosen it silently.
"""
import re

from qa import (DATA, QA, MM, allowed_numbers, categories, recording, sandbox_base, sandbox_checks, http, ts,
                unlisted_numbers)


class Invariants(QA):
    def _notes(self, uid, before=None):
        """agent_note rows for a study, optionally only those earlier than `before` (datetime)."""
        rows = [e for e in DATA.log() if e['study_uid'] == uid and e['source'] == 'agent_note']
        return [e for e in rows if before is None or ts(e['ts']) < before]

    def test_V1_report_category_equals_assessment(self):
        """V1 category in the latest reports == assessments.lung_rads"""
        checked = 0
        for r in self.rows_or_skip():
            reports = DATA.latest_reports(r['study_uid'])
            if not reports:
                continue
            a = DATA.findings(r['study_uid'])['assessment']
            self.assertIsNotNone(a, f'{r["timepoint"]}: report exists but there is no assessment')
            for kind, rep in reports.items():
                found = set(categories(rep['markdown']))
                self.assertEqual(found - {a['lung_rads'].upper()}, set(), f'{r["timepoint"]} {kind} v{rep["version"]} says {found}, assessment is {a["lung_rads"]}')
                if kind == 'radiology':
                    self.assertTrue(found, f'{r["timepoint"]} radiology report names no Lung-RADS category')
                checked += 1
        if not checked:
            self.skipTest('no report drafted yet')
        self.note = f'{checked} reports (latest version per kind)'

    def test_V2_nothing_before_confirmation(self):
        """V2 unconfirmed study: no assessment/size/growth/report, none in agent view, no sizes in phase-1 notes"""
        pending, texts = 0, 0
        for r in self.rows_or_skip():
            uid = r['study_uid']
            f = DATA.findings(uid)
            if f['pending_confirmation']:
                pending += 1
                self.assertIsNone(f['assessment'], f'{r["timepoint"]}: assessment before confirmation')
                self.assertIsNone(r['lung_rads'], 'worklist shows a category before confirmation')
                self.assertFalse(DATA.reports(uid), 'report exists before confirmation')
                for n in f['nodules']:
                    if not n['confirmation']['confirmed']:
                        for k in ('long_mm', 'short_mm', 'mean_mm', 'volume_mm3'):
                            self.assertIsNone(n[k], f'unconfirmed nodule has {k}')
                        self.assertTrue(not n.get('prior') or all(n['prior'].get(k) is None for k in ('delta_mean_mm', 'growth_per_12mo_mm', 'vdt_days')),
                                        'unconfirmed nodule carries growth')
                if not recording():                              # agent-header GET writes a log row
                    a = DATA.agent_findings(uid)
                    self.assertIsNone(a['assessment'])
                    for n in a['nodules']:
                        leaked = {'proposal', 'long_mm', 'short_mm', 'mean_mm', 'volume_mm3'} & set(n)
                        self.assertFalse(leaked, f'agent view leaks {leaked}')
            confirmed_at = [ts(n['confirmation']['at']) for n in f['nodules'] if n['confirmation']['at']]
            cutoff = min(confirmed_at) if confirmed_at else None
            for e in self._notes(uid, cutoff):
                texts += 1
                self.assertFalse(MM.findall(e['message']), f'phase-1 note has a size: {e["message"][:100]!r}')
                self.assertFalse(categories(e['message']), f'phase-1 note has a category: {e["message"][:100]!r}')
        if not pending and not texts:
            self.skipTest('no unconfirmed study and no phase-1 notes to check')
        self.note = f'{pending} unconfirmed studies, {texts} phase-1 notes scanned'

    def test_V3_agent_numbers_in_findings(self):
        """V3 every number in reports + agent notes is in that study's findings (REVIEW on FAIL)"""
        checked, flagged = 0, []
        for r in self.rows_or_skip():
            uid = r['study_uid']
            if not DATA.confirmed(uid):
                continue
            allowed = allowed_numbers(DATA.findings(uid), DATA.study(uid))
            texts = [(f'{k} v{x["version"]}', x['markdown']) for k, x in DATA.latest_reports(uid).items()]
            cutoff = min(ts(n['confirmation']['at']) for n in DATA.findings(uid)['nodules'])
            texts += [(f'note#{e["id"]}', e['message']) for e in self._notes(uid) if ts(e['ts']) >= cutoff]
            for label, text in texts:
                checked += 1
                bad = unlisted_numbers(text, allowed)
                if bad:
                    flagged.append(f'{r["timepoint"]} {label}: {sorted(set(bad))}')
        if not checked:
            self.skipTest('no confirmed study with agent text yet')
        self.assertFalse(flagged, 'REVIEW unlisted numbers -> ' + '; '.join(flagged))
        self.note = f'{checked} texts'

    def test_V4_gates_refuse_non_ui_callers(self):
        """V4 confirm/approve -> 403 from 10.77.0.1 and with the agent header; sandbox policy 403s"""
        self.no_post_when_recording()
        body = {'long_mm': 5, 'short_mm': 5, 'by': 'qa-probe'}
        for who, kw in (('sandbox address', {'base': sandbox_base()}), ('agent header', {'agent': True})):
            s, b, _ = http('/api/nodules/qa-probe/confirm', body, **kw)
            self.assertEqual((s, b.get('error')), (403, 'confirm_loopback_only'), f'confirm via {who}')
            s, b, _ = http('/api/reports/qa-probe/approve', {'approver': 'qa-probe'}, **kw)
            self.assertEqual((s, b.get('error')), (403, 'approve_loopback_only'), f'approve via {who}')
        sbx = sandbox_checks()
        if isinstance(sbx, str):
            self.note = f'worker gates ok; sandbox policy part SKIPPED ({sbx})'
            return
        for check in ('A4', 'A5'):
            self.assertIn(check, sbx)
            self.assertEqual(sbx[check][0], 'PASS', sbx[check][1])
        self.note = 'worker gates + sandbox policy_denied (A4, A5)'

    def test_V5_sandbox_reaches_only_allowed(self):
        """V5 sandbox: unlisted path, internet and npm denied (acceptance.sh A6-A8)"""
        sbx = sandbox_checks()
        if isinstance(sbx, str):
            self.skipTest(sbx)
        for check in ('A6', 'A7', 'A8'):
            self.assertIn(check, sbx)
            self.assertEqual(sbx[check][0], 'PASS', sbx[check][1])

    def test_V6_ui_external_requests(self):
        """V6 UI makes no non-loopback request over a full flow"""
        self.skipTest('needs the Electron CDP flow: node ui/tools/smoke.mjs (S06 does a static CDN scan of the served bundle)')

    def test_V7_human_by(self):
        """V7 confirmed_by / approved_by are humans (never agent; never demo-harness when recording)"""
        rec = recording()
        seen, harness = 0, 0
        for r in self.rows_or_skip():
            f = DATA.findings(r['study_uid'])
            who = [n['confirmation']['by'] for n in f['nodules'] if n['confirmation']['confirmed']]
            who += [x['approved_by'] for x in DATA.reports(r['study_uid']) or [] if x['status'] == 'approved']
            for w in who:
                seen += 1
                self.assertTrue(w and w.strip(), 'empty by')
                self.assertNotRegex(w.lower(), r'^agent|openclaw', f'by={w!r} looks like the agent')
                if 'demo-harness' in w.lower():
                    harness += 1
                    self.assertFalse(rec, 'demo-harness confirmed/approved while recording')
        if not seen:
            self.skipTest('nothing confirmed or approved yet')
        self.note = f'{seen} actors, {harness} demo-harness' + ('' if not harness else ' (dry-run aid, refused when recording)')

    def test_V8_cached_is_labelled(self):
        """V8 cached mode has a log line (banner state is demo_state.mode)"""
        state = DATA.demo()
        cached_logged = [e for e in DATA.log() if re.search(r'\bcached\b', e['message'], re.I)]
        if state['mode'] != 'cached' and not cached_logged:
            self.skipTest('no cached run (mode=live, no cached log lines)')
        self.assertTrue(cached_logged, 'mode=cached but no log line says so')
        if state['replaying']:
            self.assertEqual(state['mode'], 'cached' if cached_logged else state['mode'])
        self.note = f'{len(cached_logged)} cached log lines'
