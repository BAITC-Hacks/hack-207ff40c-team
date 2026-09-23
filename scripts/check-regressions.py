#!/usr/bin/env python3
"""Run installed regression tools; never provision dependencies or model assets."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(argv, *, environment=None, cwd=ROOT):
    print('+ ' + ' '.join(map(str, argv)), flush=True)
    subprocess.run(list(map(str, argv)), cwd=cwd, env=environment, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite', choices=['frontend', 'retained-python', 'go', 'native'])
    suite = parser.parse_args().suite
    environment = dict(os.environ)
    if suite == 'frontend':
        environment.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT / '.local/browsers'))
        run(['npm', '--prefix', 'web/frontend', 'run', 'test:regressions'], environment=environment)
    elif suite == 'retained-python':
        environment['PYTHONPATH'] = os.pathsep.join(str(ROOT / path) for path in ('station/src', 'engine', 'backend'))
        run([sys.executable, '-m', 'pytest', 'internal/transcription/adapters/py/tests',
             'deploy/meeting-browser/tests', 'engine/tests', 'backend/tests', '-q'], environment=environment)
    elif suite == 'go':
        go = shutil.which('go') or str(ROOT / '.local/tools/go/bin/go')
        if not Path(go).is_file():
            raise RuntimeError('Go is missing; provision the version in go.mod before running this check')
        # Compile the retained interface separately, keeping the station build intact.
        environment.update(VITE_MEETING_STATION='false', VITE_MEETING_LOCAL='false')
        run(['npm', '--prefix', 'web/frontend', 'run', 'build', '--', '--outDir',
             '../../.local/retained-ui', '--emptyOutDir'], environment=environment)
        target = ROOT / 'internal/web/dist'
        if target.is_symlink():
            raise RuntimeError('Refusing to replace an unexpected embedded-interface symlink')
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(ROOT / '.local/retained-ui', target)
        environment.update(GOTOOLCHAIN='local', GOPROXY='off',
            GOPATH=str(ROOT / '.local/go'), GOMODCACHE=str(ROOT / '.local/go/pkg/mod'),
            GOCACHE=str(ROOT / '.local/go-build'))
        run([go, 'test', '-race', './...'], environment=environment)
    else:
        if sys.platform != 'darwin' or not shutil.which('swift'):
            raise RuntimeError('The retained native application requires macOS and its installed Swift toolchain')
        run(['swift', 'test', '--package-path', 'macos', '--scratch-path', '.local/swift-build',
             '--cache-path', '.local/swift-cache'], environment=environment)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode)
    except (OSError, RuntimeError) as error:
        print('ERROR:', error, file=sys.stderr)
        raise SystemExit(2)
