# Handoff

## Latest preparation refresh — 2026-09-23

Re-read AGENTS.md, START_HERE.md, brief.json, state.json, the research catalog,
relevant shortlist cards and the existing decision report. Retained exactly three
provisional directions. Updated docs/DECISION.md with a compact table of first
falsifiable experiments, explicit rejection conditions and critical risks; separated
these 60-minute proposed spikes from the larger evaluation plans. Fixed load time
as the notes candidate's primary performance outcome to avoid choosing a favorable
metric after seeing results. Sources remain those reviewed earlier in this session;
no new online research or upstream execution was needed for this refresh.

Fresh commands from the repository root, all exit 0:

- `python3 scripts/harness.py doctor`: Python 3.14.6 on Darwin arm64; Git, Node,
  npm and Codex present; Go, Rust and codex.cmd absent. No credentials checked.
- `python3 scripts/harness.py check`: structure OK; product not evaluated.
- `python3 -m unittest discover -s tests -v`: 33 tests passed in 0.464s.
- `node --version`: v24.12.0; `npm --version`: 11.6.2;
  `git --version`: 2.50.1 (Apple Git-155).
- `git status --short` and `git branch --show-current`: scaffold files remain
  untracked on main. No commit made.

Files edited this refresh: docs/DECISION.md and docs/HANDOFF.md only.
No check/test failures. No submission code, fixtures, dependencies, models or API
services added. PREPARE remains active, both confirmations false, research selection
null, official challenge absent and budget $0. Product experiments remain unrun.
Last passing test command: `python3 -m unittest discover -s tests -v`.
Next action: obtain the official challenge and rules, then reassess. Stopped after
this preparation report. The sections below retain earlier work receipts.


Updated 2026-09-23. Mode: PREPARE. Official challenge and rules are missing. `state.json` remains unchanged: rules/start confirmations false, selected research ID null. Approved API budget remains $0. Product code, configured product verification and product benchmarks: none.

## Prepared result

`docs/DECISION.md` compares exactly three provisional directions: volunteer shift repair (conditional preference), interrupted inventory sync, and offline incident notes. Each includes user/problem hypotheses, a research mechanism, distinct proposed contribution, data contract, falsifiable experiment, baselines/metrics, risks, fallback and a timed 90-second demo. Theme fit is explicitly unknown. All thresholds are proposals; none are measured outcomes.

Read AGENTS.md, START_HERE.md, brief.json, state.json, the original handoff, research/catalog.json and relevant SHORTLIST.md cards. Applied `.agents/skills/hackathon-scout/SKILL.md` for read-only primary-source review. Sources and existing scheduling comparators are linked in DECISION.md. No external research code was incorporated; exact dependency commits remain unselected and component-license verification is a BUILD prerequisite.

## Transfer and files changed

Copied all 36 files from `/Users/amirkhan/innovation-hackathon/` into `/Users/amirkhan/sandwich/`, including .agents, .claude and .env.example. The source was preserved and the destination's existing .git retained. Before report edits, a recursive byte comparison found zero missing or different source files. The first copy was partially blocked at .agents by the workspace permission profile; the approved escalated copy completed that folder successfully.

After copying, authored only `docs/DECISION.md` and `docs/HANDOFF.md`. Existing harness tests may generate ignored Python bytecode. The source `reports/install-manifest.json` and `docs/HARNESS_TEST_LOG.txt` were copied as historical artifacts, not relabeled as current results. No modifications to scripts, tests, research cards, brief, state, evaluation cases or check configuration.

Git: branch `main`, no commits. `git log -1 --format=%H` reported that the branch has no commits; transferred files are untracked. No commit made.

## Local verification

Commands run from `/Users/amirkhan/sandwich`:

| Command | Exit | Observed result |
|---|---:|---|
| `python3 scripts/harness.py doctor` | 0 | Python 3.14.6, Darwin arm64; git, node, npm, codex, claude found; go, rustc, codex.cmd absent |
| `python3 scripts/harness.py check` | 0 | Harness structure OK; product not evaluated |
| `python3 -m unittest discover -s tests -v` | 0 | 32 tests passed in 0.467s |
| `node --version` | 0 | v24.12.0 |
| `npm --version` | 0 | 11.6.2 |
| `git --version` | 0 | 2.50.1 (Apple Git-155) |

Doctor inspects executable availability, not CLI authentication, credentials or research-library compatibility. No package installation, model download, paid API enablement or upstream execution occurred. Harness tests exercise their temporary fixtures; they do not activate BUILD in this repository or validate a submission. Product `verify` and `evaluate` were not run in PREPARE mode.

Observed research limitation: read-only web lookup of RIBLT's raw main/go.mod returned an error; dependency versions remain unverified. The catalog's earlier failed clone belongs to the supplied research record, not this run. No harness check or unit test failed.

Last passing required test command: `python3 -m unittest discover -s tests -v`. Post-edit validation passed: `python3 scripts/harness.py check` exited 0; recursive source comparison confirmed all 36 source files present with only DECISION.md and HANDOFF.md changed; state assertions confirmed PREPARE with both confirmations false and no selected research ID (exit 0).

## Next action

Obtain the official challenge and rules from the human, then reassess the comparison. Stop here until that information and explicit development authorization arrive. Do not activate BUILD, implement experiments/submission code, install dependencies or enable APIs from this provisional preference.

## Follow-up: Codex-only harness

At the user's request, removed CLAUDE.md and all four .claude/skills files
(and their empty directories). Updated scripts/harness.py to require only Codex
skills and omit Claude executable discovery. Updated tests/test_harness.py to
check missing/invalid Codex skills instead of duplicate-copy divergence. Updated
README.md, START_HERE.md and research/SOURCE_NOTES.md for the current layout.
Earlier transfer receipts, install manifest and test logs remain historical.
The original installer in Downloads and original source workspace were not modified.

Validation: `python3 scripts/harness.py check` and `python3 scripts/harness.py doctor`
exited 0. `python3 -m unittest discover -s tests -v` exited 0: 33 tests passed
in 0.446s. No failures. All four .agents skills remain present; state remains
PREPARE. Branch main still has no commits. No submission work or installs occurred.
Next action remains obtaining the official challenge and rules.
