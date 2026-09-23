# Foundation repair verification

Local results from 23 September 2026, macOS arm64, Python 3.14.6 and Go 1.24.4.
The inspected root is based on `ebe8e1e`; repair changes are uncommitted.
[Source manifest](source-manifest.json) hashes the modified/new source and
documentation. [Changed-file inventory](changed-files.txt) lists this work chunk.

| Command | Observed outcome | Exit | Raw evidence |
| --- | --- | ---: | --- |
| `python3 scripts/harness.py verify` | All eight configured checks passed: 34 harness, 237 station/worker, 95 retained Python, 33 browser regressions, two real review/export workflows, frontend build and lint | 0 | [Machine-readable receipt](verification.json); its eight log paths are relative to this directory |
| `.venv/bin/python scripts/check-regressions.py go` | Retained frontend compiled; full `go test -race ./...` passed, including historical integration suites | 0 | [Go build and race output](go.txt) |
| `.venv/bin/python scripts/check-regressions.py native` | Actual Swift application compiled; six XCTest and ten Swift Testing cases passed | 0 | [Native build/test output](native.txt) |
| `python3 scripts/harness.py check` | Required files, including Go model source, present | 0 | Result recorded in handoff; also covered by the harness receipt |
| `git diff --check` | No whitespace errors | 0 | Run after the integrated source and documentation edits |

The first complete Go run failed on three historical fixtures expecting the old
CLI callback, installer request and unowned cancellation contracts. Its output is
retained in [go-initial.txt](go-initial.txt), exit 1. The fixtures now use a valid
loopback callback with nonce, an actual HTTP origin, and queue-owned cancellation.
Hostile callback, shell-injection and cancellation-race regressions remain active.
The full rerun passed; cached package results refer to unchanged package inputs
from the initial run. No failing package was removed from the command.

Initial sandboxed runs could not bind localhost or write Swift's compiler cache;
approved reruns exercised those same checks. No model packages or model weights
were installed. Go and its existing pinned modules were provisioned into ignored
local directories for these tests. The Go check disables automatic toolchain and
module downloads.

Synthetic model responses, media-tool fixtures and provider-page fixtures test
contracts/failure handling. They do not establish Russian/Kazakh recognition,
speaker accuracy, live provider integration, hardware power-loss recovery or
production readiness. Actual review/export tests run real local services and
independently inspect downloaded documents. Container builds, provisioned model
inference and remote CI were not run.
