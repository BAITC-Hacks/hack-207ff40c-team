# Development from this repository root

The selected application and its harness share one Git repository. The import of
product checkpoint `fa15a850dd62cc87be94656e88196e022d4684f5` preserves the existing
module layout. Run commands here, not inside a `meeting-intelligence/` subdirectory.

## Working loop

Read [AGENTS.md](../AGENTS.md), [brief.json](../brief.json),
[state.json](../state.json) and [HANDOFF.md](HANDOFF.md). The user supplied the
actual case and authorized implementation; the current mode is BUILD. Keep audio
and text within local/self-hosted services and preserve provenance when editing
the transcript-to-reviewed-minutes workflow.

| Command | Purpose |
| --- | --- |
| `make build` | Compile the React UI for the standalone station |
| `make init` | Create private local configuration; does not install models |
| `make doctor` | Inspect application/model readiness |
| `make start` | Launch a provisioned local application |
| `make inspect` | Explicitly inspect the UI/archive with missing-model warnings |
| `make check` | Harness structure and standard-library harness regressions |
| `make verify` | Harness checks, UI build, backend/local HTTP tests, lint, real browser acceptance |
| `make package` | After committing, create a source ZIP under `.local/packages/` |

Setup commands are in [LOCAL_SETUP.md](LOCAL_SETUP.md). `make verify` assumes
the pinned core dependencies and test Chromium have been provisioned. It never
downloads models or starts external inference. `checks.json` is the executable
source of truth; logs are generated under ignored `reports/`, with reviewed
evidence copied into `docs/verification/` when relevant.

`tests/test_harness.py` copies only the harness's required fixture files into a
temporary repository and initializes explicit PREPARE fixtures. It does not copy
installed dependencies, private archives or the current BUILD authorization.
Snapshots prune those directories before traversal.

## Protocol accounting

| Requirement | Evidence / status |
| --- | --- |
| Actual brief and specific user outcome | [Case](CHALLENGE.md) and [decision](DECISION.md); secretary corrections and traceable assignments |
| Preserve the user-selected solution | Existing application improved; a new three-way selection was unnecessary |
| Baseline, fixed failures and independent checks | Baseline 108 backend tests; fixed source fixtures; corrected document content checked independently |
| Real interface and export | Browser pairs with actual services, saves/reloads revisions and downloads PDF/DOCX |
| Attribution and honest limits | [Attribution](ATTRIBUTION.md) and [submission evidence](SUBMISSION_NOTES.md); no new-ASR, 100x or production-readiness claim |
| Parallel work with clear ownership | Specialist changes were isolated in disjoint worktrees and integrated by the primary |
| No paid/external meeting-content APIs or model downloads | Retained during this session; test dependencies and Chromium were installed locally |
| Human-only activation step | **Procedural deviation:** the agent ran activation after the user's explicit implementation request. The harness reserves that CLI step for the human unless specifically delegated; that separate delegation was not recorded |
| Full speech/model acceptance | **Unfinished validation:** local RU/KZ/mixed audio and model quality were not exercised with provisioned models |

Build work was requested by the user. The activation deviation does not justify
inventing an approval or changing the historical timestamps. Future mode changes
must follow the written human-activation requirement. Tests and supplied synthetic
reports establish the documented application behavior, not real-recording accuracy.

## Commit contents

Commit the source, architecture/setup documentation, project skills/configuration,
lockfiles and explicitly synthetic verification artifacts. `.gitignore` excludes
local credentials, runtime state, models, dependencies, temporary worktrees,
backups and generated packages. The former nested product `.git` and a complete
Git bundle are preserved under `.local/repository-migration-20260923/`.

The root Git history is retained. No remote was changed, no commit was created
for this consolidation, and no push/deployment was performed. The previous ZIP
describes the earlier checkpoint; create a fresh package after committing this
consolidated root if a ZIP is needed.
