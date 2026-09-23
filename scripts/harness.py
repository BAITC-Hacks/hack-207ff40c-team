#!/usr/bin/env python3
"""Dependency-free hackathon workflow checks. This is not a security sandbox."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ('hackathon-scout', 'hackathon-select', 'hackathon-build', 'hackathon-review')
REQUIRED = ('AGENTS.md','START_HERE.md','brief.json','state.json','checks.json',
            'research/catalog.json','evals/config.json','evals/cases.jsonl',
            'scripts/evaluate.py','docs/HANDOFF.md')
SKIP_DIRS = {'.git','.venv','venv','node_modules','__pycache__','reports','third_party','dist','.next'}


def stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:6]


def load_json(path: Path):
    def bad_constant(value):
        raise ValueError(f'Non-standard JSON number: {value}')
    return json.loads(path.read_text(encoding='utf-8'), parse_constant=bad_constant)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def build_authorized(root: Path) -> bool:
    state = load_json(root/'state.json')
    return (state.get('mode') == 'build' and state.get('rules_confirmed') is True
            and state.get('official_start_confirmed') is True)


def snapshot(root: Path) -> dict:
    hashes = {}
    for p in sorted(root.rglob('*')):
        relative = p.relative_to(root)
        if p.is_symlink() or not p.is_file() or set(relative.parts) & SKIP_DIRS:
            continue
        if (p.name.startswith('.env') and p.name != '.env.example') or p.suffix in {'.pyc','.log'}:
            continue
        hashes[str(relative).replace('\\','/')] = hashlib.sha256(p.read_bytes()).hexdigest()
    return {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'sha256':hashes,
            'note':'Local file manifest only, not tamper-proof evidence or organizer approval.'}


def check(root: Path) -> list[str]:
    errors = []
    for name in REQUIRED:
        if not (root/name).is_file():
            errors.append(f'Missing required file: {name}')
    for name in ('brief.json','state.json','checks.json','research/catalog.json','evals/config.json'):
        try:
            if not isinstance(load_json(root/name), dict):
                errors.append(f'{name} must contain a JSON object')
        except (OSError, ValueError) as exc:
            errors.append(f'{name}: {exc}')
    for name in SKILLS:
        a = root/'.agents/skills'/name/'SKILL.md'
        if not a.is_file():
            errors.append(f'Missing skill: {name}')
        elif not a.read_text(encoding='utf-8').startswith('---\nname: '):
            errors.append(f'Invalid skill frontmatter: {name}')
    if (root/'AGENTS.md').exists() and (root/'AGENTS.md').stat().st_size > 24000:
        errors.append('AGENTS.md exceeds this harness compactness budget (24KB)')
    return errors


def activate(root: Path, rules: bool, start: bool) -> None:
    if not rules or not start:
        raise ValueError('Both explicit human confirmations are required. Do not infer organizer permission.')
    brief = load_json(root/'brief.json')
    if not isinstance(brief.get('challenge_text'), str) or len(brief['challenge_text'].strip()) < 20:
        raise ValueError('Fill challenge_text in brief.json with the actual official challenge (at least 20 characters).')
    if not isinstance(brief.get('rules_source'), str) or not brief['rules_source'].strip():
        raise ValueError('Record rules_source in brief.json (URL, file, or attributed organizer message).')
    state = load_json(root/'state.json')
    if build_authorized(root):
        print('Already in BUILD mode; retaining original activation timestamp.')
        return
    write_json(root/'reports'/f'pre-build-manifest-{stamp()}.json', snapshot(root))
    state.update(mode='build', rules_confirmed=True, official_start_confirmed=True,
                 activated_at_utc=datetime.now(timezone.utc).isoformat())
    write_json(root/'state.json', state)
    print('BUILD mode activated from explicit human confirmation. This is not organizer verification.')


def expand_argv(value) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(x,str) and x for x in value):
        raise ValueError('argv must be a nonempty list of nonempty strings, not a shell command')
    return [sys.executable if x == '{python}' else x for x in value]


def timeout_value(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int,float)) or not (0 < value <= 600):
        raise ValueError('timeout_seconds must be a number above 0 and at most 600')
    return float(value)


def verify(root: Path) -> int:
    if not build_authorized(root):
        raise ValueError('Product verification is disabled in PREPARE mode. Harness checks are separate.')
    config = load_json(root/'checks.json')
    commands = config.get('commands')
    if not isinstance(commands, list) or not commands:
        raise ValueError('No product commands configured. Add real test, build and smoke checks; empty is NOT passing.')
    validated, names = [], set()
    for item in commands:
        if not isinstance(item, dict):
            raise ValueError('Each check must be an object')
        name, kind = item.get('name'), item.get('kind')
        if not isinstance(name,str) or not name.strip() or name in names:
            raise ValueError('Check names must be nonempty and unique')
        names.add(name)
        if kind not in {'test','build','smoke'}:
            raise ValueError('Every check kind must be test, build or smoke')
        validated.append((name, kind, expand_argv(item.get('argv')), timeout_value(item.get('timeout_seconds',120))))
    if {v[1] for v in validated} != {'test','build','smoke'}:
        raise ValueError('Configure at least one real test, build AND smoke command')
    report_id = stamp()
    results = []
    for index, (name, kind, argv, limit) in enumerate(validated):
        start = time.perf_counter()
        status, code, out, err = 'error', None, '', ''
        try:
            proc = subprocess.run(argv, cwd=root, text=True, encoding='utf-8', errors='replace',
                                  capture_output=True, timeout=limit, shell=False)
            code, out, err = proc.returncode, proc.stdout, proc.stderr
            status = 'passed' if code == 0 else 'failed'
        except subprocess.TimeoutExpired as exc:
            status, err = 'timeout', f'Exceeded {limit} seconds.'
            if exc.stdout:
                out = exc.stdout.decode('utf-8','replace') if isinstance(exc.stdout,bytes) else exc.stdout
        except OSError as exc:
            err = str(exc)
        log = root/'reports'/f'verify-{report_id}-{index:02d}.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text('STDOUT\n'+out+'\nSTDERR\n'+err, encoding='utf-8')
        results.append({'name':name,'kind':kind,'argv':argv,'status':status,'exit_code':code,
                        'seconds':time.perf_counter()-start,'log':str(log.relative_to(root))})
        print(f'{status.upper():7s} {name} -> {log.relative_to(root)}')
    passed = all(r['status']=='passed' for r in results)
    report = root/'reports'/f'verification-{report_id}.json'
    write_json(report, {'all_passed':passed,'results':results,
                        'warning':'Exit codes alone do not establish that a configured check is meaningful.'})
    print(f'Report: {report.relative_to(root)}')
    return 0 if passed else 1


def doctor() -> int:
    print(f'Python: {sys.version.split()[0]} | platform: {platform.system()} {platform.machine()}')
    if sys.version_info < (3,10):
        print('ERROR: Python 3.10+ required')
        return 2
    for name in ('git','node','npm','go','rustc','codex','codex.cmd'):
        print(f'{name:10s} {shutil.which(name) or "not found (may be optional)"}')
    print('No packages installed, credentials checked, network calls made or global settings changed.')
    print('An available executable does not confirm CLI login, model access or project compatibility.')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('doctor','check','status','snapshot','verify'):
        sub.add_parser(name)
    act = sub.add_parser('activate')
    act.add_argument('--confirm-rules', action='store_true')
    act.add_argument('--confirm-start', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'doctor':
            return doctor()
        if args.command == 'check':
            errors = check(ROOT)
            for e in errors:
                print('ERROR:',e)
            print('Harness structure: '+('FAILED' if errors else 'OK; product not evaluated'))
            return 1 if errors else 0
        if args.command == 'status':
            print(json.dumps({'state':load_json(ROOT/'state.json'),'brief':load_json(ROOT/'brief.json')}, indent=2))
        elif args.command == 'activate':
            activate(ROOT,args.confirm_rules,args.confirm_start)
        elif args.command == 'snapshot':
            dest = ROOT/'reports'/f'manifest-{stamp()}.json'
            write_json(dest,snapshot(ROOT))
            print(dest.relative_to(ROOT))
        elif args.command == 'verify':
            return verify(ROOT)
        return 0
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
