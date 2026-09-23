# Harness verification

2026-09-23, Python 3.14.6 on Darwin arm64: harness structure passed; all 33 functional
harness/evaluator tests passed. See HANDOFF.md for commands, changes and limits.
The deleted assessment feature's 17 tests were retired with it. That preparation
run did not evaluate a product; these harness tests were not counted as product evidence.
HARNESS_TEST_LOG.txt is the original scaffold's historical log, not this run's receipt.

After the user supplied the case and authorized improvement, `checks.json` was
configured with the selected product's build, backend/local-HTTP tests, lint and
real browser acceptance. The integrated `python3 scripts/harness.py verify` run
passed all four commands (exit 0): 171 backend tests and two browser workflows,
plus the build and lint. Dependency consistency also passed.

Raw receipt: [verification JSON](verification/verification-20260923T093456358250Z-5e27cb.json).
The source package contains copies of these raw logs in `docs/verification/`.
Synthetic supplied transcripts exercised correction, omitted-task recovery and
downloaded DOCX/PDF content. Model inference and real language accuracy were not
tested. See [product evidence](SUBMISSION_NOTES.md).

After consolidation into this repository root, all six configured checks passed
again: harness structure, 33 harness regressions, production frontend build,
171 backend/local HTTP tests, lint and two real browser workflows. The harness
fixtures now initialize explicit test state and copy only required files;
snapshots prune private runtime/model directories before traversal.
Root receipt: [verification JSON](verification/verification-20260923T095442120502Z-b47d75.json).
Application-source parity (194 files), Python dependency consistency, the preserved
Git bundle and whitespace checks also passed. This cleanup installs no dependencies
and leaves the root changes uncommitted for the user.
