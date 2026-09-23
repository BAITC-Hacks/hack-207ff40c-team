# Foundation repairs — 23 September 2026

This is the disposition register for the **72 findings** in
[TECHNICAL_REVIEW.md](TECHNICAL_REVIEW.md). That document preserves the original
failure scenarios and historical line numbers. This repair covers the canonical
station/worker/interface and the retained Go, browser appliance and native paths.

The intended change for the secretary is reliability: accepted recordings remain
recoverable, cancellation and retry preserve the latest intent, failed saves keep
edits, and exported minutes reflect the committed revision. It does not establish
speech accuracy, customer acceptance or production readiness.

## Verification scope

Reproduce with `make verify`, `make verify-go` and `make verify-native` from the
repository root. The latter requires macOS. These commands use installed tools;
they do not download models or dependencies. The CI workflow provisions its
declared build dependencies separately before running the same checks.

Results and complete command output are retained in
[verification/foundations-20260923/](verification/foundations-20260923/).
`make verify` includes 34 harness tests, 237 station/worker tests, 95 retained
Python contract tests, 33 browser regressions, two actual review/export browser
workflows, the station frontend build and lint. Model responses, audio tools and
meeting-provider pages used by regression fixtures are explicitly synthetic.
The review/export workflows run the real local services and inspect downloaded
PDF text and DOCX XML independently.

The native application compiled and its 16 tests passed. Go validation includes
the retained interface build and the full Go test suite with the race detector;
both passed with exit 0. No physical Radxa, live Teams/Zoom/Meet
session, customer recording, actual speech-model inference or container build was
available. Remote CI has been configured but not run by this work.

## Disposition by finding

Test abbreviations refer to the linked suites below. Every row records an
implemented repair, including explicit rejection of unsupported combinations.
No row asserts real model quality from a contract fixture.

| ID | Repair and relevant implementation | Regression evidence |
| --- | --- | --- |
| R001 | Root-only model-weight exclusions preserve `internal/models/*.go`; harness/package inventories require all four source files. | H: source-inventory/manifest test; G: compiled imports. New source files must be included in the next commit. |
| R002 | `protocol.py` carries dates from cumulative source speech, never model quotations; chunk boundaries keep literal ISO dates intact. | W: multi-chunk deadline, forged quotation, boundary-spanning date. |
| R003 | `main.py` supervises claim/pipeline failures with bounded backoff; health and admission report degradation until the consumer recovers. | W: transient SQLite failure, degraded health/admission, resumed processing. |
| R004 | `main.py` syncs the renamed source directory before database acceptance. | W: observed fsync-before-commit order; failed sync cannot acknowledge or retain a queued row. Physical power-loss behavior is untested. |
| R005 | Summary/chat Markdown disables raw HTML and renders image alt text without loading URLs. | F: hostile iframe/script content and zero external image requests. |
| R006 | Upload failures propagate; recorder blobs remain available for retry/download; discarding active audio requires confirmation. | F: microphone/system 413/network failure, retained recording, local download and close confirmation. |
| R007 | API and repository validate sort fields/direction and use fixed SQL columns. | G: SQL-expression and invalid-direction rejection. |
| R008 | Adapter logging redacts credential argument values while preserving execution arguments. | A/Go: token-argument redaction, including alternate token flag forms. |
| R009 | CLI installer shell-quotes server URL and token values; inputs cannot introduce shell substitutions. | C: installer executes with hostile synthetic values without invoking them. |
| R010 | CLI authorization requires exact literal loopback callback, a random state nonce and explicit browser approval; callback validates nonce before saving credentials. | C + F: external callback rejection, nonce mismatch, valid approval/redirect contract. |
| R011 | Dropzone waits for a closed-file byte/hash marker, verifies and syncs its own copy, retains producer audio and deduplicates committed handoffs. | D: growing file, digest mismatch, lost acknowledgement, deletion replay and intentional new handoff. |
| R012 | First administrator creation uses one atomic database operation. | G: concurrent attempts produce one administrator. |
| R013 | Buffered adapters use per-invocation temporary directories and remove chunks on completion/failure. | A/Python: overlapping buffered calls do not share names or leave chunks. |
| R014 | `bundle.py` validates the fully expanded 16 MiB result before review exports or publication; oversized edits return 413 and retain the prior revision. | W: small request expanding repeated evidence beyond the limit never reaches export/commit. |
| R015 | PDF tables split long cells across pages without dropping trailing Russian/Kazakh text. | W: maximum-length assignment; PDF page count and extracted final text. |
| R016 | Pipeline cancellation is checked between stages and propagated into active audio/model subprocess supervision. | W: cancel after ASR cannot enter diarization/extraction. |
| R017 | Local Pyannote receives its resolved YAML configuration file, including when configured with a directory. | W: file/directory loader contracts, no repository-ID substitution. |
| R018 | Untimed nonempty transcripts are rejected for diarization; GigaAM plus diarization fails before conversion. | W: unsupported timestamp contract and early pipeline refusal. |
| R019 | Capability readiness checks the selected Pyannote or Sherpa backend and its local assets. | W: Pyannote readiness without unrelated Sherpa assets; missing configuration remains unavailable. |
| R020 | ASR/diarization run in supervised child processes with deadlines, shared descendant process groups and parent-owned scratch cleanup. | W: real sleeping child/grandchild termination on cancellation/timeout; synthetic executable output contract. |
| R021 | Station generation checks prevent stale upload/cancel/retry/result responses from replacing newer intent; retry remains queued during worker cleanup conflicts. | S: interleaved acknowledgements, stale result/failure, HTTP 409 followed by cancelled/failed state and eventual retry. |
| R022 | Station rejects inverted speaker bounds and makes deterministic upload rejection terminal while retaining the recording. | S: validation before archive and HTTP 400/409/413/415/422 handling. |
| R023 | Export signature validation accumulates bytes across arbitrary transport chunks. | S: PDF/DOCX signatures delivered one byte at a time. |
| R024 | Station scheduling orders by next availability and preserves command priority without starving new uploads. | S: continuously polled jobs cannot prevent a third upload. |
| R025 | Browser join monitoring uses stable terminal state, not transient page text alone. | B: provider page fixtures transition into meeting and terminal states. Live provider changes remain an acceptance dependency. |
| R026 | Browser restart recovery produces a valid bounded WAV copy and preserves original interrupted bytes. | B: damaged/odd-length headers, normal finalization and oversized/unrecoverable source retention. |
| R027 | Recording duration is the minimum of worker-aligned station limit, controller limit and PCM byte capacity; invalid limits fail before recording. | S + B: forwarded durations, short byte budget, controller minimum and invalid limits. |
| R028 | Pyannote adapter handles the version-4 annotation wrapper and writes RTTM through its actual file API. | A/Python: wrapper output and RTTM fixture contract. |
| R029 | Go parameter conversion and Python adapters preserve explicit CPU/device selection. | A/Go + A/Python: CPU forwarding does not become automatic GPU selection. |
| R030 | Voxtral automatic language uses an unconditioned per-audio request; explicit language hints remain explicit. Required processor/tokenizer versions are pinned and checked. | A/Python plus tagged primary source inspection linked in adapter README; no live multilingual inference. |
| R031 | Sortformer rejects unsupported speaker-count constraints before model loading; its bundled model has four outputs. | A/Python: unsupported range rejection and four-output fixture. |
| R032 | Buffered chunk durations must be finite and positive; invalid CLI values fail before model load. | A/Python: zero, negative, nonfinite and malformed values. |
| R033 | Browser storage access is guarded, with memory fallback when getters or methods throw. | F: theme change/logout still work when storage is unavailable. |
| R034 | Archive pages allow navigation beyond 200 meetings and keep older entries reachable. | F: open the 201st meeting, navigate back to newer pages. |
| R035 | Refresh requests are coalesced and tied to session generation, so stale failures cannot erase a newer login. | F: simultaneous 401s and intervening login. |
| R036 | Browser Stop Sharing finalizes system recording and stops every media track. | F: actual synthetic MediaRecorder blob survives ended-track handling. |
| R037 | Partial media startup releases acquired streams/audio resources when a later step fails. | F: media startup rejection and unmount fixtures. |
| R038 | Chat decoding retains UTF-8 decoder state between stream chunks. | F: byte-split Russian/Kazakh text remains intact. |
| R039 | Failed/JSON summary responses do not replace valid summary text. | F: non-2xx and wrong content-type responses. |
| R040 | Template failures preserve drafts; token rotation cannot reset fields; save completion belongs to its original editor. | F: failed-save retry, auth rotation, pending dismissal and replacement-editor tests. |
| R041 | Bulk operations track per-item success; failed items remain selected and visible for retry. | F: mixed-success batch fixtures. |
| R042 | Multi-track start sends the agreed configuration shape. | F: outgoing request body checked against the API contract. |
| R043 | Segment-only transcripts remain readable, including timestamp seeking. | F: result without top-level text. |
| R044 | Notes await persistence, retain failed edits and cannot close a newer draft after a delayed save. | F: rejected POST, desktop/mobile pending dismissal and request ownership. |
| R045 | Audio visualizers share the intended media graph and release contexts/nodes on final unmount. | F: StrictMode replay and actual audio-context cleanup. |
| R046 | Quick polling handles missing jobs, bounded repeated failures and pending/processing/completed transitions. | F: 404/failure limits and successful pending queue. |
| R047 | Retained engine semantic verification receives complete chronological source and all factual fields, or explicitly declines verification. | N/Python: late owner/deadline corrections and context-budget refusal. |
| R048 | Native snapshots persist monotonically increasing revisions; delayed HTTP cannot undo newer WebSocket state, including after restart. | N/Swift + backend: revision ordering, rebuilt hub and legacy local-file compatibility. |
| R049 | Go recovery starts workers before draining pending jobs and can recover more jobs than channel capacity. | G: 225 pending jobs with a 200-slot channel. |
| R050 | Admission reserves capacity before changing persisted job state; rejected reruns retain transcript/summary and return the actual stored parameters/status. | G: full queue and injected scheduling transaction rollback for audio/video. |
| R051 | Atomic schedule/claim and execution ownership prevent duplicate starts, including cancel/retry/cleanup windows. | G: concurrent schedule/claim, delayed cancellation cleanup, claim registration and final-write barriers. |
| R052 | Every finished Go job cancels its derived context. | G: recovery processor observes child contexts released after completion. |
| R053 | Shutdown stops producers before broadcaster teardown; closed delivery cannot leave a blocked sender. | G/SSE: real HTTP stream/shutdown and race suite. |
| R054 | Multipart upload emits one response after all tracks and job persistence succeed. | G: one valid JSON document containing both tracks. |
| R055 | Multi-track uploads persist their owned folder; deletion also handles older rows without that field. | G: actual multipart directory lifecycle. |
| R056 | Invalid page/limit values are rejected before repository access. | G: zero, negative, nonnumeric and excessive pagination. |
| R057 | Malformed transcription configuration fails without starting a job. | G: malformed JSON/type mismatch leaves previous completed result intact. |
| R058 | Registration issues the media-access cookie as well as refresh/session credentials. | G: immediate HttpOnly media cookie after registration. |
| R059 | Completion webhooks load the committed transcript instead of the pre-inference object. | G: actual localhost webhook payload compared with stored transcript. |
| R060 | Quick-job API reads return independent snapshots of mutable/pointer fields. | G: concurrent status access under the race detector. |
| R061 | Quick requests use bounded admission, one consumer and the shared inference capacity, with cancellation/deadlines. Sequential multi-track children retain the parent's admission. | G: admission saturation, cancellation while waiting and one-slot multi-track orchestration. |
| R062 | Quick manifests persist expiry across restart; periodic cleanup removes old source/output/database data, including legacy orphan records. | G: restart, young orphan aging and output-without-source expiry. |
| R063 | Quick success requires a real stored transcript and durable result manifest before completion publication/purge. | G: missing result and manifest-write failure retain recoverable state. |
| R064 | Summary streaming drains content and error channels correctly; failed partial output is not persisted. | G: buffered multilingual content over repeated runs and error-channel closure. |
| R065 | Gzip streaming flushes its compressor and the underlying HTTP writer. | G/middleware: client reads decompressed content before handler finishes. |
| R066 | Empty/nil fallback model responses return errors instead of dereferencing missing content. | G: empty chat/summary fallback fixture. |
| R067 | Chat budgeting counts the transcript once. | G: a request fitting the context is accepted and forwarded with one transcript copy. |
| R068 | Installer uses the supported `--token-stdin` login contract and private configuration permissions. | C: registered flag, shell execution and config permissions. |
| R069 | CLI upload streams multipart bytes with cancellation/deadlines and bounded watcher concurrency; premature success/redirect cannot silently lose audio. | C: streaming, cancelled/partial upload, bounded watcher workers. |
| R070 | Deletion records intent under the queue's ownership lock before file removal, atomically clears children and leaves a scrubbed delta-sync tombstone; retry resumes after filesystem/database failure. | G: completed-but-owned job refusal, filesystem failure, database rollback after real file removal, retry and tombstone checks. |
| R071 | Calendar text normalizes CRLF/bare CR before escaping. | W: forged component terminators cannot inject an extra VTODO. |
| R072 | Worker/station resource limits reject nonfinite, nonpositive and invalid numeric values. | W + S: NaN/infinity/negative/zero configuration fixtures. |

## Test locations

- **H:** [harness tests](../tests/test_harness.py).
- **W:** [worker foundation regressions](../mac-worker/tests/test_foundations.py), plus existing worker API, review and pipeline tests.
- **S:** [station foundation regressions](../station/tests/test_station_foundations.py), plus existing station capture/join/local HTTP tests.
- **F:** [browser regressions](../web/frontend/e2e/regressions.spec.ts) and [real review/export workflows](../web/frontend/e2e/review.spec.ts).
- **G:** [API regressions](../internal/api/regression_test.go), [admission/deletion failures](../internal/api/admission_deletion_regression_test.go), [queue regressions](../internal/queue/regression_test.go), [queue lifecycle](../internal/queue/lifecycle_regression_test.go), [repository lifecycle](../internal/repository/lifecycle_test.go), [pipeline](../internal/transcription/pipeline_regression_test.go), [quick jobs](../internal/transcription/quick_regression_test.go), [SSE](../internal/sse/broadcaster_test.go), [gzip](../pkg/middleware/compression_test.go).
- **C:** [CLI API security](../internal/api/cli_security_test.go), [CLI streaming/authorization](../internal/cli/security_test.go).
- Additional **G** integration barriers: [deletion ownership](../internal/api/deletion_ownership_regression_test.go), [multi-track admission](../internal/transcription/multitrack_admission_regression_test.go).
- **D:** [dropzone tests](../internal/dropzone/dropzone_test.go), [dropzone handoff contract](../internal/dropzone/README.md).
- **A:** [Go adapter contracts](../internal/transcription/adapters/contracts_test.go), [Python adapter contracts](../internal/transcription/adapters/py/tests/test_adapter_contracts.py), [primary API/version evidence](../internal/transcription/adapters/py/README.md).
- **B:** [capture recovery](../deploy/meeting-browser/tests/test_capture_recovery.py), [join page tests](../deploy/meeting-browser/tests/test_join_page.py).
- **N:** [retained engine tests](../engine/tests/test_engine.py), [native backend contract](../backend/tests/test_native_contract.py), [Swift client tests](../macos/Tests/MeetingBoxTests/).

## Operational changes and remaining acceptance

Existing dropzone producers must publish the documented `.ready` handoff; file
creation alone is no longer accepted as completion. CLI clients must use the new
state-bearing authorization flow or `--token-stdin`. The browser archive is paged.
Capture defaults to four hours, reduced by the PCM byte budget; pair
`MI_STATION_MAX_AUDIO_SECONDS` with worker `MI_MAX_AUDIO_SECONDS` when changing it.
Pyannote accepts a local pipeline YAML file or a directory containing that file.
GigaAM with diarization is explicitly unsupported until it provides timed segments.
Sortformer's bundled model supports four outputs only; choose another backend for
constrained speaker counts. These limits are surfaced, not simulated as successes.

Independent integration review added regressions for nested model processes,
ISO-date chunk boundaries, delayed editor responses, Markdown image requests,
queue cancellation ownership and deleted dropzone replays. The final source
inventory and receipts identify exactly what was checked. Sandbox-only failures
(localhost binds and Swift cache writes) were rerun with approved access; this
does not count as model or device verification.

The separate feature requests—formal issuance gate, delivery of reminders,
completion confirmation, confirmed cross-meeting task matching and project roles—
remain product work. The existing shared station token and self-entered reviewer
name are not per-person authorization. Provision local models and run a labeled
Russian/Kazakh/mixed audio-to-export acceptance set before claiming operational
speech performance. Physical interrupted recording/power recovery and real
meeting-provider integration also require their actual target environment.
