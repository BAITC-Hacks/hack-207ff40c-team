# Production engineering review — 23 September 2026

The repository is not ready for a production-readiness claim. The findings below
are open defects, not fixes made by this review. They include inherited code
because the requested scope was the entire relevant implementation, not a diff.
Passing the current checks does not cover these failure paths.

Reviewed working tree: root commit `e40f2733d18f989a1e24023172214bb1046c2562`
plus the interface branding changes recorded in HANDOFF. Paths and line numbers
below refer to this checkout. Three independent reviewers examined the worker,
station/appliance, and frontend/native components; the integrator reviewed the
Go server, queue, authentication, streaming, CLI, packaging and their call sites.

Scope labels matter:

- **Current**: standalone React interface, station, Mac worker, and repository packaging.
- **Optional worker**: a selectable inference backend in the current worker.
- **Retained**: Go server/legacy React interface/Go adapter/CLI or appliance deployment.
  These are shipped source, but are not all exercised by the canonical local launcher.
- **Inactive native**: earlier Python engine and Swift client, outside the canonical application.

Priorities: P1 urgent defects; P2 actionable defects; P3 lower-impact defects.
No P0 finding is asserted. Each entry gives a concrete failure and a minimal fix.
Synthetic probes establish control-flow or contract failures, not model accuracy.

## P1 findings

### R001 — [P1] Include the required Go model source in submissions

**Location:** `.gitignore:8`; also `.dockerignore:37–38`, `scripts/harness.py:25,52–53`.
**Scope:** Current packaging; retained Go build.
The unanchored `models/` exclusion matches `internal/models`, not just downloaded
weights. `git check-ignore -v` identifies all four required Go source files there,
and `git ls-files internal/models` is empty in the current commit. A normal commit
or Git-based submission therefore omits the package imported throughout the Go
server. Docker excludes it independently, and the harness manifest omits it too.
**Fix:** scope weight exclusions to their actual root directories, include
`internal/models/*.go`, and check the source inventory of a clean checkout and
container build context. Do not globally exempt all directories named `models`.

### R002 — [P1] Preserve previously established deadlines across extraction chunks

**Location:** `mac-worker/src/meeting_worker/protocol.py:95–103`.
**Scope:** Current.
The next chunk's allowed deadline enum is built from its text plus previous
evidence quotations. Those quotations are not derived until all chunks finish
at line 189. A deadline present only in an earlier chunk is consequently excluded
from the schema used to carry the action forward. A synthetic schema probe with
an existing `2026-09-25` deadline produced the enum `[None]` on the next chunk.
The model must erase that date or violate the schema.
**Fix:** build the enum from trusted cumulative transcript evidence, preserving
earlier supported dates; test a two-chunk meeting whose deadline is not repeated.

### R003 — [P1] Supervise the worker's sole queue consumer

**Location:** `mac-worker/src/meeting_worker/main.py:84–86`.
**Scope:** Current.
An exception from `store.claim` escapes the background task permanently. The API
continues serving health and accepting work even though nothing consumes the
queue. A temporary TestClient probe that raised one SQLite `OperationalError`
observed one claim attempt, HTTP 200 health, and subsequent queued work never
claimed. The pipeline's own error handling does not protect this call.
**Fix:** catch recoverable claim failures with bounded backoff, supervise the task,
and make readiness fail if the consumer has died. Test recovery from one transient
database failure and explicit degradation for persistent failures.

### R004 — [P1] Make the worker's accepted source filename durable before committing

**Location:** `mac-worker/src/meeting_worker/main.py:169–178`.
**Scope:** Current.
The upload bytes are fsynced, then the temporary file is renamed and the SQLite
job is durably committed without syncing the source directory. A power failure
after the response can preserve the queued row but lose the rename that gives
the recording its final name. File fsync alone does not make the directory entry
durable. This contradicts acknowledgement of an archived source; the station's
separate archive mitigates it only when that station is present.
**Fix:** fsync the source directory after the rename and before committing or
acknowledging the job, using the existing directory-sync pattern from bundles.

### R005 — [P1] Remove executable raw HTML from generated summaries and chat

**Location:** `web/frontend/src/features/transcription/components/audio-detail/SummaryDialog.tsx:227`;
also `web/frontend/src/components/ChatInterface.tsx:588,606`.
**Scope:** Retained React/Go interface.
Untrusted model output is passed through `rehypeRaw` without sanitization. A probe
with the installed Markdown plugins retained an iframe with executable `srcdoc`.
In the Go-served interface there is no CSP preventing that same-origin iframe
from accessing the parent session and authenticated APIs. A malicious transcript
that is echoed into a summary can therefore turn viewing minutes into stored XSS.
**Fix:** disable raw HTML, or apply an explicit sanitization allowlist that excludes
iframes and executable content; add CSP and a malicious-model-output browser test.

### R006 — [P1] Keep the only recording when upload fails

**Location:** `web/frontend/src/contexts/GlobalUploadContext.tsx:123–145`.
**Scope:** Retained recorder interface.
`uploadFiles` catches upload failures and resolves normally. Its recorder callers
interpret that resolution as successful delivery:
`web/frontend/src/components/AudioRecorder.tsx:243–251` and
`web/frontend/src/components/SystemAudioRecorder.tsx:446–454` clear the recording Blob. A 413 response,
server error, or disconnected network therefore discards a newly recorded meeting
that has no other saved copy. Showing an upload toast does not preserve the audio.
**Fix:** return explicit per-file success or reject on failure; clear the Blob only
after confirmed acceptance and retain retry/download controls. Test failed uploads
from both recording modes, not only uploaded files that already exist on disk.

### R007 — [P1] Allowlist database sort expressions

**Location:** `internal/repository/implementations.go:118–122`.
**Scope:** Retained Go API.
The listing handler forwards `sort_by` and `sort_order` directly from query
parameters (`internal/api/handlers.go:919–934`) into `db.Order`. This is SQL syntax,
not a bound parameter. An authenticated caller can supply expressions or
subqueries instead of a column name, including conditional ordering based on
other tables. The finding does not depend on stacked statements being supported.
[GORM explicitly identifies Order as an unescaped input](https://gorm.io/docs/security.html).
**Fix:** map accepted public sort names to fixed columns and restrict direction
to `asc`/`desc`; reject everything else. Add request-level injection tests.

### R008 — [P1] Redact Hugging Face credentials from command logs

**Location:** `internal/transcription/adapters/whisperx_adapter.go:459`;
also `internal/transcription/adapters/pyannote_adapter.go:331`.
**Scope:** Retained Go inference adapters.
Both adapters log the complete argument vector at INFO. WhisperX appends the
configured or environment-provided `HF_TOKEN` at lines 561–566; Pyannote similarly
resolves and appends the credential. An ordinary authorized diarization run thus
writes a usable credential into operational logs, even when the operator kept it
out of request payloads. No real credential was read for this review.
**Fix:** redact credential arguments before logging, preferably pass secrets via
the child environment, and test logs with a sentinel token.

### R009 — [P1] Escape request values before generating executable shell scripts

**Location:** `internal/api/cli_install_handlers.go:72–73`.
**Scope:** Retained public CLI installer.
The `text/template` inserts the query-string token and request-derived server URL
inside shell double quotes. The token comes directly from `c.Query` at line 137;
forwarded headers can also supply the URL. Double quotes still evaluate shell
substitutions. A crafted installer URL can therefore execute attacker-provided
shell syntax when a user follows the documented download-and-run workflow.
**Fix:** avoid placing untrusted values in shell source, or use correct shell
literal escaping plus strict token/origin validation. Use a trusted configured
server origin and test generated scripts with inert metacharacter payloads.

### R010 — [P1] Restrict CLI authorization callbacks to the initiating local client

**Location:** `internal/api/cli_auth_handlers.go:75–87`.
**Scope:** Retained Go authentication.
The authorization endpoint accepts any parseable callback URL and appends a
long-lived bearer token. The confirmation interface obtains that destination
from its URL and navigates to the returned value. A victim who approves a plausible
device request can consequently send their token to an attacker-controlled HTTPS
site, rather than the local CLI. Parsing a URL does not validate its destination.
**Fix:** require the supported loopback scheme/host/port, bind the request to a
short-lived nonce initiated by the CLI, and show the destination in confirmation.
Test external origins and mismatched authorization attempts.

### R011 — [P1] Do not delete a dropzone recording while its producer is writing

**Location:** `internal/dropzone/dropzone.go:184–186,216–220`.
**Scope:** Retained Go dropzone.
A file-create event is followed by a fixed 500 ms sleep, copying, and deletion of
the original. There is no completed-write protocol. A recorder or network copy
that pauses for longer than 500 ms after its first write gets imported partially;
the original is then removed while its producer may still be writing to the
open inode. The successfully created job contains only the early audio bytes.
**Fix:** require an atomic final rename/ready marker, or a documented completion
protocol with stability checks; verify the copy before retaining/removing sources.
Test a producer that writes a recording in delayed chunks.

### R012 — [P1] Make first-administrator registration atomic

**Location:** `internal/api/handlers.go:1651–1658`.
**Scope:** Retained Go authentication.
The public registration route counts users, then hashes the password and inserts
at line 1687. No database constraint or transaction makes the single-admin rule
atomic; only duplicate usernames are rejected. Two concurrent requests using
different names can both see zero users and both create authenticated accounts
with access to the global meeting API.
**Fix:** enforce a database-backed singleton bootstrap claim atomically with user
creation. Test simultaneous first-registration requests and require one success.

### R013 — [P1] Give buffered transcription jobs private temporary chunk files

**Location:** `internal/transcription/adapters/py/nvidia/parakeet_transcribe_buffered.py:94–95`;
also `internal/transcription/adapters/py/voxtral/voxtral_transcribe_buffered.py:89–90`.
**Scope:** Retained Go/Python adapters.
The adapters use predictable process-global `/tmp/chunk_i.wav` or
`/tmp/voxtral_chunk_i.wav` filenames. The Go queue runs multiple jobs concurrently.
Two recordings selecting the same adapter can overwrite or delete each other's
chunks, producing the wrong meeting's transcript or a missing-file failure. The
predictable names also expose these writes to pre-existing filesystem entries.
**Fix:** create a private `TemporaryDirectory` per invocation and keep all chunks
under it; test overlapping jobs with distinct sentinel audio.

## P2 findings — current worker

### R014 — [P2] Bound expanded review results before publishing them

**Location:** `mac-worker/src/meeting_worker/review.py:101–107`.
**Scope:** Current.
Each manually recovered action copies the complete source quotation, then copies
it again into review history. A valid synthetic 7,958-byte request adding 50
actions against one 200 KB passage expanded a roughly 401 KB report to 20,441,227
bytes. The worker commits it before responding, while the station rejects JSON
over 16 MiB (`station/src/meeting_station/worker.py:43–44`). The review becomes
committed but unreadable through the station; retrying cannot shrink it.
**Fix:** store evidence references with bounded excerpts, bound history growth,
and validate the complete serialized result against the shared transport limit
before committing. Test the expanded size, not just request size.

### R015 — [P2] Allow long valid assignments to span PDF pages

**Location:** `mac-worker/src/meeting_worker/exports.py:152`.
**Scope:** Current.
Assignments are placed in table rows that cannot split across pages. A valid
4,000-character Russian action created a roughly 1,110-point row for a
685.9-point frame and raised ReportLab `LayoutError` in a synthetic export probe.
Because the export bundle is published together, this also prevents otherwise
valid DOCX/JSON publication and can fail a review or the whole processing job.
**Fix:** use splittable content/rows or a paragraph layout, with explicit content
limits where appropriate. Exercise long multilingual actions and evidence.

### R016 — [P2] Check cancellation between expensive inference stages

**Location:** `mac-worker/src/meeting_worker/pipeline.py:68–78`.
**Scope:** Current.
Cancellation during normalization is not checked before ASR, and cancellation
during ASR is not checked before diarization. The next check is after both.
Fake-adapter probes confirmed that the subsequent expensive stage still starts.
The UI can show a cancelled job while its unnecessary inference occupies the only
consumer and delays all later meetings.
**Fix:** check the durable cancellation state immediately before every expensive
stage and before exporting; separately provide interruption for running adapters.

### R017 — [P2] Pass a local Pyannote configuration file, not its directory

**Location:** `mac-worker/src/meeting_worker/diarization.py:42–51`.
**Scope:** Optional worker Pyannote backend.
The code requires the configured path to be a directory, then passes that
directory to `Pipeline.from_pretrained`. The supported Pyannote 3 loader treats
an existing file as local configuration; a directory goes through repository
resolution. Conversely, configuring the actual YAML file is rejected by the
worker's directory check. This makes the advertised local backend fail before
diarization, rather than using its provisioned local configuration.
**Fix:** accept/resolve the local YAML file and validate its referenced assets.
The contract was checked against the [Pyannote 3.3.2 loader](https://github.com/pyannote/pyannote-audio/blob/3.3.2/pyannote/audio/core/pipeline.py);
model execution was not performed.

### R018 — [P2] Supply timed GigaAM segments before assigning speakers

**Location:** `mac-worker/src/meeting_worker/asr.py:193–197`.
**Scope:** Optional worker GigaAM backend.
This adapter returns the entire recognition as one segment without start/end
times. `assign_speakers` skips untimed segments at
`mac-worker/src/meeting_worker/diarization.py:64–65`. A synthetic transcript with
two valid speaker turns therefore remained entirely unassigned although the
diarization stage succeeded. Selecting GigaAM cannot deliver the claimed
speaker-linked transcript with this adapter output.
**Fix:** return aligned timestamps, or explicitly reject this combination until
alignment exists; test speaker assignment through the adapter's actual schema.

### R019 — [P2] Check readiness for the selected diarization backend

**Location:** `mac-worker/src/meeting_worker/asr.py:83–91`.
**Scope:** Optional worker Pyannote backend.
Readiness checks Sherpa assets even when the configured backend is Pyannote.
A correctly provisioned Pyannote-only installation reports unavailable, while
Sherpa files can make readiness pass despite missing selected Pyannote assets.
The UI's availability decision therefore disagrees with the pipeline it launches.
**Fix:** dispatch dependency and asset checks by the selected backend and test
both backends with only their own assets present.

### R020 — [P2] Bound in-process model execution and provide a way to stop it

**Location:** `mac-worker/src/meeting_worker/asr.py:112,153–158,188–192`;
also `mac-worker/src/meeting_worker/diarization.py:53`.
**Scope:** Optional worker MLX/Transformers/GigaAM/Pyannote backends.
These model calls run directly inside the worker thread without applying the
configured audio timeout or a cancellable execution boundary. A model call that
hangs or exceeds its budget retains the sole inference consumer; cancelling its
async wrapper cannot terminate the running thread, and shutdown awaits it.
**Fix:** execute these adapters in managed subprocesses with deadlines and
termination, or an equivalently enforceable backend cancellation mechanism.
Test an intentionally non-returning adapter without loading a real model.

## P2 findings — station, appliance and retained Python adapters

### R021 — [P2] Prevent an old cancellation acknowledgement from erasing a retry

**Location:** `station/src/meeting_station/store.py:139–145`.
**Scope:** Current.
`apply_remote` unconditionally applies the response and clears the pending
action. If a cancellation request is in flight and the user retries locally
before its response returns, the old `cancelled` response overwrites the new
queued state and erases the retry action. A temporary-store probe ended with
`cancelled`, no action and no work after an accepted retry.
**Fix:** attach a command generation/version to remote operations and only apply
responses to the generation they acknowledge. Test retry during a delayed cancel.

### R022 — [P2] Validate speaker bounds consistently across station and worker

**Location:** `station/src/meeting_station/models.py:18–19`.
**Scope:** Current.
The station accepts individually valid bounds such as `min_speakers=3` and
`max_speakers=1`. The worker rejects their relationship in its manifest validator.
The station then treats the worker's 422 as a transient outage and retries forever
(`station/src/meeting_station/worker.py:146–150`), leaving an accepted meeting
permanently queued.
**Fix:** use the same cross-field validation at ingress and treat deterministic
manifest rejection as an actionable terminal error, not an offline retry.

### R023 — [P2] Validate export signatures across transport chunk boundaries

**Location:** `station/src/meeting_station/worker.py:75–77`.
**Scope:** Current.
Only the first HTTP chunk is retained for the export magic-byte check. HTTP
chunk boundaries do not preserve file headers: a valid PDF can start with `%P`
in one chunk and `DF` in the next. An HTTPX stream probe reproduced rejection of
that valid PDF, preventing archival and causing repeated export retries.
**Fix:** accumulate the required prefix bytes across chunks or inspect the saved
temporary file before committing it. Test one-byte and split-header chunks.

### R024 — [P2] Prevent status polling from starving new station uploads

**Location:** `station/src/meeting_station/store.py:125`.
**Scope:** Current.
Eligible submitted jobs are always ordered ahead of unsubmitted jobs. With two
in-flight jobs whose status calls each take three seconds and a two-second poll
interval, one of them is always eligible again when the other finishes. A
60-second scheduling simulation performed 20 polls and zero uploads for a new
recording. Adding work does not guarantee it will ever reach the worker.
**Fix:** separate polling and submission scheduling or use fair eligibility/age
ordering; test progress with several slow remote jobs and new arrivals.

### R025 — [P2] Do not infer meeting termination from arbitrary page text

**Location:** `deploy/meeting-browser/join.js:14`.
**Scope:** Retained meeting-room browser appliance.
The ended-meeting detector searches the page body's text before checking live
meeting controls. A chat message or caption containing “meeting has ended” can
therefore set `ended` while the call remains active. The controller consumes that
state and stops recording (`deploy/meeting-browser/controller.py:252–253`). A DOM probe reproduced this
classification with a still-present leave-call control.
**Fix:** use provider-specific call lifecycle elements/events and require a stable
terminal state; exclude chat/captions from termination detection.

### R026 — [P2] Recover or expose audio from an interrupted browser capture

**Location:** `deploy/meeting-browser/controller.py:63–65,325–327`.
**Scope:** Retained appliance capture.
An abruptly terminated FFmpeg WAV can retain its unfinalized `0xffffffff` header
lengths. Restart recovery marks the recording stopped without finalizing a
recoverable copy. The station subsequently rejects the incomplete WAV at
`station/src/meeting_station/browser.py:225–229` and leaves import pending; the
recording path does not offer a usable failed-capture download in that state.
**Fix:** retain the original, repair/validate a bounded copy on recovery, and expose
the preserved audio with an explicit failed/recovered state. Test a killed capture
with real PCM bytes and an unfinished WAV header.

### R027 — [P2] Match the station's recording duration to worker acceptance

**Location:** `station/src/meeting_station/recorder.py:38`.
**Scope:** Retained appliance recording with the current worker.
The default 512 MiB cap permits roughly 16,777 seconds of the configured PCM,
but the worker accepts at most 14,400 seconds
(`mac-worker/src/meeting_worker/config.py:51`). A four-hour-ten-minute recording
can therefore be captured and accepted by the station but is guaranteed to fail
the worker's duration check.
**Fix:** enforce a shared duration limit during capture and communicate it before
recording; test the boundary across both components.

### R028 — [P2] Use the installed Pyannote 4 result contract for RTTM output

**Location:** `internal/transcription/adapters/py/pyannote/pyannote_diarize.py:118`.
**Scope:** Retained adapter's default RTTM output path.
The pinned Pyannote 4.0.2 pipeline returns `DiarizeOutput`, which has no
`write_rttm` method. Its `speaker_diarization` member provides that operation.
Calling the adapter with its default RTTM format therefore raises after inference;
the unified Go path explicitly requesting JSON avoids this particular branch.
An API-shaped stub reproduced the failure; the [pinned upstream definition](https://github.com/pyannote/pyannote-audio/blob/4.0.2/src/pyannote/audio/pipelines/speaker_diarization.py)
confirms the contract.
**Fix:** unwrap the annotation consistently before output serialization and test
both default RTTM and JSON formats.

### R029 — [P2] Honor an explicit CPU selection in retained inference adapters

**Location:** `internal/transcription/adapters/py/pyannote/pyannote_diarize.py:54–55`;
also `internal/transcription/adapters/py/voxtral/voxtral_transcribe.py:40`
and `internal/transcription/adapters/py/voxtral/voxtral_transcribe_buffered.py:58`.
**Scope:** Retained Go/Python adapters.
These paths switch to CUDA whenever it is available, even if the caller selected
CPU; the Go Pyannote conversion also substitutes `auto` instead of forwarding the
request's device. On a GPU host where another job occupies VRAM, a CPU-targeted
request can unexpectedly fail with GPU memory exhaustion or compete with it.
**Fix:** preserve explicit device choices throughout conversion and CLI arguments;
only auto-detect for an actual `auto` request. Test CPU selection with mocked CUDA
availability.

### R030 — [P2] Preserve automatic language detection through the Voxtral boundary

**Location:** `internal/transcription/adapters/py/voxtral/voxtral_transcribe.py:118–120`;
also `internal/transcription/adapters/py/voxtral/voxtral_transcribe_buffered.py:168–170`.
**Scope:** Retained Voxtral adapters.
The Go argument builder omits the language argument when the job selects `auto`,
but the Python scripts default it to `en`. Such a job is actually conditioned on
English, which is a different contract for Russian/Kazakh input.
**Fix:** retain an explicit automatic mode and omit language conditioning when it
is selected; test the effective model arguments for `auto`, Russian and Kazakh.

### R031 — [P2] Enforce or reject Sortformer's requested speaker limit

**Location:** `internal/transcription/adapters/py/nvidia/sortformer_diarize.py:87–95`.
**Scope:** Retained Sortformer adapter.
`max_speakers` is accepted and printed, but never supplied to or enforced on the
model result. An adapter probe requesting one speaker emitted four speakers from
the stubbed model. Downstream code receives a successful result that contradicts
the submitted constraint.
**Fix:** implement a supported constraint, or reject unsupported limits before
inference and expose the model's actual capability. Test output as well as args.

### R032 — [P2] Reject nonpositive buffered transcription chunk lengths

**Location:** `internal/transcription/adapters/py/nvidia/parakeet_transcribe_buffered.py:22–25`;
also `internal/transcription/adapters/py/voxtral/voxtral_transcribe_buffered.py:25–28`.
**Scope:** Retained Python adapter CLI; normal Go callers currently pass constants.
The exposed chunk-length option has no finite-positive validation. A negative
value produces zero chunks for nonempty audio and the scripts serialize an empty
successful transcript. A direct chunking probe confirmed this behavior.
**Fix:** require a finite positive duration yielding at least one sample, and fail
if nonempty input unexpectedly produces zero chunks. Test zero/negative/tiny/NaN
values at argument validation.

## P2 findings — frontend and inactive native clients

### R033 — [P2] Survive unavailable browser storage during application startup

**Location:** `web/frontend/src/features/auth/store/authStore.ts:6`.
**Scope:** Current and retained frontend.
`localStorage.removeItem` runs unguarded at module import. The canonical entry
imports the auth interceptor even in local mode, so a browser context that denies
storage throws `SecurityError` before React mounts. `ThemeContext` has additional
unguarded storage access. This is a blank application, not merely a lost preference.
**Fix:** guard storage operations and use an in-memory/default fallback. Test
startup with storage getters/methods throwing and cover logout/theme persistence.

### R034 — [P2] Provide access to meetings beyond the newest 200

**Location:** `web/frontend/src/features/meeting-intelligence/MeetingIntelligencePage.tsx:155`.
**Scope:** Current.
The list fetch is capped at 200 and the previous load-more path disappears at that
cap. Search filters only already-loaded records; the frontend API offers no offset
although the station endpoint supports one. Once a station has 201 meetings, an
older archived meeting cannot be found or opened through the normal interface.
**Fix:** add offset/cursor pagination and server-side search, or retain an explicit
older-meetings flow. Test a station populated beyond the cap.

### R035 — [P2] Coalesce concurrent refresh-token requests

**Location:** `web/frontend/src/lib/authHelpers.ts:4–10`.
**Scope:** Retained authenticated frontend.
Each auth hook and the fetch interceptor can refresh independently. The Go
endpoint rotates the refresh cookie. If one request rotates it before a second
request carrying the old cookie is validated, the second returns 401 and its
caller clears a session that the first request just renewed. Multiple mounted
hooks and concurrent expired API requests make that interleaving reachable.
**Fix:** share one in-flight refresh promise and one timer; prevent stale refresh
failure from clearing a newer session. Test simultaneous 401 responses.

### R036 — [P2] Stop recording when the user stops sharing system audio

**Location:** `web/frontend/src/components/SystemAudioRecorder.tsx:303–305`.
**Scope:** Retained recorder interface.
The display-track ended handler closes over `isRecording=false` from the render
that started capture; the state becomes true later. Clicking the browser's Stop
Sharing control invokes that stale handler, which does not stop the recorder or
microphone. Recording can continue after the user believes capture ended.
**Fix:** use current refs or locally owned capture resources in the ended handler
and stop every related track. Test Stop Sharing, not only the app's stop button.

### R037 — [P2] Release newly acquired media after recorder startup fails

**Location:** `web/frontend/src/components/SystemAudioRecorder.tsx:383–384`.
**Scope:** Retained recorder interface.
After acquiring display/microphone streams, startup stores them through async
state updates. If audio mixing or MediaRecorder construction then throws, the
catch block calls a cleanup closure from the old render, whose streams are null.
The just-acquired microphone/display tracks and audio context remain alive.
**Fix:** keep acquisition resources in local variables/refs and clean them on every
failure and unmount path. Inject failures after each successful acquisition.

### R038 — [P2] Decode chat text with one streaming UTF-8 decoder

**Location:** `web/frontend/src/components/ChatInterface.tsx:340`.
**Scope:** Retained chat interface.
A new `TextDecoder` is created for each network chunk. A Cyrillic code point
split between chunks is decoded as replacement characters; a byte-split probe
turned `Қазақ` into corrupted text. HTTP chunk boundaries can split any code point,
so normal Russian/Kazakh responses are affected.
**Fix:** retain one decoder, call `decode(chunk, {stream: true})`, and flush once at
EOF. Test every split position in multilingual text.

### R039 — [P2] Reject unsuccessful summary responses before rendering their body

**Location:** `web/frontend/src/features/transcription/hooks/useTranscriptionSummary.ts:72–76`.
**Scope:** Retained summary interface.
The request body is consumed as summary text without checking `response.ok`.
A 400/500 JSON error from the server is displayed as a generated summary and can
be carried into subsequent copying/export instead of leaving a clear failed state.
**Fix:** validate status and the expected response contract first; preserve the
last valid summary and expose a retryable error. Test real non-2xx responses.

### R040 — [P2] Preserve template edits when saving fails

**Location:** `web/frontend/src/features/settings/pages/SettingsPage.tsx:175–186`.
**Scope:** Retained template editor.
The POST/PUT result is not checked for success, and the editor is reset/closed
afterward. A rejected or failed save therefore discards the user's only edited
template while behaving like a successful save.
**Fix:** require a successful status before clearing the draft; keep the editor
open with its content and error details on failure. Test 401, validation and 500.

### R041 — [P2] Account for failed jobs in bulk start and delete

**Location:** `web/frontend/src/features/transcription/components/AudioFilesTable.tsx:490–501`;
also `:522–531` in that file.
**Scope:** Retained job table.
Both bulk operations await `fetch` but ignore HTTP status, then clear the entire
selection. Fetch resolves for 400/409/500, so rejected starts/deletions are treated
as completed operations. Mixed-success batches lose the list of items that still
need attention.
**Fix:** inspect each response, report per-item outcomes and preserve failed items
for retry. Test a batch with one success and one deliberate server rejection.

### R042 — [P2] Pass multi-track mode into the transcription-parameter dialog

**Location:** `web/frontend/src/features/transcription/components/AudioFilesTable.tsx:1014–1019`.
**Scope:** Retained multi-track interface.
The table opens the dialog without its `isMultiTrack` prop, whose default is false.
The dialog writes `is_multi_track_enabled=false`; multi-track jobs are subsequently
rejected by the API, and editing a multi-track profile can silently reset that
mode. The table's advanced-start checks also reject this combination.
**Fix:** derive the dialog mode from the selected job/profile and define behavior
for mixed selections. Test single-track and multi-track round trips separately.

### R043 — [P2] Render segment-only transcripts when word alignment is absent

**Location:** `web/frontend/src/components/transcript/TranscriptView.tsx:127`.
**Scope:** Retained transcript interface.
The displayed rows are derived only from `word_segments`, but the nonempty guard
checks ordinary `segments`. Valid unaligned adapter output contains segments and
may omit word segments (`WordSegments` is optional in the Go result). The component
therefore renders an empty transcript despite available recognized speech.
**Fix:** fall back to segment-level rows and seeking when word timings are absent;
test both forms of the actual API schema.

### R044 — [P2] Keep a note draft until the create request succeeds

**Location:** `web/frontend/src/features/transcription/components/audio-detail/TranscriptSection.tsx:139–150`.
**Scope:** Retained notes interface.
The handler calls the non-awaitable mutation function and immediately closes and
clears the note form. A failed notes POST loses the note; the caller has neither a
successful acknowledgement nor an error handler that restores the text.
**Fix:** await `mutateAsync` or clear in `onSuccess`; preserve the draft and show
`onError`. Test a failed note save after entering nonempty text.

### R045 — [P2] Release audio visualization resources when their owner ends

**Location:** `web/frontend/src/components/audio/AudioVisualizer.tsx:67–111`.
**Scope:** Retained audio interface.
Each mount creates an AudioContext and connected nodes. Cleanup cancels animation
and observers but neither disconnects these nodes nor closes the context. Repeated
navigation retains audio processing resources and can exhaust browser context
limits, breaking subsequent playback/visualization.
**Fix:** give the graph explicit ownership, disconnect/close it at the appropriate
unmount boundary, and handle React StrictMode without recreating a media-element
source incompatibly. Test repeated mount/unmount cycles.

### R046 — [P2] Terminate quick-transcription polling when the job no longer exists

**Location:** `web/frontend/src/features/transcription/components/QuickTranscriptionDialog.tsx:124–137`.
**Scope:** Retained quick-transcription interface.
Polling handles successful status responses but ignores a persistent 404 after
server restart or job expiry. Quick jobs live in server memory, so this condition
is reachable in normal operation. The dialog stays processing and polls every
two seconds indefinitely.
**Fix:** treat not-found/expired responses as explicit terminal states, and bound
transient retries with an actionable recovery option. Test restart during a job.

### R047 — [P2] Verify claims against later corrections, not only chosen citations

**Location:** `engine/meetingbox_engine/reasoner.py:42–44`.
**Scope:** Inactive native engine.
The verifier receives only the segments cited by the extracted claim. If a later
uncited passage changes the owner or deadline, it cannot see the correction and
can approve the stale commitment. A synthetic capture of the verifier request
contained only segment 1 and omitted the later contradictory passage.
**Fix:** provide the relevant chronological discussion, including later changes,
or fail closed when that context cannot be checked. Test an explicit correction
in a segment not cited by the initial extractor.

### R048 — [P2] Reject stale HTTP snapshots after newer native WebSocket updates

**Location:** `macos/Sources/MeetingBox/AppModel.swift:240–246`.
**Scope:** Inactive Swift client.
Both HTTP refresh and WebSocket handlers replace the same local meeting snapshot.
The client model omits the server's update/report sequence needed to order them.
A delayed processing-state HTTP response can arrive after a completed WebSocket
update and overwrite the report, then persist/export the stale state.
**Fix:** include a monotonic server revision in both transports and ignore older
snapshots; test out-of-order delivery. This was statically traced, not run on a
native device.

## P2 findings — retained Go server, queue and CLI

### R049 — [P2] Recover all pending jobs, not just the channel's first 200

**Location:** `internal/queue/queue.go:475–480`.
**Scope:** Retained Go queue.
Startup recovery runs before workers start (`:129–134`), while the channel has
capacity 200 (`:104`). Every additional pending job reaches the default branch
and is dropped from recovery without changing its pending status. There is no
later database poll. Restarting with 201 pending jobs strands at least one until
another intervention/restart.
**Fix:** run a bounded durable recovery producer alongside consumers or consume
from a database-backed queue; test a backlog exceeding channel capacity.

### R050 — [P2] Preserve the previous result when enqueueing a rerun fails

**Location:** `internal/api/handlers.go:1004–1019`.
**Scope:** Retained Go API/queue.
Starting transcription clears the transcript and summary and persists `pending`
before the nonblocking enqueue. If the channel is full, the API returns 500 but
leaves the cleared job pending and not queued. Further start requests reject its
status; no running poll recovers it. The user loses access to the previous result
without obtaining the requested rerun.
**Fix:** atomically persist durable queue intent with the transition, or restore
the prior state/results when admission fails. Retain old results until replacement
is committed; test full-queue admission.

### R051 — [P2] Claim a job atomically before accepting a transcription start

**Location:** `internal/api/handlers.go:1009–1016`.
**Scope:** Retained Go API/queue.
The eligible-status read at `:1039–1055` and subsequent update are separate.
Two concurrent start requests can both read an eligible job, save pending and
enqueue its ID. Two workers then process the same output directory and database
record, while `runningJobs[jobID]` overwrites one cancellation handle.
**Fix:** use a compare-and-set status transition/durable claim and enqueue only
its winner; test concurrent starts and cancellation of the accepted execution.

### R052 — [P2] Cancel each completed job context

**Location:** `internal/queue/queue.go:219–222`.
**Scope:** Retained Go queue.
Every job creates a child context at line 197. On ordinary completion the queue
removes its tracking entry without calling the corresponding cancel function.
The long-lived parent context retains those children until server shutdown, so
memory grows with total completed jobs rather than active work.
**Fix:** call the child cancel function after recording its outcome, preferably
in a per-job helper with deferred cleanup. Do not defer cleanup inside the
long-running outer loop. Test sustained job processing and cancellation cleanup.

### R053 — [P2] Stop SSE producers before shutting down their receiver

**Location:** `internal/sse/broadcaster.go:183–190`.
**Scope:** Retained Go server shutdown.
`Broadcast` sends to an unbuffered channel without selecting shutdown. Main shuts
the broadcaster down at `cmd/server/main.go:211` before its deferred queue stop
at `:147`. An in-flight job broadcasting progress/completion after receiver exit
blocks permanently; queue shutdown then waits for that worker forever.
**Fix:** make broadcast/register sends shutdown-aware and stop producers before
their consumer. Test termination during a job that emits a final event.

### R054 — [P2] Return the created multi-track job as JSON

**Location:** `internal/api/handlers.go:550–556`.
**Scope:** Retained multi-track upload API.
The successful multipart upload branch creates the database job and returns
without writing a response body. The frontend upload hook calls `response.json`
unconditionally, so it raises a parsing error after a successful upload. Retrying
can create another job while the original remains hidden behind an error state.
**Fix:** send the documented JSON job response on this branch and test the actual
multipart endpoint together with the frontend response parser.

### R055 — [P2] Persist the folder needed to delete multi-track recordings

**Location:** `internal/api/handlers.go:536–541`.
**Scope:** Retained multi-track upload/deletion.
The multipart job stores neither `MultiTrackFolder` nor a single `AudioPath`.
Deletion checks the former, falls back to removing the latter, and ignores the
result (`:1265–1269`). Deleting an uploaded multi-track job removes its database
entry while leaving its confidential source recordings on disk.
**Fix:** persist the owned upload directory when creating the job and clean it
with checked, retryable deletion. Test that all track files disappear after a
successful delete and remain recoverable when deletion fails.

### R056 — [P2] Reject zero and invalid pagination limits

**Location:** `internal/api/handlers.go:915–917,946`.
**Scope:** Retained Go listing API.
Integer parse errors are ignored and the parsed limit is used to divide when
computing page count. `limit=0` or a nonnumeric limit therefore produces an
integer divide-by-zero panic instead of a client validation error. Gin recovery
turns it into 500, but the request is still broken; negative/unbounded values also
bypass the intended pagination contract.
**Fix:** require bounded positive page/limit values before querying and respond
400 on invalid input. Test zero, negative, nonnumeric and excessive limits.

### R057 — [P2] Reject malformed transcription parameters before changing the job

**Location:** `internal/api/handlers.go:1102–1106`.
**Scope:** Retained Go transcription API.
JSON decoding errors are logged and ignored, leaving defaults or partially decoded
parameters in place. An invalid request can therefore clear existing results,
enqueue inference, and select a different model than the caller intended instead
of returning 400.
**Fix:** reject malformed/nonempty request bodies before any state mutation; if
empty-body defaults are intentional, handle only that specific case. Test invalid
JSON and type errors on a completed job and assert no mutation or enqueue.

### R058 — [P2] Set the media authentication cookie on first registration

**Location:** `internal/api/handlers.go:1702–1711`.
**Scope:** Retained Go/browser authentication.
Registration issues a JWT in JSON and a refresh cookie but omits the access
cookie that login sets. Fetch calls can use the returned bearer token, whereas
the audio element relies on cookies (`web/frontend/src/components/audio/EmberPlayer.tsx:255–257`). A newly registered
user can appear logged in yet receive 401 for playback until another login/refresh
establishes the missing cookie.
**Fix:** share session establishment between register, login and refresh; test
native media requests immediately after registration, without an extra refresh.

### R059 — [P2] Build completion webhooks from the committed transcription

**Location:** `internal/transcription/unified_service.go:159–165`.
**Scope:** Retained Go integration.
The completion callback captures the job loaded before inference. Saving the
transcript updates the database (`:883–891`) without updating that captured
object. A completed webhook therefore sends nil or an earlier transcript even
though a subsequent API fetch returns the new result.
**Fix:** reload the committed job or pass the successful result directly when
constructing the webhook. Test the complete processing-to-webhook path, asserting
the callback's transcript rather than merely HTTP delivery.

### R060 — [P2] Return immutable quick-job snapshots outside the mutex

**Location:** `internal/transcription/quick_transcription.go:112–125`.
**Scope:** Retained quick-transcription API.
The getter releases its read lock while returning the shared job pointer.
The HTTP handler serializes it concurrently with processing updates under the
write lock. The serializer is outside that lock, creating a real data race and
potentially inconsistent status/result responses. Submission also returns the
same pointer after starting its processing goroutine.
**Fix:** copy a complete response snapshot under the lock for both paths; test
concurrent polling/processing with Go's race detector when Go is available.

### R061 — [P2] Apply admission control to quick-transcription inference

**Location:** `internal/transcription/quick_transcription.go:103–106`.
**Scope:** Retained quick-transcription API.
Every accepted request starts a new processing goroutine, bypassing the bounded
normal transcription queue. Each can launch/load its own model using a background
context. A burst of quick requests can therefore exhaust RAM/VRAM and starve normal
meetings despite configured queue limits.
**Fix:** route quick jobs through bounded inference admission and enforce a job
deadline/cancellation contract. Test concurrency limits without loading models.

### R062 — [P2] Make temporary transcription retention survive restart

**Location:** `internal/transcription/quick_transcription.go:249–254`.
**Scope:** Retained quick-transcription storage.
Cleanup walks only the in-memory job map, which is empty after restart, and
removes `<quickDir>/<id>_output` although the unified processor writes results
under the configured transcripts directory. The temporary database deletion is
also a GORM soft delete. Thus expired recordings/results can remain indefinitely
despite the six-hour temporary-job contract.
**Fix:** persist expiry/owned artifact paths, reconcile them at startup, and delete
the actual files and intended database records. Test expiry both with and without
an intervening server restart.

### R063 — [P2] Do not mark a quick transcription complete after losing its result

**Location:** `internal/transcription/quick_transcription.go:179–191,203–206`.
**Scope:** Retained quick-transcription API.
After successful inference, result lookup and temporary transcript write errors
are ignored. The database entry is then deleted and status becomes completed even
if reading the temporary file fails. A full disk or failed lookup produces a
successful job with no transcript, with its original result no longer available
through normal job lookup.
**Fix:** carry the fetched result directly into the quick-job snapshot, propagate
lookup/write failures, and retain recoverable output until publication succeeds.

### R064 — [P2] Drain summary content before treating a closed error channel as done

**Location:** `internal/api/summarize_handlers.go:104–110`.
**Scope:** Retained Go summarization.
The receive from the error channel does not check `ok`. Providers close this
channel when finishing while content may still be buffered. A select can choose
the closed error channel, obtain nil and return, persisting only the prefix already
read. Normal successful generation can therefore be silently truncated. Conversely,
choosing closed content first can miss a pending error.
**Fix:** coordinate completion across both channels or use one typed event channel;
drain content and handle the terminal error exactly once. Test buffered chunks
remaining when the producer closes both channels.

### R065 — [P2] Flush the gzip stream when flushing progressive responses

**Location:** `pkg/middleware/compression.go:28–40`.
**Scope:** Retained Go chat/summary streaming.
The wrapper overrides writes but inherits the underlying ResponseWriter's Flush.
Consequently endpoint flushes do not flush the gzip writer. The middleware decides
compression before the endpoint sets streaming response headers and can use the
JSON request content type, so these POST streams are compressed. Clients can see
no text until compression fills or the whole response closes.
**Fix:** implement Flush to flush gzip before the underlying writer, or explicitly
exclude streaming routes before wrapping. Test first-chunk arrival before completion.

### R066 — [P2] Handle an empty fallback chat response without dereferencing nil

**Location:** `internal/api/chat_handlers.go:638–640`.
**Scope:** Retained Go chat.
The error branch covers nil responses and empty choices as well as non-nil errors,
but always calls `err2.Error()`. A provider returning HTTP 200 with an empty choices
array and no decode error therefore causes a panic while handling the fallback.
**Fix:** distinguish transport/provider errors from an invalid empty response and
return an explicit error for the latter. Test empty choices and nil response.

### R067 — [P2] Count transcript context once when budgeting chat requests

**Location:** `internal/api/chat_handlers.go:503–508,520–538`.
**Scope:** Retained Go chat.
The token budget starts with transcript tokens, then adds the first user message
after prepending that same transcript. A roughly 2,500-token transcript with a
short question can therefore be rejected against a 4,096-token context even though
the actual assembled input fits. This incorrectly disables questions about longer
meetings before calling the provider.
**Fix:** assemble the exact outbound messages and count each once, reserving the
required output budget. Test a transcript that fits once but not twice.

### R068 — [P2] Match installer authentication arguments to the actual CLI

**Location:** `internal/api/cli_install_handlers.go:125`.
**Scope:** Retained CLI installer.
The token-provided branch executes `login --token-only`, but the login command
defines `--server` and no `--token-only` flag (`internal/cli/login.go:26–27`). The
generated installer exits on that unknown flag and never completes authentication.
**Fix:** implement a secure supported token-input path or generate only arguments
the CLI accepts; test the generated install command against the actual parser.

### R069 — [P2] Bound CLI upload memory and network lifetime

**Location:** `internal/cli/client.go:29–35,58–59`.
**Scope:** Retained upload CLI/service.
Each upload first copies the entire recording into a bytes buffer and uses an
HTTP client without a deadline or request cancellation. The watcher can start
multiple uploads. Large recordings multiply resident memory, and a peer that
accepts a connection but never responds can retain those buffers/goroutines
indefinitely, exhausting a continuously running capture machine.
**Fix:** stream multipart bodies, use context/deadline-aware requests and bound
concurrent uploads. Test a large synthetic stream and a stalled local receiver.

### R070 — [P2] Make recording deletion recoverable across database failures

**Location:** `internal/api/handlers.go:1265–1269`.
**Scope:** Retained Go deletion API.
The source recording is removed before the database deletion and related cleanup,
which subsequently use the request context. If the database operation fails or
the client disconnects after filesystem deletion, the still-visible job has lost
its source. Other cleanup failures are logged/ignored, allowing partial deletion
to be presented as complete.
**Fix:** record a durable deletion intent, transactionally update database state,
then perform idempotent checked artifact cleanup with retries. Test database
failure and disconnect between the state transition and filesystem cleanup.

## P3 findings

### R071 — [P3] Normalize carriage returns before escaping calendar text

**Location:** `mac-worker/src/meeting_worker/exports.py:89`.
**Scope:** Current ICS export.
Escaping replaces LF but leaves CR. A valid task containing Windows CRLF line
endings consequently emits a bare carriage return inside the ICS property;
a synthetic export produced `SUMMARY:First\r\\nSecond`. Calendar consumers can
reject or misparse that entry.
**Fix:** normalize CRLF and lone CR to LF before applying ICS escaping; test all
three line-ending forms with an independent calendar parser.

### R072 — [P3] Require finite timeout and duration settings

**Location:** `mac-worker/src/meeting_worker/config.py:79–84`.
**Scope:** Current worker configuration.
The positive-value validator checks only `value <= 0`; NaN passes because that
comparison is false, and positive infinity also passes. Configuration probes
accepted nonfinite values for the float limits, defeating duration comparisons or
passing invalid/unbounded timeout values to downstream libraries.
**Fix:** require `math.isfinite` as well as positivity and practical upper bounds
where appropriate. Test environment parsing with `nan`, `inf` and `-inf`.

## Verification and evidence boundaries

`python3 scripts/harness.py doctor` exited 0. Installed tools include Python
3.14.6, Node 24.12 and npm 11.6.2. Go, Docker, FFmpeg, Ollama and provisioned model
weights were unavailable for this review. No dependencies, model weights or
datasets were installed/downloaded, and no external inference API was enabled.

The final `python3 scripts/harness.py verify` exited 0 after branding changes:
33 harness regressions, frontend production build, 171 backend/local HTTP tests,
frontend lint and two actual browser review/export workflows. Raw receipt:
[verification-20260923T102002343181Z-2628c8.json](verification/review-20260923/verification-20260923T102002343181Z-2628c8.json).
The six raw logs are preserved beside that receipt as `.txt` files so the repository's
log exclusions do not omit them; their bytes are unchanged. The receipt's original
`reports/` paths describe where the harness generated them.
The retained frontend also built successfully with
`npm --prefix web/frontend run build -- --outDir ../../.local/legacy-brand-build`.
`git diff --check` passed. These checks cover supplied synthetic transcripts and
reports; they do not establish speech recognition accuracy or closed-environment
production acceptance.

An initial sandboxed verification exited 1 because local HTTP/browser tests could
not bind sockets. After approved execution outside that restriction, both full
runs passed. That environment failure is not counted as a product defect.

Review probes used synthetic objects, temporary databases, controlled HTTP streams,
existing rendering dependencies and API-shaped adapter stubs. No real meeting
data or credentials were used. Go findings were checked against surrounding source,
callers and existing tests, but Go compilation/race tests could not run. No live
ML inference, Radxa/device capture, native Swift execution, container deployment,
or sustained-load acceptance was performed. Adapter stubs establish interface
failures only. Hardware crash durability findings are ordering analyses, not
claims that a power-loss laboratory test was performed.

Coverage included current station/worker routes, persistence, locks, cancellation,
retries, archives, review revisions, exports, model configuration and adapters;
React upload/record/review/auth/transcript/summary/chat/settings flows; appliance
browser/capture/deployment/backup configuration; retained Go routing/authentication,
repositories, job lifecycle, queue/SSE/LLM streaming, subprocess adapters,
dropzone/webhooks/CLI; and inactive engine/backend/native synchronization. Existing
tests and configured checks were inspected for the relevant contracts. This is a
source review with the execution limits above, not proof that unlisted paths are
defect-free.

## Requested capabilities that remain requirements gaps

These are separate from the defects above. Missing proposed features are not
reported as regressions in code that never claimed to implement them.

| Requested capability | Observed boundary and next implementation contract |
| --- | --- |
| Secretary approval and issued minutes | Current code already supports corrections, finding review states, recovered actions, source links and immutable review bundles/history. It does not yet establish a distinct organizational issuance gate with authenticated editor identity and a required reason for each post-issuance amendment. Define draft versus issued minutes and the unresolved-item policy. |
| Assignment, acknowledgement, reminders and completion confirmation | Extracted actions and ICS export are not a persistent execution lifecycle or reminder-delivery service. Add durable task identity, allowed transitions, assignee/supervisor, confirmed due date, calculated overdue state and a local delivery queue. |
| Confirmed cross-meeting continuity | Current actions are report-local. Add explicit project selection and a human-confirmed match to a stable task; retain separate evidence for proposed owner/date/status changes. A completion claim must remain distinct from verified completion. |
| Secretary, assignee and manager authorization | A station token or the retained single-admin login is not project/role-based access. Add backend object authorization for reports, tasks, evidence/audio ranges and exports before distributing accounts. A reviewer string in history is not authenticated identity. |
| Organizational templates and internal integration | Existing exports can seed an adapter contract; no verified customer document-management contract or template conformity is established. Define stable IDs, revision/approval state and source references, and exercise a clearly labeled local adapter. |
| Radxa resilience | The architecture separates capture/archive from inference. Recovery must additionally cover the defects above, including interrupted capture and remote command races; no physical station power-loss test was performed. Concept enclosure images are not validated CAD/manufacturing specifications. |

## Fix order and disposition

Address current source packaging and P1 worker defects first, then current station
retry/fairness/export failures. If the retained Go service is part of the evaluated
deployment, its P1 XSS, recording loss, authentication, shell/SQL injection,
credential logging and temporary-file defects are release blockers for that path.
Explicitly exclude unused retained entry points from the deployment until fixed.
Add targeted regression tests for each selected fix, then rerun the existing
verification and a clean-checkout build. Actual RU/KZ/mixed-audio-to-export
acceptance remains necessary before claiming the mandatory speech capabilities.

The separate authorized branding cleanup replaced obsolete logos, visible
interface names and PWA display metadata with Meeting Station. It did not remove
licenses, attribution, source history, existing executable names or compatibility
identifiers. None of the 72 findings was marked fixed by that cosmetic change.
