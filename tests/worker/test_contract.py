"""Run with stdlib unittest against a live SPARKMD_FAKE_SEED/IMAGING worker.
SPARKMD_TEST_URL defaults to http://127.0.0.1:8100; use an isolated SPARKMD_HOME.
"""
import concurrent.futures
import json
import os
import threading
import unittest
import urllib.error
import urllib.request

BASE = os.environ.get('SPARKMD_TEST_URL', 'http://127.0.0.1:8100')


def request(path, body=None, *, agent=False, method=None):
    headers = {'Content-Type': 'application/json'}
    if agent: headers['X-SparkMD-Caller'] = 'agent'
    req = urllib.request.Request(BASE+path, None if body is None else json.dumps(body).encode(), headers, method=method)
    try:
        response = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        raw = response.read()
        return response.status, json.loads(raw) if raw else None, dict(response.headers)


def mcp(name, args):
    status, body, _ = request('/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': args}})
    assert status == 200, body
    result = body['result']
    return json.loads(result['content'][0]['text']), result['isError']


class WorkerContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        status, body, _ = request('/api/health')
        if status != 200 or not body.get('placeholder'):
            raise unittest.SkipTest('requires an isolated fake imaging worker')

    def setUp(self):
        self.assertEqual(request('/api/demo/reset', {})[0], 200)

    def analyze(self, uid):
        self.assertEqual(request(f'/api/studies/{uid}/select-series', {'series_uid': uid+'-soft', 'reason': 'soft thin CT'})[0], 200)
        status, result, _ = request(f'/api/studies/{uid}/analyze', {'wait_s': 5})
        self.assertEqual(status, 200)
        self.assertEqual(result['state'], 'done', result)
        self.assertEqual(result['study_status'], 'awaiting_confirmation')
        return result

    def confirm(self, uid, long, short):
        status, body, _ = request(f'/api/nodules/{uid}-N1/confirm', {'long_mm': long, 'short_mm': short, 'by': 'Dr. Joyce (test)'})
        self.assertEqual(status, 200, body)
        return body

    def test_mcp_protocol_and_tool_safety(self):
        status, body, headers = request('/mcp', {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26'}})
        self.assertEqual(status, 200)
        self.assertTrue(headers.get('mcp-session-id') or headers.get('Mcp-Session-Id'))
        self.assertEqual(body['result']['protocolVersion'], '2025-03-26')
        self.assertEqual(request('/mcp', {'jsonrpc': '2.0', 'method': 'notifications/initialized'})[0], 202)
        status, body, _ = request('/mcp', {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        names = {tool['name'] for tool in body['result']['tools']}
        self.assertEqual(len(names), 9)
        self.assertFalse(any('confirm' in n or 'approv' in n for n in names))
        self.assertEqual(request('/mcp')[0], 405)
        self.assertEqual(request('/mcp', method='DELETE')[0], 204)

    def test_selection_and_single_flight(self):
        result, error = mcp('run_analysis', {'study_uid': 'fixture-T0'})
        self.assertTrue(error)
        self.assertEqual(result['error'], 'select a series first')
        self.assertEqual(request('/api/studies/fixture-T0/select-series', {'series_uid': 'fixture-T0-sharp', 'reason': 'test'})[0], 422)
        self.assertEqual(request('/api/studies/fixture-T0/select-series', {'series_uid': 'fixture-T0-soft', 'reason': 'test'})[0], 200)
        with concurrent.futures.ThreadPoolExecutor() as pool:
            rest = pool.submit(request, '/api/studies/fixture-T0/analyze', {'wait_s': 5})
            tool = pool.submit(mcp, 'run_analysis', {'study_uid': 'fixture-T0'})
            a, b = rest.result()[1], tool.result()[0]
        self.assertEqual(a['job_id'], b['job_id'])
        self.assertEqual(a['state'], 'done')
        self.assertEqual(b['study_status'], 'awaiting_confirmation')

    def test_proposals_hidden_and_confirmation_gates(self):
        self.analyze('fixture-T0')
        ui = request('/api/studies/fixture-T0/findings')[1]
        agent = request('/api/studies/fixture-T0/findings', agent=True)[1]
        tool, error = mcp('get_findings', {'study_uid': 'fixture-T0'})
        self.assertFalse(error)
        self.assertEqual(agent, tool)
        self.assertIsNone(agent['assessment'])
        self.assertTrue(agent['pending_confirmation'])
        self.assertIn('proposal', ui['nodules'][0])
        for key in ('proposal', 'mean_mm', 'long_mm', 'short_mm', 'volume_mm3'):
            self.assertNotIn(key, agent['nodules'][0])
        self.assertEqual(request('/api/nodules/fixture-T0-N1/confirm', {'long_mm': 10, 'short_mm': 10, 'by': 'agent'}, agent=True)[0], 403)
        self.assertEqual(request('/api/reports/anything/approve', {'approver': 'agent'}, agent=True)[0], 403)
        self.assertEqual(request('/api/studies/fixture-T0/reports', {'kind': 'radiology', 'markdown': 'not yet'})[0], 409)
        for long, short in [(0, 0), (101, 10), (9, 10), (-1, -2)]:
            self.assertEqual(request('/api/nodules/fixture-T0-N1/confirm', {'long_mm': long, 'short_mm': short, 'by': 'test'})[0], 422)
        findings = self.confirm('fixture-T0', 11, 9)
        n = findings['nodules'][0]
        self.assertEqual(n['mean_mm'], 10)
        self.assertTrue(n['confirmation']['edited'])
        self.assertEqual(findings['assessment']['lung_rads'], '4A')
        self.assertEqual(findings['assessment']['rule_id'], 'S-BASE-8-15')
        self.assertEqual(findings['assessment']['driver_nodule_id'], 'fixture-T0-N1')

    def test_growth_from_confirmed_prior_and_edit_recomputes(self):
        self.analyze('fixture-T0')
        self.confirm('fixture-T0', 11, 9)
        self.analyze('fixture-T1')
        value = self.confirm('fixture-T1', 14, 14)
        prior = value['nodules'][0]['prior']
        self.assertEqual(prior['mean_mm'], 10)
        self.assertEqual(prior['delta_mean_mm'], 4)
        self.assertEqual(prior['interval_days'], 371)
        self.assertAlmostEqual(prior['growth_per_12mo_mm'], 4*365.25/371)
        self.assertTrue(prior['growth_normalized'])
        self.assertEqual(value['assessment']['lung_rads'], '4B')
        self.assertEqual(value['assessment']['rules_version'], 'lungrads-v2022')
        self.confirm('fixture-T0', 13, 13)
        changed = request('/api/studies/fixture-T1/findings')[1]
        self.assertEqual(changed['nodules'][0]['prior']['delta_mean_mm'], 1)
        self.assertFalse(changed['nodules'][0]['prior']['growing'])
        self.assertEqual(changed['assessment']['lung_rads'], '4A')

    def test_current_confirmation_waits_for_prior(self):
        self.analyze('fixture-T0')
        self.analyze('fixture-T1')
        current = self.confirm('fixture-T1', 14, 14)
        self.assertIsNone(current['assessment'])
        self.assertEqual(request('/api/studies/fixture-T1')[1]['status'], 'awaiting_confirmation')
        self.confirm('fixture-T0', 10, 10)
        self.assertEqual(request('/api/studies/fixture-T1/findings')[1]['assessment']['lung_rads'], '4B')

    def test_approve_outbox_sse_idempotency_and_agent_log(self):
        self.analyze('fixture-T0')
        self.confirm('fixture-T0', 11, 9)
        status, letter, _ = request('/api/studies/fixture-T0/reports', {'kind': 'pcp_letter', 'markdown': 'Lung-RADS 4A; mean 10.0 mm.'}, agent=True)
        self.assertEqual(status, 200)
        connected = threading.Event()
        delivered = []
        def subscriber():
            with urllib.request.urlopen(BASE+'/api/events', timeout=5) as response:
                connected.set()
                for raw in response:
                    line = raw.decode().strip()
                    if line == 'event: outbox_delivered':
                        delivered.append(True)
                        return
        thread = threading.Thread(target=subscriber, daemon=True)
        thread.start()
        self.assertTrue(connected.wait(3))
        status, approved, _ = request(f'/api/reports/{letter["report_id"]}/approve', {'approver': 'Dr. Joyce'})
        self.assertEqual(status, 200)
        self.assertFalse(approved['already_approved'])
        thread.join(2)
        self.assertEqual(delivered, [True])
        status, again, _ = request(f'/api/reports/{letter["report_id"]}/approve', {'approver': 'other'})
        self.assertEqual(status, 409)
        self.assertTrue(again['already_approved'])
        self.assertEqual(again['outbox_id'], approved['outbox_id'])
        self.assertEqual(again['report']['approved_by'], 'Dr. Joyce')
        self.assertEqual(len(request('/api/outbox')[1]), 1)
        self.assertEqual(request('/api/nodules/fixture-T0-N1/confirm', {'long_mm': 12, 'by': 'test'})[0], 409)
        mcp('get_study', {'study_uid': 'fixture-T0'})
        logs = request('/api/agent-log?study_uid=fixture-T0&limit=200')[1]
        self.assertTrue(any(e.get('tool') == 'get_study' for e in logs))
        self.assertTrue(any('POST /api/studies/' in e['message'] for e in logs))


if __name__ == '__main__':
    unittest.main()
