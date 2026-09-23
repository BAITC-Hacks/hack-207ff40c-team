# Run Meeting Station on one computer

This path runs the existing Python archive and inference worker with the React
interface on `127.0.0.1`. It does not require Radxa, Go, Caddy, Docker, an account
server or cloud inference. It supports uploaded recordings and pasted
transcripts. The Radxa microphone and online-meeting browser are separate
appliance features; their absence does not prevent file import.

The local interface uses a generated station pairing token. API requests still
require that token. A separate worker token stays in the Python processes. This
mode is restricted to loopback; use [RUNBOOK.md](RUNBOOK.md) for the deployed LAN
path and its mutual TLS configuration.

## 1. Install application dependencies and build the interface

From a fresh checkout, use Python 3.11 or newer and Node 22.12 or newer. Python
3.12 is the provisioned model environment described in the worker documentation;
compatibility of optional native model packages must be checked for your Python
and platform. The pinned base API/export/test environment was checked on Python 3.14.6; the model provisioning recipe uses Python 3.12 and still requires an environment-specific acceptance run.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements/validation.lock
npm --prefix web/frontend ci --ignore-scripts
VITE_MEETING_STATION=true VITE_MEETING_LOCAL=true npm --prefix web/frontend run build
.venv/bin/python scripts/run-local.py init
```

Installation requires internet access; inference does not use cloud providers.
Python packaging executes its build backends. `npm ci --ignore-scripts` uses the
committed lockfile without dependency installation hooks. The build requires the
platform packages from that lockfile; do not omit optional dependencies.
`run-local.py` never installs software or downloads models. The two frontend flags
produce build metadata that the local host checks, preventing an accidental
upstream/account-server build from being served as the local interface.

## 2. Provision inference assets

Install **ffmpeg**, **whisper.cpp** with a multilingual Whisper GGML model, and
**Ollama** with the local `qwen3.5:4b` model before using inference. Follow [MODEL_SETUP.md](MODEL_SETUP.md) for explicit provisioning commands, pinned sources and model checks. The [worker README](../mac-worker/README.md) describes the earlier hardware setup. Model files are not included in Git.
Do not use an English-only Whisper model for Russian/Kazakh recordings.

During provisioning, a separately installed Ollama can download the configured
model with `ollama pull qwen3.5:4b`. This is an explicit one-time download, not a
runtime fallback. Review its model license and allow enough disk/memory for the
speech and language models. Start Ollama in a separate terminal:

```sh
OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 ollama serve
```

Edit `.local/single-machine/config.json`; all values are strings:

```json
{
  "MI_WHISPER_BINARY": "/absolute/path/to/whisper-cli",
  "MI_WHISPER_MODEL": "/absolute/path/to/ggml-large-v3.bin",
  "MI_FFMPEG_BINARY": "/absolute/path/to/ffmpeg",
  "MI_OLLAMA_URL": "http://127.0.0.1:11434",
  "MI_OLLAMA_MODEL": "qwen3.5:4b",
  "MI_ENABLE_DIARIZATION": "true",
  "MI_PDF_FONT": "/absolute/path/to/a/Unicode-font.ttf"
}
```

Use a Unicode font containing Cyrillic and Kazakh letters. On macOS, an available
choice is `/System/Library/Fonts/Supplemental/Arial.ttf`; check that it exists on
your machine. The PDF renderer also checks installed fallback fonts.

Speaker separation is required by the current case. To enable it, install
`.venv/bin/python -m pip install -e 'mac-worker[local]'`, set
`MI_ENABLE_DIARIZATION` to `"true"`, and add the `MI_SEGMENTATION_MODEL` and
`MI_EMBEDDING_MODEL` local ONNX paths documented in the worker README. Optional
`MI_WHISPER_MODEL_EN` and `MI_WHISPER_VAD_MODEL` accept separately provisioned
model files. Missing speaker models are reported explicitly; there is no cloud
fallback. Diarization alone does not identify people's names.

## 3. Check, launch and pair

```sh
.venv/bin/python scripts/run-local.py doctor
.venv/bin/python scripts/run-local.py start
```

Open **http://127.0.0.1:8766/meeting-intelligence**. In the pairing dialog, paste
the `station` value from `.local/single-machine/tokens.json`. This file is ignored
by Git and created with owner-only permissions. Do not paste the `worker` value.
On macOS, this command copies only the station token without printing it:

```sh
.venv/bin/python scripts/run-local.py token | pbcopy
```

Choose **Import**, upload an allowed recording or paste a transcript, select the
meeting/report languages, and submit. Review the transcript, cited decisions,
owners and deadlines before exporting the report. A service being available or a
model file existing does not establish recognition or extraction accuracy.

`doctor` reports missing Python packages, incorrect frontend builds, missing
executables/model files and whether the configured model appears in the local
Ollama inventory. It makes no inference request. The worker checks GGUF/local
model metadata again at inference time. A passing doctor is a setup check, not a
multilingual acceptance result.

If models are unavailable, `start --allow-missing-models` explicitly starts the
real interface and archive for setup inspection. It prints the missing inference
prerequisites; uploaded jobs may fail and no completed report is promised. The
ordinary `start` command refuses that incomplete setup.

Ctrl-C terminates the two child Python services and retains sources/results in
`.local/single-machine/`. Stop separately started Ollama in its own terminal.
Restarting uses the same tokens and archive. This launcher does not load the
repository `.env` or reuse appliance credentials. Ports can be changed with
`--port 8766 --worker-port 8765`; occupied ports fail without stopping the process
that owns them. `--state-dir` selects a separate initialized archive/settings
directory. Generated settings, recordings and tokens must never be committed.

## Checks and troubleshooting

```sh
make verify
# If shipping the retained Go/native entry points, also run:
make verify-go
make verify-native  # macOS only
```

`make verify` needs the core validation environment, Node dependencies and an
already installed Playwright Chromium. `make verify-go` needs the Go version in
`go.mod` and its modules provisioned under `.local/go`; it builds the retained
interface separately and runs `go test -race ./...` with downloads disabled.
`make verify-native` compiles and tests the existing Swift application. These
commands never install dependencies. Exact evidence and supported combinations
are in [FOUNDATION_FIXES.md](FOUNDATION_FIXES.md).

Tests use synthetic fixtures/fake inference transports and do not establish real
Russian/Kazakh accuracy. Verify an actual recording and downloaded report
separately when local model assets are available.

After building the local frontend, an opt-in HTTP check starts the real worker
and station on unused loopback ports, fetches the built HTML/JavaScript, checks
authenticated API routing and missing-model status, and verifies that both child
services stop. It uses temporary empty archives and makes no inference request:

```sh
MI_RUN_LOCAL_HTTP_TESTS=1 .venv/bin/python -m pytest station/tests/test_local_http.py -q
```

- **Account sign-in appears:** rebuild with both frontend flags, visit the
  loopback URL and refresh. LAN origins do not activate standalone authentication.
- **Pairing rejected:** use this launcher's station token and port. Tokens from
  another archive are not interchangeable.
- **Missing Ollama model:** provision it explicitly while online, then restart
  Ollama with cloud disabled. The launcher never pulls it automatically.
- **Missing executable/model:** configure absolute installed paths. Merely
  installing the Python package does not install Whisper, ffmpeg or model weights.
- **Unavailable Radxa recording/browser:** import a file on this standalone path.
