#!/usr/bin/env python3
"""Create a source ZIP from the clean committed revision, without runtime assets."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/packages/meeting-intelligence-submission.zip")
    args = parser.parse_args()
    if git("status", "--porcelain").strip():
        raise SystemExit("Commit the reviewed source changes first; the package must identify an exact revision")
    files = git("ls-tree", "-r", "--name-only", "HEAD").decode().splitlines()
    excluded = {"main", "server", "startup_log.txt", "tests/data/AMI-Corpus-IB4002.Mix-Headset-clip.wav"}
    excluded.update(name for name in files if Path(name).name.startswith(".env") and Path(name).name != ".env.example")
    output = args.output.resolve()
    receipt_path = output.with_suffix(".json")
    if output.exists() or receipt_path.exists():
        raise SystemExit("Refusing to overwrite an existing submission archive or receipt")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="meeting-package-") as directory:
        archive = Path(directory) / "source.zip"
        subprocess.run(["git", "archive", "--format=zip", "--output=" + str(archive), "HEAD", "--", ".",
            *[":(exclude)" + name for name in sorted(excluded)]], cwd=ROOT, check=True)
        with zipfile.ZipFile(archive) as bundle:
            names = set(bundle.namelist())
            for required in ("README.md", "LICENSE", "docs/SUBMISSION_NOTES.md", "requirements/validation.lock",
                             "scripts/run-local.py", "mac-worker/src/meeting_worker/review.py", "web/frontend/package-lock.json"):
                if required not in names:
                    raise SystemExit("Missing required submission file: " + required)
            if bundle.testzip() is not None:
                raise SystemExit("Source ZIP integrity check failed")
            if any(set(Path(name).parts) & {"node_modules", ".venv", ".local", ".git"} or name.startswith("models/") for name in names):
                raise SystemExit("Runtime/private assets unexpectedly tracked; inspect before packaging")
        with output.open("xb") as target:
            target.write(archive.read_bytes())
    receipt = {"commit": git("rev-parse", "HEAD").decode().strip(),
        "archive": output.name, "bytes": output.stat().st_size,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "excluded_tracked_files": sorted(excluded),
        "scope": "Source submission; no dependencies, model weights, private runtime archives or production-readiness claim"}
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(output)
    print(receipt_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
