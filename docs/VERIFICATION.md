# Verification receipt

Tested in this environment on 2026-09-23 with Python 3.13.5 on Linux.

- Harness structure check: passed.
- Harness and paired-evaluator unit/integration checks: 32 tests passed.
- Verified behaviors include missing-config refusal, PREPARE-mode refusal, explicit activation,
  skill-copy consistency, independent target comparison, type-sensitive JSON comparisons,
  actual adapter subprocess execution, failed-baseline accounting, timeouts and report generation.
- The unit tests contain toy adapters only. They are not research results or product benchmarks.
- No Codex or Claude executable was available here; actual CLI discovery/login was not tested.
- macOS and Windows execution were not tested here. The Python scripts use cross-platform
  standard-library interfaces, but local shell commands and dependencies still need checking.
- No upstream research repository was executed. The starter contains links and research notes,
  not the third-party algorithms or a finished application.

Repeat locally: `python3 -m unittest discover -s tests -v`.

The tests disable Python site startup only in their standard-library toy child processes,
to avoid unrelated environment startup delays. Actual product commands run exactly as configured.
