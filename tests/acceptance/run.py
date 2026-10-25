#!/usr/bin/env python3
"""Spark MD acceptance runner (11): black-box HTTP checks against the worker, stdlib unittest only.

  python3 tests/acceptance/run.py                 quick pass: smoke + E1-E6 + V1-V8 (default)
  python3 tests/acceptance/run.py --only V,S03    run groups (S, E, V) and/or single IDs
  python3 tests/acceptance/run.py --json out.json also write the rows (date, commit, base, results) for the 11 record
  SPARKMD_TEST_URL=http://127.0.0.1:8100          worker under test
  SPARKMD_QA_NO_SANDBOX=1                         skip the sandbox probes (agent/tests/acceptance.sh)

Read-only by default: never confirms or approves, and only GETs while the worker is in the recording state.
Each check prints PASS / FAIL / SKIP with its ID; exit code = number of FAILs.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import qa  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', default='', help='comma list of groups (S,E,V) or IDs (S03,V1)')
    ap.add_argument('--json', help='write results to this file')
    args = ap.parse_args()
    wanted = [w.strip().upper() for w in args.only.split(',') if w.strip()]

    suite = unittest.TestSuite()
    for t in unittest.defaultTestLoader.discover(HERE, pattern='test_*.py'):
        for case in t:
            for test in case:
                m = re.match(r'test_([A-Z])(\d+[a-z]?)_', test._testMethodName)
                tid = (m.group(1) + m.group(2)).upper() if m else ''
                if not wanted or any(tid == w or (len(w) == 1 and tid.startswith(w)) for w in wanted):
                    suite.addTest(test)
    suite._tests.sort(key=lambda t: (t._testMethodName[5], int(re.match(r'test_[A-Z](\d+)', t._testMethodName).group(1)), t._testMethodName))

    try:
        commit = subprocess.run(['git', '-C', qa.REPO, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = '?'
    state = 'RECORDING (GET-only)' if qa.recording() else 'normal'
    print(f'Spark MD acceptance, quick pass  base={qa.BASE}  commit={commit}  state={state}', flush=True)
    start = time.time()
    qa.Result.rows = []
    runner = unittest.TextTestRunner(resultclass=qa.Result, stream=open(os.devnull, 'w'), verbosity=0)
    result = runner.run(suite)
    counts = {w: sum(1 for r in qa.Result.rows if r['result'] == w) for w in ('PASS', 'FAIL', 'SKIP')}
    print(f'-- {counts["PASS"]} PASS, {counts["FAIL"]} FAIL, {counts["SKIP"]} SKIP in {time.time()-start:.1f}s '
          f'(not automated here: E7-E9, cold restart C1-C5, contention, air gap A1-A5, V6 CDP)')
    if args.json:
        with open(args.json, 'w') as out:
            json.dump({'date': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'commit': commit, 'base': qa.BASE, 'results': qa.Result.rows}, out, indent=1)
    return counts['FAIL'] or (0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    sys.exit(main())
