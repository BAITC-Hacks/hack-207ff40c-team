# Innovation hackathon harness

A topic-adaptive preparation and build workflow for Codex.
Start with START_HERE.md. The starter stays in PREPARE mode until the human confirms
that event rules permit development. It is not a hackathon submission or a research reproduction.

## Use
Run from this folder:

```sh
python3 scripts/harness.py doctor
python3 scripts/harness.py check
python3 -m unittest discover -s tests -v
codex
```

Paste the preparation prompt in START_HERE.md.
Windows: use `py -3` for Python; `codex.cmd` avoids a blocked PowerShell .ps1 wrapper.
No package installs, model downloads, new API credentials, global settings, or permission
bypasses are part of the setup. Python 3.10+ is the only harness prerequisite.

## Contents
AGENTS.md provides compact standing instructions. Codex discovers the four project
skills under .agents/skills: hackathon-scout, hackathon-select, hackathon-build, and
hackathon-review. The check command validates their presence and frontmatter.

research/catalog.json and research/SHORTLIST.md carry six primary-source research leads.
brief.json and state.json keep official facts separate from assumptions.
scripts/harness.py supplies tool checks, activation, manifests and actual command execution.
scripts/evaluate.py supplies paired JSON-in/JSON-out evaluations with externally specified targets.
checks.json intentionally has no product commands until a product exists. verify must fail
until real test, build and smoke checks have been configured. Harness unit tests do not count.

## Honest boundaries
The harness is tested separately from the upstream research repositories. No upstream
code is bundled or claimed to be original. See research/SOURCE_NOTES.md for verification scope.
The scripts are not a sandbox. They run the argv commands configured in the project with
ordinary local permissions. Review these commands and external source before executing.
The evaluator measures adapter process wall time, including startup. It does not measure
browser experience, network traffic or model cost unless independently instrumented.
A perfect score on toy fixtures is not proof of innovation or production readiness.

Run CLI sessions from this repository root. A parent or user instruction file can affect
agent behavior; inspect any existing global instructions without deleting or overriding them.
