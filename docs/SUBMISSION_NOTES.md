# Submission evidence and remaining limits

Updated 2026-09-23. Scope: improve the participant's earlier local Meeting Station
for the supplied Samruk-Kazyna case. This is source submission preparation;
nothing was pushed, published or deployed to an external service.

## Origin and useful change

Baseline: `849f2224f93209feb9ce408f4ebd898026a9c97d`, cloned from the participant's
[repository](https://github.com/Eraly-ml/meeting-intelligence). The inherited
application already had local ASR/model adapters, diarization, extraction,
citations, queues and a hardware deployment. Those are not claimed as new work.

The secretary can identify anonymous voices, correct/confirm/reject findings,
recover an omitted task from its transcript passage, and distribute one consistent
saved revision. Changes preserve source words/citations,
record who supplied the review label and reject stale conflicting edits. A local
setup no longer depends on the earlier Radxa/Go installation. Both DOCX and PDF
are available with Unicode and visible evidence/review status.

## Verification record

The application was consolidated into the existing harness repository on
2026-09-23. There is now one source root. `python3 scripts/harness.py verify`
passed from that root: structure check, **33 harness tests**, **171 backend/local
HTTP tests**, frontend build, lint, and **two real browser workflows** including
downloaded PDF/DOCX content checks. The 194 tracked files in `station/`,
`mac-worker/` and `web/frontend/` match imported checkpoint `fa15a85` byte for byte.
The local Python environment was repointed to the root without installing new
dependencies; `pip check` passed. The original Git bundle was independently verified.

Current root receipt: [verification JSON](verification/verification-20260923T095442120502Z-b47d75.json).
Corresponding raw logs use the same timestamp in [verification/](verification/).
This root consolidation is left uncommitted for the user; the checkpoint below
describes the earlier product implementation, not the root's current Git HEAD.
Protocol accounting, including the human-activation deviation, is in
[DEVELOPMENT.md](DEVELOPMENT.md).

Baseline: 108 backend tests passed on this machine. One initial run was stopped
by the execution sandbox denying the mutual-TLS test's localhost bind; the
authorized rerun passed all 108. Frontend build/lint also passed before changes.

Current acceptance uses:

```sh
MI_RUN_LOCAL_HTTP_TESTS=1 .venv/bin/python -m pytest station/tests mac-worker/tests -q
VITE_MEETING_STATION=true VITE_MEETING_LOCAL=true npm --prefix web/frontend run build
npm --prefix web/frontend run lint
.venv/bin/python scripts/check-ui.py
.venv/bin/python -m pip check
```

Initial implementation acceptance on 2026-09-23, before root consolidation:

| Check | Result | Exit |
| --- | --- | --- |
| Backend, including real local HTTP startup/authentication/shutdown | 171 passed in 5.07 s | 0 |
| Local frontend production build | Passed | 0 |
| Frontend ESLint | Passed | 0 |
| Real browser correction and missed-action recovery | 2 passed in 5.5 s; downloaded DOCX/PDF contents independently checked | 0 |
| Python dependency consistency (`pip check`) | No broken requirements | 0 |

The checked implementation is commit `59da4ba` (only submission documentation,
CI and the packaging script were finalized afterward). Raw build/test/browser logs
and the command receipt are in [verification/](verification/). The earlier receipt records
commands as executed from the then-parent harness; the commands above run from this
repository. The backend suite reported one third-party AnyIO deprecation warning;
the browser runner reported an environment color-setting warning. Neither was
treated as a product accuracy result or hidden failure.

The browser check starts real station/worker processes and the compiled React
interface against temporary, explicitly synthetic reports. It pairs, edits,
recovers an omitted action, retries, reloads and downloads actual documents; the downloaded Word XML/PDF text is
checked independently. No API responses are mocked in the browser. It does not
exercise speech recognition or language-model inference. Backend transport
fixtures likewise verify contracts and failure handling, not semantic accuracy.

Saved acceptance artifacts: [actual interface screenshot](verification/synthetic-review-desktop.png),
[corrected DOCX](verification/synthetic-review.docx), [corrected PDF](verification/synthetic-review.pdf),
[recovered-action DOCX](verification/synthetic-missed-action.docx) and
[recovered-action PDF](verification/synthetic-missed-action.pdf). These use the
synthetic supplied transcript, not recognized customer audio.

The six adversarial RU/KZ/mixed verifier fixtures were frozen before their change:
`mac-worker/tests/fixtures/protocol_verification.json`, SHA-256
`c41d1b1272b9a9ac5dc99f886bd10eac3de763f53fbd4654e00935fac3c429c0`.
Fifteen new verifier regressions failed against the old implementation and passed
after the fix. Review acceptance cases are recorded in [REVIEW_CASES.md](REVIEW_CASES.md).
The omitted-action regression was also specified before its implementation: the
old API rejected the request with HTTP 422. Its canonical synthetic action has
SHA-256 `a892bb74d96d8299cab738fe98f0e724c3fd2fef80c25a8bcdc5d3d6805f2208`
(sorted JSON, UTF-8, compact separators `(',', ':')`, `ensure_ascii=False`; see
`MISSED_ACTION` in `mac-worker/tests/test_review.py`).

Core environment: macOS arm64, Python 3.14.6, Node 24.12.0, npm 11.6.2.
Frontend lockfile preserved and extended with Playwright 1.63.0; core Python
versions captured in [validation.lock](../requirements/validation.lock).
Provisioning on Python 3.12/Linux and the added GitHub workflow were not executed
in this local session. No passing CI run is claimed.

## Boundaries that matter to reviewers

- No speech, diarization or language-model weights were downloaded or executed
  here. Current Russian/Kazakh/code-switch recognition and real speaker/owner
  accuracy remain unmeasured. Previous hardware results in historical docs are
  not results of this session.
- Verification sees the complete chronological transcript only when it fits the
  configured context budget. Larger inputs receive an explicit warning and
  unverified findings requiring human review. Extraction and local model review
  can still omit facts or be wrong; source linkage is not proof of truth.
- A participant name is an explicit human mapping, not biometric identification.
  A reviewer name is a self-reported label under a shared station token, not
  individual authentication or an immutable compliance log.
- The standalone path supports recording upload and existing transcripts.
  Live Teams/Zoom/Meet capture remains a separate appliance deployment and was
  not exercised with real services here. An upload extension test does not prove
  codec support on an unprovisioned ffmpeg installation.
- ICS exports tasks; scheduled reminders, automated mailing, task execution
  status dashboards and full ECM integration are not implemented by this change.
- Cloud inference fallback is absent. Source inspection/tests enforce local
  endpoint/proxy/redirect boundaries; a complete model run with WAN disconnected
  still needs checking on provisioned hardware.
- Before customer production use: establish per-user authorization, retention
  and deletion, encrypted disk/backups, operational monitoring and customer data
  acceptance. The present checks do not certify production readiness or legal
  compliance. No 100x speed/accuracy or measured secretary time saving is claimed.

## Source package

From a clean committed checkout, `python3 scripts/package-submission.py` creates
a source ZIP and a JSON receipt under `.local/packages/`, with its commit and
SHA-256. Commit the consolidated root before generating a fresh package; the old
ZIP is retained only in the ignored local migration backup. Packaging excludes two
old checked-in compiled binaries, the historical startup log, an unused inherited
AMI-labelled audio clip, and non-example environment files. Dependencies, models
and runtime archives are not bundled.
Install/provision using the README and [MODEL_SETUP.md](MODEL_SETUP.md).
