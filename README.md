<p align="center">
  <img src="docs/assets/readme/hero.svg" alt="Meeting Station — private meetings, traceable decisions. Russian, Kazakh and mixed speech. Local models, human review and export." width="1200" />
</p>

<p align="center">
  <a href="#how-it-works">How it works</a> ·
  <a href="#security">Security</a> ·
  <a href="#installation">Installation</a> ·
  <a href="#verification">Test results</a> ·
  <a href="docs/REQUIREMENTS.md">Case requirements</a>
</p>

# Meeting Station

**Turn a meeting recording into minutes you can check.** Meeting Station prepares a transcript, summary and task table. The secretary opens a task's source passage, listens to the audio, corrects the owner or deadline, and saves a reviewed version for export.

<p align="center">
  <img src="docs/assets/readme/samruk-kazyna-logo.jpg" alt="Samruk-Kazyna, the hackathon case owner" width="110" /><br />
  <sub>Built for the Samruk-Kazyna meeting-minutes challenge · MEET-BOX project</sub>
</p>

The problem is familiar: someone writes the minutes by hand, a deadline changes during the conversation, and the final task list loses who promised what. The [case](docs/CHALLENGE.md) adds an essential constraint: Russian, Kazakh and mixed-language meetings must be processed without sending audio or text to external AI APIs.

Our approach keeps the recording, models and review on local equipment. **The secretary works from a traceable draft instead of reconstructing the meeting from scratch.**

## How it works

1. **Bring in the meeting.** Upload audio/video, or use a microphone connected to the room station. Notify participants before recording and AI transcription begin.
2. **Transcribe locally.** Whisper turns audio into text. Enable Sherpa speaker separation to add anonymous speaker labels; the reviewer connects those labels to people.
3. **Prepare the draft.** A local Qwen model extracts decisions, tasks, stated owners and deadlines. The report also includes a summary, topics, open questions and risks.
4. **Check the evidence.** Source links open the supporting transcript passage and seek the audio player to its timestamp. The original transcript remains available.
5. **Resolve the details.** Correct a task, reject it or add a missed assignment from a source passage. Save a revision with the reviewer name, time and reason for the changes.
6. **Take the result with you.** Export that revision as **PDF, DOCX, JSON, CSV or a calendar task file**. The same reviewed records feed each format.

Processing runs after capture finishes. The appliance also has a browser for online meetings, subject to host admission and account permissions. Importing a text transcript skips speech recognition and speaker separation.

### A changed assignment should stay one assignment

> “Dana will send the report on Friday.”  
> Later: “Timur will take over the report. The deadline is Monday.”

The extraction pipeline reads the discussion in order and checks later corrections against earlier tasks. The intended result is one task for Timur, with Monday preserved as the spoken deadline. The secretary can confirm the actual calendar date while reviewing the source.

Unspecified owners and deadlines stay empty. A local model checks findings against their cited passages and exposes review issues or an unavailable check. These checks can miss errors; the source audio and human correction remain part of the workflow.

[Extraction and checks](mac-worker/src/meeting_worker/pipeline.py) · [Review contract](docs/ARCHITECTURE.md#human-review-contract) · [Report fields](mac-worker/src/meeting_worker/protocol.py)

<details>
<summary><strong>See the interface: import → transcript → review → saved minutes</strong></summary>

These are actual application screenshots using explicitly synthetic meeting data. The capture exercised local APIs, editing, persistence and reload; it did not run speech or language models. Click an image to inspect it.

<table>
  <tr>
    <td width="50%"><a href="docs/assets/readme/01-import.png"><img src="docs/assets/readme/01-import.png" alt="Import a recording and choose meeting language and speaker separation" width="480" /></a><br /><strong>1. Import the meeting</strong></td>
    <td width="50%"><a href="docs/assets/readme/02-transcript.png"><img src="docs/assets/readme/02-transcript.png" alt="Russian and Kazakh transcript with speaker labels and source timestamps" width="480" /></a><br /><strong>2. Read the source</strong></td>
  </tr>
  <tr>
    <td width="50%"><a href="docs/assets/readme/03-review.png"><img src="docs/assets/readme/03-review.png" alt="Secretary corrects an assignment's owner and date beside its supporting quote" width="480" /></a><br /><strong>3. Correct and review</strong></td>
    <td width="50%"><a href="docs/assets/readme/04-reviewed-minutes.png"><img src="docs/assets/readme/04-reviewed-minutes.png" alt="Saved report revision with review history and document export" width="480" /></a><br /><strong>4. Save and export</strong></td>
  </tr>
</table>

[Capture receipt and image provenance](docs/assets/readme/README.md)

</details>

## Two devices, one local workflow

A **room station** is a small computer that stays connected to the meeting-room microphone. It records the meeting, holds the queue and keeps the archive. We use a **Radxa Cubie A7A**, a single-board computer, for that role.

A **local inference worker** is the computer that does the heavier AI processing. In the documented installation, it is a Mac on the same private network. The browser talks to the station; the station sends work to the Mac and stores the returned reports.

![The browser connects to the room station over HTTPS. The station keeps the archive and exchanges jobs with the local Mac worker over mutual TLS. Results return for human review.](docs/assets/readme/local-architecture.svg)

| Device in the documented installation | Responsibility |
| --- | --- |
| **Radxa Cubie A7A** · 6 GB RAM · Debian 11 | Web interface, microphone recording, persistent queue, meeting archive and online-meeting browser. |
| **MacBook Air M5** · 16 GB memory | FFmpeg audio preparation, Whisper speech recognition, optional Sherpa speaker separation, Qwen3.5 4B and document generation. |

**Why separate them?** Recording and archive access stay with the room station; model memory and compute belong on the worker. A running, unlocked station retains queued recordings when the Mac is unavailable and resumes processing when it reconnects. Completed reports remain available from the station.

After a station reboot, automatic vault unlocking needs the Mac logged in, awake and reachable. The [runbook](docs/RUNBOOK.md) covers startup and recovery. A [one-computer installation](docs/LOCAL_SETUP.md) runs both roles locally for evaluation without buying a board.

<details>
<summary><strong>The room station: enclosure concept and rotating view</strong></summary>

<table>
  <tr>
    <td width="50%"><img src="docs/assets/readme/station-enclosure-concept.png" alt="Concept enclosure for the room recording station, with Samruk-Kazyna case branding" width="480" /></td>
    <td width="50%"><img src="docs/assets/readme/station-turntable.gif" alt="Animated concept of the station enclosure" width="480" /></td>
  </tr>
</table>

Participant-supplied design concepts, not validated CAD or evidence of hardware performance. [Artwork provenance](docs/assets/readme/README.md).

</details>

[Component architecture](docs/ARCHITECTURE.md) · [Appliance architecture](docs/APPLIANCE_ARCHITECTURE.md) · [Station service](station/) · [Inference worker](mac-worker/)

## Security

**Local processing is the starting point. The configured appliance also protects the network links and stored meeting data.**

![Security controls: HTTPS for the browser, mutual TLS between the devices, encrypted archive contents and filenames, and locally installed inference models.](docs/assets/readme/security.svg)

- **Browser → station: HTTPS.** A private certificate authority establishes trust in the station. Secure cookies, a same-origin content policy and uncached API responses protect the browser session.
- **Station ↔ worker: mutual TLS.** Each device proves its identity with a certificate, alongside a separate worker token. The station checks the worker's certificate authority and address; the worker requires a trusted client certificate. Invalid identities are rejected, with no HTTP fallback.
- **Archive at rest: encrypted contents and filenames.** The appliance uses a gocryptfs vault for recordings, transcripts, exports, databases, browser state and credentials. Startup guards keep services stopped while it is locked. The vault password stays off the board; the documented Mac uses FileVault.
- **Models: local and explicit.** Ollama listens on the Mac's loopback interface. Models are installed before use; this pipeline has no external AI fallback. Worker requests reject public destinations, redirects and environment proxies.

[Security and recovery guide](docs/SECURITY.md) · [Device certificate generation](scripts/create-worker-pki.py) · [HTTPS configuration](deploy/radxa/Caddyfile.station.example) · [Vault startup guard](deploy/radxa/unlock-vault.sh)

These are appliance deployment controls: the one-computer launcher uses loopback HTTP and does not provision an encrypted vault. Downloads happen during setup; online meetings still connect to their provider. Keep certificate verification enabled and renew the 90-day device certificates before expiry.

Encryption protects traffic and the locked archive. An administrator or malware on an unlocked device can still access data. The current shared station token is not per-person access control, and the review history is not a tamper-proof audit log.

## Installation

Choose the deployment you need. Model files, certificates and private device configuration are not bundled in the repository.

| Start here | What you need | Guide |
| --- | --- | --- |
| **One computer** | Python 3.11+, Node 22.12+, FFmpeg, local speech/diarization models and Ollama. The model setup uses Python 3.12. | [Local installation](docs/LOCAL_SETUP.md) |
| **Room station + Mac** | The same local inference resources, a provisioned Radxa, the Go toolchain from `go.mod`, and device certificates. | [Station installation](docs/STATION_SETUP.md) |

For the one-computer path, follow the guide to install dependencies, build the interface, initialize configuration and provision models. Then run from the repository root:

```sh
.venv/bin/python scripts/run-local.py doctor
.venv/bin/python scripts/run-local.py start
```

Open **http://127.0.0.1:8766/meeting-intelligence** and pair with the generated **station** token. Upload a non-sensitive recording, enable speaker separation, check the source passages and inspect the exported PDF/DOCX. Missing models are reported explicitly.

[Model provisioning and licenses](docs/MODEL_SETUP.md) · [Setup troubleshooting](docs/LOCAL_SETUP.md#checks-and-troubleshooting)

## Verification

The **23 September 2026 foundation-repair checks** recorded the following results. [Commands, logs and source manifest](docs/verification/foundations-20260923/README.md) identify the tested code and environment.

| Check | Recorded result |
| --- | --- |
| Station and worker tests | **237 passed** |
| Browser regressions | **33 passed** |
| Real local review/export workflows | **2 passed**, including independent PDF/DOCX content checks |
| Retained Python / native / harness suites | **95 / 16 / 34 passed** |
| Retained Go implementation | Full **race test suite passed** |
| Frontend | Station and retained builds passed; lint passed |

Reproduce with `make verify`; the retained entry points additionally use `make verify-go` and `make verify-native` on macOS. Dependencies and test Chromium must already be installed. These checks exercise application behavior with synthetic data and simulated inference; they do not measure multilingual recognition quality.

<details>
<summary><strong>Earlier physical-device measurements · 11 September 2026</strong></summary>

| Recorded check | Result |
| --- | --- |
| 120-second synthetic English recording → local processing → four exports, through HTTPS, mTLS and encrypted storage | **62.567 seconds** |
| Radxa reboot → website, archive, worker link and meeting browser restored | **80.745 seconds**; saved PDF unchanged |
| TLS negative checks | Missing certificate, untrusted CA, wrong server name and wrong certificate purpose rejected |

These are historical results on the two devices above, not a fresh measurement of the current repair tree. A clean English fixture and a single timed run do not establish Russian/Kazakh accuracy or long-meeting throughput.

[Hardware validation log](docs/VALIDATION.md) · [Security measurements](docs/SECURITY.md#verified-boundaries-and-remaining-limits) · [Recognition measurements](docs/ACCURACY.md)

</details>

## What still needs validation

Representative Russian, Kazakh and mixed-speech evaluation, overlapping voices, and an inference run with the internet physically disconnected remain open. Speaker labels distinguish voices; a person must confirm their names. Google Meet capture is documented in the earlier hardware log; live Zoom and Teams admission remain unverified.

In-app corrections, revision history and PDF/DOCX export are implemented. Formal issuance, personal access roles, automatic reminders, cross-meeting task tracking and document-management integration remain future work. Calendar export creates a file; it does not send notifications.

[Full case map](docs/REQUIREMENTS.md) · [72-finding repair register](docs/FOUNDATION_FIXES.md) · [Submission evidence](docs/SUBMISSION_NOTES.md)

## License and attribution

[MIT](LICENSE). Meeting Station builds on the Scriberr backend foundations and retains their copyright and license notices. The station, local worker and review workflow are described in the [contribution and attribution record](docs/ATTRIBUTION.md). Model and artwork licenses apply separately. Samruk-Kazyna branding identifies the hackathon case owner.

For a trial or installation question, open an issue with the meeting languages and equipment you need to support. Keep recordings, transcripts and credentials out of public issues.
