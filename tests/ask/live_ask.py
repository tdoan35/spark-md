"""Live /api/ask bench on the box (not a unit test): the 4 UI chip phrases against a real study.

Usage: python3 tests/ask/live_ask.py <study_uid> [base_url]
Per phrase: time to the viewer_command frame, first text delta and done; the answer; numbers not in findings.
Read-only: the agent may call get_findings / viewer_command; the Q&A skill forbids reports, priority and log_event.
"""
import json
import re
import sys
import time
import urllib.request

PHRASES = ['Show me the nodule', 'Compare it to last year', 'Why did you flag this?', 'Reset the view']  # ui chat-rail.tsx
NUM = re.compile(r'(?<![\w.])\d+(?:\.\d+)?')


def numbers(obj, out):
    if isinstance(obj, dict):
        for v in obj.values():
            numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            numbers(v, out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out.add(float(obj))
    elif isinstance(obj, str):
        out.update(float(n) for n in NUM.findall(obj))
    return out


def ask(base, uid, text):
    req = urllib.request.Request(f'{base}/api/ask', json.dumps({'study_uid': uid, 'text': text}).encode(),
                                 {'Content-Type': 'application/json'})
    t0, marks, answer, tools, event = time.monotonic(), {}, '', [], None
    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw in resp:
            line = raw.decode().rstrip('\n')
            if line.startswith('event:'):
                event = line[6:].strip()
            elif line.startswith('data:'):
                data, dt = json.loads(line[5:]), round(time.monotonic() - t0, 2)
                if event == 'tool':
                    tools.append(data.get('tool'))
                    if data.get('tool') == 'viewer_command':
                        marks.setdefault('viewer', dt)
                elif event == 'delta':
                    marks.setdefault('text', dt)
                    answer += data.get('text', '')
                elif event in ('done', 'error'):
                    marks[event] = dt
                    if event == 'error':
                        answer += f' [error: {data}]'
    return marks, answer.strip(), tools


def main():
    uid, base = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else 'http://127.0.0.1:8100')
    with urllib.request.urlopen(f'{base}/api/studies/{uid}/findings') as r:
        allowed = numbers(json.load(r), set())
    allowed.update(float(n) for n in NUM.findall(uid))
    rows = []
    for text in PHRASES:
        marks, answer, tools = ask(base, uid, text)
        stray = [n for n in NUM.findall(answer) if float(n) not in allowed]
        sentences = len(re.findall(r'[.!?](?:\s|$)', answer))
        rows.append({'phrase': text, **marks, 'sentences': sentences, 'tools': tools, 'stray_numbers': stray, 'answer': answer})
        print(json.dumps(rows[-1]), flush=True)
    return rows


if __name__ == '__main__':
    main()
