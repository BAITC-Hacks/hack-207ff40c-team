# Set up the room station and local worker

This deployment uses a small Radxa computer for recording, the web interface and
the archive, with a Mac on the same private network for inference. For evaluation
on one computer, use [LOCAL_SETUP.md](LOCAL_SETUP.md) instead.

The [September 11 runbook](RUNBOOK.md) records the original installation. Its LAN
addresses and private paths are examples from that installation, not credentials
or a ready-made configuration for a new board. This repository includes source
and deployment scripts; it does not include model files or a flashable disk image.

## 1. Prepare the equipment and downloads

The documented hardware is a Radxa Cubie A7A with 6 GB RAM and Debian 11, plus a
MacBook Air M5 with 16 GB memory. Connect the microphone to the station. Reserve
both devices' private LAN addresses so certificates continue to match them.

Prepare Git, Node.js 22.12+/npm and the Go toolchain declared in `go.mod` for the
application build. The Mac worker requires Python 3.11+; the model provisioning
recipe uses Python 3.12. The station package supports Python 3.9+ on the board.
The appliance also needs Caddy, FFmpeg/recording tools, gocryptfs and the service
dependencies listed in the [runbook](RUNBOOK.md#board-installation-and-configuration).

Follow [MODEL_SETUP.md](MODEL_SETUP.md) to provision FFmpeg, whisper.cpp, a
multilingual Whisper model, Sherpa's segmentation/embedding models and Ollama
with Qwen3.5 4B. Complete downloads during setup and retain component licenses.
Do not substitute an English-only speech model for the required languages.

## 2. Build the station application

From the repository root:

```sh
bash scripts/build-station.sh
```

The script installs the locked frontend dependencies with `npm ci`, builds with
`VITE_MEETING_STATION=true`, embeds the interface in Go and produces
`build/scriberr-linux-arm64`. The binary keeps its inherited deployment filename.
Set `MI_STATION_MODE=true` in the board's Go service configuration; both flags are
required. This build does not install models, certificates or system services.

## 3. Configure the Mac worker

```sh
python3.12 -m venv .venv-worker
.venv-worker/bin/python -m pip install -e 'mac-worker[local,test]'
if [ ! -e .env ]; then
  cp mac-worker/.env.example .env
fi
```

Review `.env`, including any existing file. Replace the example token with a
fresh random secret, set the local executable/model paths and configure the
private LAN bind address. Keep these files outside Git. Set
`MI_ENABLE_DIARIZATION=true` and both ONNX model paths, and request speaker
separation when submitting audio. Configure a local Unicode PDF font with Kazakh
and Cyrillic glyphs. See the [worker configuration](../mac-worker/.env.example).

Provision the device identities with [create-worker-pki.py](../scripts/create-worker-pki.py)
and the [security guide](SECURITY.md). The LAN worker requires its server
certificate, private key and trusted client CA. The station receives its own
client certificate/key and the public CA; the CA private key stays off the board.
Use a fresh output directory and the actual worker IP. Keep verification enabled.

Start separately installed Ollama in one terminal:

```sh
OLLAMA_NO_CLOUD=1 \
OLLAMA_HOST=127.0.0.1:11434 \
OLLAMA_NUM_PARALLEL=1 \
OLLAMA_MAX_LOADED_MODELS=1 ollama serve
```

After models and credentials have been provisioned, start the worker separately:

```sh
.venv-worker/bin/meeting-worker
```

An existing LaunchAgent may already own the service port. Use either the installed
service or the foreground command. The [runbook](RUNBOOK.md#mac-inference-service)
also describes the original Mac's additional process network restrictions; a
manual worker launch does not install that policy.

## 4. Install and protect the station

Follow the [board installation procedure](RUNBOOK.md#board-installation-and-configuration)
to stage the binary, station package, Python environment and service definitions.
Configure the station's worker address, separate pairing/worker tokens and client
TLS identity. The Go and Python services bind to board loopback behind Caddy.

Configure Caddy's HTTPS address and trusted public browser CA, then provision the
encrypted archive and startup guards using the [security and recovery guide](SECURITY.md).
An ordinary application install does not create that encrypted vault. Keep the
vault unlock credential and recovery copy on protected separate storage; the
documented deployment uses FileVault on the Mac and pinned SSH to unlock the board.
The private installation credentials and migration backups are not in this repo.

Open the configured station HTTPS address, sign in and enter the station pairing
token. Other browsers must trust the public station CA through a trusted channel.
Keep the Mac logged in and awake for processing and automatic unlock after reboot.
Renew device certificates before their 90-day expiry; changing the worker's IP
requires a matching certificate and station configuration.

## 5. Check the complete installation

1. Import non-sensitive Russian, Kazakh and mixed-language recordings with known
   transcripts and expected assignments. Enable speaker separation.
2. Open an assignment's source passage, listen to it, correct the owner/date and
   save a review. Reload the page and inspect the downloaded PDF and DOCX,
   including Kazakh/Cyrillic characters.
3. Disconnect internet access while keeping the private LAN available. Repeat an
   upload with installed models and record the outcome.
4. Stop the worker while the unlocked station remains running. Check that a new
   recording queues and existing reports remain accessible. Restart the worker;
   confirm the job completes once and the source is retained.
5. Check certificate rejection, vault lock/unlock and reboot recovery against
   [SECURITY.md](SECURITY.md). Preserve a recoverable encrypted backup first.

These are acceptance steps for a new installation. The earlier hardware log and
current synthetic regression checks do not establish that this new setup passed.
Use [ACCURACY.md](ACCURACY.md) for recognition measurements and count missing or
invented tasks, wrong owners and wrong deadlines separately.

For application regressions, follow [the verification instructions](LOCAL_SETUP.md#checks-and-troubleshooting).
`make verify` runs the configured checks once their pinned dependencies and test
browser are installed; `make verify-go` additionally checks the retained Go path.
