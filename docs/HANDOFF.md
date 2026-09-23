# Handoff

Mode: BUILD. The user supplied the Samruk-Kazyna case, selected the earlier
Meeting Intelligence solution and requested implementation. Submission only;
no paid APIs or external audio/text inference. Speech-model assets remain
unprovisioned. The human-activation procedural deviation is recorded in
[DEVELOPMENT.md](DEVELOPMENT.md), alongside the completed protocol checks.

## Current repository

**This directory is now the application and harness repository root.** Start with
[README.md](../README.md) and [ARCHITECTURE.md](ARCHITECTURE.md). The canonical
components are `web/frontend/`, `station/` and `mac-worker/`; their 194 tracked
files match imported product checkpoint `fa15a850dd62cc87be94656e88196e022d4684f5`.
Upstream baseline: `849f2224f93209feb9ce408f4ebd898026a9c97d` from the participant's
[Eraly-ml/meeting-intelligence](https://github.com/Eraly-ml/meeting-intelligence).

Root Git branch `main` and its existing history are preserved (pre-consolidation
HEAD `d6703a9`). **Changes are uncommitted for the user.** The former nested clone
has been flattened. Its complete Git bundle, original metadata, inactive
worktrees, original conflicting harness files, old binaries and previous ZIP
remain under ignored `.local/repository-migration-20260923/`. The bundle verified
successfully. No remote, deployment or publish operation was performed.

## What changed in this cleanup

- Application source and its existing `scripts/`, `tests/` and `docs/` merged into
  the root; conflicting README, environment example, ignore file and attribution
  were deliberately reconciled. The earlier implementation file list remains in
  [changed-files.txt](verification/changed-files.txt).
- `README.md`, `docs/ARCHITECTURE.md`, `docs/README.md`, `docs/DEVELOPMENT.md`,
  `START_HERE.md`, `AGENTS.md` and this handoff describe one source root, the
  component boundaries and the source-to-reviewed-export workflow.
- `Makefile` now exposes the canonical commands. The inherited Makefile and
  website/release/Go workflows are preserved under `docs/history/`; only the
  submission validation workflow remains active under `.github/workflows/`.
- `.gitignore` and `.dockerignore` exclude private/local data, model assets, dependencies, temporary
  worktrees and packages. `.env.example` points standalone users to generated
  local configuration; `.python-version` reflects the documented model/CI target.
- `checks.json` uses root paths and includes harness checks. `scripts/harness.py`
  prunes private/model/runtime directories from snapshots. `tests/test_harness.py`
  copies only required files and initializes explicit test state, rather than
  inheriting this BUILD workspace. `scripts/package-submission.py` writes future
  packages under `.local/packages/` after a clean root commit.
- `brief.json`, decision, experiment, attribution, verification and submission
  notes have current paths. Raw verification receipts/logs are in
  `docs/verification/`. The moved local environment was repointed without installs.

## Verification

Last full command: `python3 scripts/harness.py verify`, exit 0. All six configured
checks passed: harness structure; **33 harness regressions**; production React
build; **171 backend/local HTTP tests**; lint; **two real browser workflows**.
The browser checks corrected and recovered assignments, replayed a request,
reloaded and downloaded actual DOCX/PDF files whose content was checked
independently. These use explicitly synthetic supplied transcripts/reports;
no ASR or language-model inference is claimed.

Receipt: [root verification JSON](verification/verification-20260923T095442120502Z-b47d75.json).
`pip check`, application-source parity, `git diff --check`, Git bundle integrity,
`make help` and tool inspection also passed. Upstream deprecation/browser-support
data warnings remain visible in the raw logs. Linux/model provisioning and remote
CI have not been executed locally. The UI and core application behavior were not
changed by this repository consolidation.
Final canonical documentation links, the single active workflow structure and
Git exclusions were also checked successfully.

## Next action

Commit this consolidated root when ready. Use `make verify` for subsequent changes
and `make package` after committing if a new ZIP is required. The previous ZIP is
an archived checkpoint, not a package of these uncommitted root changes. Real
Russian/Kazakh/mixed-speech, diarization and offline audio-to-export acceptance
remain necessary before claiming production readiness or measured accuracy.
