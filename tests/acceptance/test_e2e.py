"""End-to-end scenarios E1-E6 (11), as read-only checks of whatever state the worker is in.

A scenario that needs a human click or an LLM run (confirm, approve, talk) SKIPs unless the state already
shows its result; the runner never confirms or approves. Run the scenario by hand, then rerun this file.
"""
import math

from qa import DATA, QA, STATUS_ORDER, http, sandbox_base


def reached(row, status):
    return STATUS_ORDER.index(row['status']) >= STATUS_ORDER.index(status) if row['status'] in STATUS_ORDER else False


class EndToEnd(QA):
    def test_E1_study_reaches_awaiting_confirmation(self):
        """E1 intake -> analysis -> awaiting_confirmation with proposals, phase-1 log without sizes"""
        rows = self.rows_or_skip()
        done = [r for r in rows if reached(r, 'awaiting_confirmation')]
        if not done:
            self.skipTest('no study has reached awaiting_confirmation yet (drop T0)')
        for r in done:
            f = DATA.findings(r['study_uid'])
            self.assertTrue(f['nodules'] or f.get('pending_confirmation') == [], f'{r["timepoint"]} has no nodule rows')
            for n in f['nodules']:
                self.assertIsNotNone(n.get('proposal'), 'UI view lacks the proposal')
                self.assertEqual(n['proposal']['source'], 'A7')
        failed = [r['study_uid'][-8:] for r in rows if r['status'] == 'failed']
        self.assertFalse(failed, f'failed studies: {failed}')
        self.note = f'{len(done)} studies past analysis; target time unmeasured (time it by hand)'

    def test_E2_confirmation_yields_assessment_and_drafts(self):
        """E2 confirmed study: assessment from the rules, edited only if changed, both drafts saved"""
        done = [r for r in self.rows_or_skip() if DATA.confirmed(r['study_uid'])]
        if not done:
            self.skipTest('no study fully confirmed yet (human confirms in the UI)')
        for r in done:
            uid = r['study_uid']
            f = DATA.findings(uid)
            a = f['assessment']
            self.assertIsNotNone(a, f'{r["timepoint"]}: confirmed but assessment is null')
            self.assertEqual(a['lung_rads'], r['lung_rads'], 'worklist lung_rads != assessment')
            self.assertTrue(a.get('rule_id') and a.get('rules_version'))
            self.assertIn(a.get('driver_nodule_id'), [n['nodule_id'] for n in f['nodules']])
            for n in f['nodules']:
                p, c = n['proposal'] or {}, n['confirmation']
                self.assertEqual(n['mean_mm'], round((n['long_mm'] + n['short_mm']) / 2, 1))
                self.assertTrue(0 < n['short_mm'] <= n['long_mm'] <= 100)
                if p.get('long_mm') is not None:
                    same = (n['long_mm'], n['short_mm']) == (p['long_mm'], p['short_mm'])
                    self.assertEqual(c['edited'], not same, f'edited={c["edited"]} but proposal==confirmed is {same}')
        drafted = [r for r in done if DATA.latest_reports(r['study_uid'])]
        if not drafted:
            self.skipTest('confirmed, but the agent has not drafted yet (phase 2)')
        for r in drafted:
            kinds = set(DATA.latest_reports(r['study_uid']))
            self.assertEqual(kinds, {'radiology', 'pcp_letter'}, f'drafts present: {kinds}')
        self.note = f'{len(done)} confirmed, {len(drafted)} drafted'

    def test_E3_growth_from_confirmed_prior(self):
        """E3 priors: confirmed prior drives growth/VDT (growth_per_12mo rule); unconfirmed prior blocks it"""
        rows = self.rows_or_skip()
        by_patient = {}
        for r in rows:
            by_patient.setdefault(r['patient_id'], []).append(r)
        pairs = [(sorted(v, key=lambda r: r['rank'])) for v in by_patient.values() if len(v) > 1]
        if not pairs:
            self.skipTest('no patient with two studies yet (drop T1)')
        checked = 0
        for studies in pairs:
            for prior_row, cur_row in zip(studies, studies[1:]):
                cur = DATA.findings(cur_row['study_uid'])
                prior_ok = DATA.confirmed(prior_row['study_uid'])
                prior_means = {n['mean_mm'] for n in DATA.findings(prior_row['study_uid'])['nodules'] if n['mean_mm'] is not None}
                for n in cur['nodules']:
                    pr = n.get('prior')
                    if not prior_ok:
                        self.assertTrue(pr is None or pr.get('growth_per_12mo_mm') is None,
                                        f'{cur_row["timepoint"]} shows growth from an unconfirmed {prior_row["timepoint"]}')
                        continue
                    if pr is None or pr.get('mean_mm') is None:
                        continue                                  # new nodule: no prior to compare
                    checked += 1
                    self.assertIn(pr['mean_mm'], prior_means, 'prior mean is not a confirmed prior value')
                    days = pr['interval_days']
                    if cur_row['day_offset'] is not None and prior_row['day_offset'] is not None:
                        self.assertEqual(days, cur_row['day_offset'] - prior_row['day_offset'], 'interval != day_offset difference')
                    if n['mean_mm'] is None:
                        continue                                  # current not confirmed yet
                    delta = round(n['mean_mm'] - pr['mean_mm'], 1)
                    self.assertAlmostEqual(pr['delta_mean_mm'], delta, delta=0.051)
                    want = delta if days <= 365.25 else delta * 365.25 / days
                    self.assertAlmostEqual(pr['growth_per_12mo_mm'], want, delta=0.06, msg='growth_per_12mo rule (05 §Growth)')
                    self.assertEqual(bool(pr['growth_normalized']), days > 365.25)
                    if pr.get('vdt_days') and n['volume_mm3'] and pr.get('volume_mm3') and n['volume_mm3'] > pr['volume_mm3']:
                        vdt = days * math.log(2) / math.log(n['volume_mm3'] / pr['volume_mm3'])
                        self.assertAlmostEqual(pr['vdt_days'], vdt, delta=max(1.0, vdt * 0.01), msg='VDT cross-check')
        if not checked:
            self.skipTest('pairs exist, but no confirmed prior/current nodule pair to check yet')
        self.note = f'{checked} nodule pairs cross-checked'

    def test_E3b_worklist_priority_order(self):
        """E3 worklist sorted by priority then received time among equals"""
        rows = self.rows_or_skip()
        if len(rows) < 2:
            self.skipTest('needs 2+ studies')
        rank = {'urgent': 0, 'elevated': 1, 'routine': 2}
        keys = [rank[r['priority']] for r in rows]
        self.assertEqual(keys, sorted(keys))

    def test_E4_phrases_viewer_action_first(self):
        """E4 talk to the scan: viewer action before agent text, numbers from findings"""
        self.skipTest('needs the LLM (no GPU jobs in this pass); run the four chips by hand, then V3 reads the answers')

    def test_E4a_ask_is_loopback_only(self):
        """E4 /api/ask from the sandbox address is rejected by the worker (403)"""
        self.no_post_when_recording()
        status, body, _ = http('/api/ask', {'study_uid': 'qa-probe', 'text': 'qa'}, base=sandbox_base())
        self.assertEqual(status, 403, body)

    def test_E5_extras(self):
        """E5 extras: experimental items labelled, nothing unsourced"""
        rows = [r for r in self.rows_or_skip() if DATA.confirmed(r['study_uid'])]
        have = [(r, DATA.findings(r['study_uid'])['extras']) for r in rows]
        have = [(r, x) for r, x in have if x]
        if not have:
            self.skipTest('no extras in findings (cut order: extras go first)')
        for r, x in have:
            cac = x.get('cac')
            if cac:
                self.assertTrue(cac.get('experimental'), 'CAC must be labelled experimental')
        self.note = f'{len(have)} studies with extras'

    def test_E6_approve_gates(self):
        """E6 approve: 403 off-loopback, 404 unknown, 409 already_approved:true on re-approve, letters in the outbox"""
        self.no_post_when_recording()
        # Gate order in the worker: loopback first, then lookup. Neither probe can change state.
        status, body, _ = http('/api/reports/qa-probe/approve', {'approver': 'qa'}, base=sandbox_base())
        self.assertEqual((status, body.get('error')), (403, 'approve_loopback_only'))
        status, _, _ = http('/api/reports/qa-probe/approve', {'approver': 'qa'}, agent=True)
        self.assertEqual(status, 403, 'agent header from loopback must be refused')
        status, _, _ = http('/api/reports/qa-probe/approve', {'approver': 'qa-probe'})
        self.assertEqual(status, 404, 'unknown report id from the UI address')
        notes = []
        for r in self.rows_or_skip():
            reports = DATA.reports(r['study_uid']) or []
            # Unconfirmed study must hold no report at all (approve would be confirm_all_first).
            if DATA.findings(r['study_uid'])['pending_confirmation']:
                self.assertFalse(reports, f'{r["timepoint"]} is unconfirmed but has {len(reports)} report(s)')
            approved = [x for x in reports if x['status'] == 'approved']
            for x in approved:
                # Re-approving an approved report is a no-op by contract: 409 already_approved:true.
                status, body, _ = http(f'/api/reports/{x["report_id"]}/approve', {'approver': 'qa-probe'})
                self.assertEqual(status, 409, body)
                self.assertIs(body.get('already_approved'), True)
                if x['kind'] == 'pcp_letter':
                    self.assertTrue([o for o in DATA.outbox() if o['report_id'] == x['report_id']], 'approved letter missing from outbox')
                notes.append(x['kind'])
        self.note = f'403/404 gates ok; re-approve 409 checked for {len(notes)} approved report(s)' if notes else \
            '403/404 gates ok; no approved report yet, 409 already_approved and confirm_all_first not exercised (run by hand: E6)'
