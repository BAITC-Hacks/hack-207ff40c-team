#!/usr/bin/env python3
"""Execute paired baseline/proposed JSON adapters against fixed, independent targets."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
from harness import ROOT, build_authorized, expand_argv, load_json, stamp, timeout_value, write_json


def strict_loads(text: str):
    def bad(value):
        raise ValueError(f'Non-standard JSON number: {value}')
    return json.loads(text, parse_constant=bad)


def at_path(value, path: str):
    for key in path.split('.'):
        if isinstance(value, dict):
            value = value[key]
        elif isinstance(value, list):
            if not key.isdecimal():
                raise KeyError(path)
            value = value[int(key)]
        else:
            raise KeyError(path)
    return value


def exact_equal(left, right) -> bool:
    # JSON booleans must not compare equal to 1 or 0; types are deliberate here.
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(exact_equal(left[k],right[k]) for k in left)
    if isinstance(left, list):
        return len(left)==len(right) and all(exact_equal(a,b) for a,b in zip(left,right))
    return left == right


def compare(output, expected: dict) -> list[dict]:
    mismatches = []
    for path, target in expected.items():
        try:
            actual = at_path(output, path)
            if not exact_equal(actual,target):
                mismatches.append({'path':path,'expected':target,'actual':actual})
        except (KeyError, IndexError, ValueError, TypeError):
            mismatches.append({'path':path,'expected':target,'error':'missing or invalid output path'})
    return mismatches


def read_cases(path: Path) -> list[dict]:
    cases, ids = [], set()
    for line_no, text in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        if not text.strip():
            continue
        try:
            value = strict_loads(text)
        except ValueError as exc:
            raise ValueError(f'Invalid case JSON on line {line_no}: {exc}') from exc
        if not isinstance(value,dict) or 'input' not in value:
            raise ValueError(f'Case on line {line_no} needs an object with input')
        identity = value.get('id')
        if not isinstance(identity,str) or not identity.strip() or identity in ids:
            raise ValueError(f'Case IDs must be nonempty and unique (line {line_no})')
        expected = value.get('expected')
        if not isinstance(expected,dict) or not expected or not all(isinstance(k,str) and k and all(k.split('.')) for k in expected):
            raise ValueError(f'Case {identity} needs nonempty explicit expected output paths')
        ids.add(identity)
        cases.append(value)
    if not cases:
        raise ValueError('Case file is empty. No evaluation was run; empty is NOT passing.')
    return cases


def invoke(argv: list[str], payload, root: Path, limit: float) -> dict:
    start = time.perf_counter()
    result = {'status':'error','output':None,'exit_code':None}
    try:
        proc = subprocess.run(argv,input=json.dumps(payload,ensure_ascii=False,allow_nan=False),
                              cwd=root,text=True,encoding='utf-8',errors='replace',capture_output=True,
                              timeout=limit,shell=False)
        result['exit_code'] = proc.returncode
        # Do not put real secrets or personal data in adapters; their diagnostic tail is retained.
        result['stderr_tail'] = proc.stderr[-4000:]
        if proc.returncode != 0:
            result['error'] = f'Adapter exited {proc.returncode}'
        elif len(proc.stdout) > 2_000_000:
            result['error'] = 'Adapter output exceeds the 2MB accepted result limit'
        else:
            try:
                result['output'] = strict_loads(proc.stdout)
                result['status'] = 'ok'
            except ValueError as exc:
                result['error'] = f'Expected one plain JSON value on stdout: {exc}'
    except subprocess.TimeoutExpired:
        result['status'],result['error'] = 'timeout',f'Exceeded {limit} seconds'
    except OSError as exc:
        result['error'] = str(exc)
    result['seconds'] = time.perf_counter()-start
    return result


def summarize(rows: list[dict], method: str) -> dict:
    results = [r[method] for r in rows]
    n = len(results)
    return {'attempted':n,'passed':sum(r['passed'] for r in results),
            'pass_rate':sum(r['passed'] for r in results)/n,
            'execution_errors':sum(r['status']!='ok' for r in results),
            'mean_process_seconds_all_attempts':statistics.mean(r['seconds'] for r in results),
            'median_process_seconds_all_attempts':statistics.median(r['seconds'] for r in results)}


def evaluate(root: Path) -> tuple[dict, Path]:
    if not build_authorized(root):
        raise ValueError('Product evaluation is disabled in PREPARE mode.')
    cfg = load_json(root/'evals/config.json')
    baseline = expand_argv(cfg.get('baseline_argv'))
    proposed = expand_argv(cfg.get('proposed_argv'))
    limit = timeout_value(cfg.get('timeout_seconds',30))
    filename = cfg.get('cases_file','evals/cases.jsonl')
    if not isinstance(filename,str) or not filename:
        raise ValueError('cases_file must be a nonempty relative path')
    path = (root/filename).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('cases_file must stay inside this repository')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    cases = read_cases(path)
    rows = []
    for index,case in enumerate(cases):
        row = {'id':case['id'],'category':case.get('category','unspecified'),'expected':case['expected']}
        # Alternate order to reduce a systematic first-run bias. Each run is still a cold process.
        methods = [('baseline',baseline),('proposed',proposed)]
        if index % 2:
            methods.reverse()
        for name,argv in methods:
            result = invoke(argv,case['input'],root,limit)
            result['mismatches'] = compare(result['output'],case['expected']) if result['status']=='ok' else []
            result['passed'] = result['status']=='ok' and not result['mismatches']
            row[name] = result
        rows.append(row)
        print(f"{case['id']}: baseline={'PASS' if row['baseline']['passed'] else 'FAIL'} "
              f"proposed={'PASS' if row['proposed']['passed'] else 'FAIL'}")
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    summary = {method:summarize(rows,method) for method in ('baseline','proposed')}
    sound_run = before == after and all(summary[m]['execution_errors']==0 for m in summary)
    report = {'cases_sha256_before':before,'cases_sha256_after':after,'case_count':len(cases),
              'baseline_argv':baseline,'proposed_argv':proposed,'summary':summary,'cases':rows,
              'evaluation_executed_without_errors':sound_run,
              'proposed_all_cases_passed':summary['proposed']['passed']==len(cases),
              'warning':'Exact-output adapter test only; not proof of novelty or significance. Timings include per-case process startup. No implied safety/calibration/production claim.'}
    dest = root/'reports'/f'evaluation-{stamp()}.json'
    write_json(dest,report)
    lines = ['# Paired evaluation','',f'Cases: {len(cases)}',f'Cases SHA-256: {before}','',
             '| Method | Passed / attempted | Execution errors | Mean process seconds |',
             '| --- | ---: | ---: | ---: |']
    for method,s in summary.items():
        lines.append(f"| {method} | {s['passed']} / {s['attempted']} | {s['execution_errors']} | {s['mean_process_seconds_all_attempts']:.6f} |")
    lines.extend(['','Raw output: '+dest.name,'',report['warning'],
                  '\nExecution sound: '+str(sound_run),
                  '\nProposed passed every case: '+str(report['proposed_all_cases_passed'])])
    dest.with_suffix('.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return report,dest


def main() -> int:
    try:
        report,path = evaluate(ROOT)
        print(f'Report: {path.relative_to(ROOT)}')
        return 0 if report['evaluation_executed_without_errors'] and report['proposed_all_cases_passed'] else 1
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
