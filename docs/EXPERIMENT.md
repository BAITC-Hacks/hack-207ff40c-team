# Evidence for the secretary's reviewed-minutes workflow

2026-09-23. Technical acceptance using explicitly synthetic supplied transcripts
and reports; no end-user study or ASR/LLM inference. Selection:
[DECISION.md](DECISION.md). Product evidence and raw logs:
[SUBMISSION_NOTES.md](SUBMISSION_NOTES.md).

Baseline: the participant's earlier application at `849f222` had no canonical
review API/UI or DOCX export. Its 108 backend tests and frontend build/lint passed
before changes. The new chronology regressions failed against that implementation;
the omitted-action request returned HTTP 422 before its implementation.

Expected user change: after the model assigns the wrong owner/date or misses a
task, the secretary can correct or recover it from the unchanged transcript,
identify voices, save a revision and distribute matching PDF/DOCX/JSON/CSV/ICS.
Reject the implementation if it invents source evidence, duplicates a retry,
overwrites a stale revision or publishes inconsistent exports.

Fixed evidence: six verifier fixtures SHA-256
`c41d1b1272b9a9ac5dc99f886bd10eac3de763f53fbd4654e00935fac3c429c0`;
twelve human-review acceptance cases in the product's `docs/REVIEW_CASES.md`;
omitted-action case SHA-256
`a892bb74d96d8299cab738fe98f0e724c3fd2fef80c25a8bcdc5d3d6805f2208`
(canonicalization described in the product notes). Verifier tests use transport
fixtures and establish request/response contracts, not model accuracy.

Integrated result: `python3 scripts/harness.py verify`, exit 0.
171 backend tests passed, production frontend build and lint passed, two real
browser flows passed. Browser tests pair with actual Python services, edit/recover
tasks, replay a request, reload and download documents. DOCX XML and PDF text were
independently checked for the corrected owner/date. The input deliberately
contains stale or omitted findings; the target comes from the fixed source.
Failures and their recovery paths remain covered; no scores exclude failures.

Initial receipt: [verification JSON](verification/verification-20260923T093456358250Z-5e27cb.json).
The same application checks passed after consolidation into this source root,
along with all 33 harness regressions: [root receipt](verification/verification-20260923T095442120502Z-b47d75.json).
No measured secretary time saving, multilingual accuracy, production readiness,
or 100x improvement is claimed. Next acceptance requires provisioned local models
and labeled RU/KZ/mixed recordings, followed by an actual offline audio-to-export
run. No model weights, paid APIs or private meeting data were used here.
