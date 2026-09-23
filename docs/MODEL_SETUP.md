# Provision local inference on macOS or Linux

**Source-inspected on 2026-09-23; these provisioning commands and model inference
have not been run in this submission workspace.** No model assets are bundled.
Complete the application setup in [LOCAL_SETUP.md](LOCAL_SETUP.md) first, using
Python 3.12 for this recipe. Run commands from the repository root. Downloads
below are explicit provisioning steps while online; the launcher never downloads
models. Diarization is required for the meeting case and is enabled below.

## 1. Native tools and pinned Whisper CLI

On macOS 14+ with Homebrew already installed, install Apple's command-line tools
if absent, then the [CMake](https://formulae.brew.sh/formula/cmake) and
[ffmpeg](https://formulae.brew.sh/formula/ffmpeg) packages:

```sh
xcode-select --install  # Only if Apple's command-line tools are absent.
brew install cmake ffmpeg
```

On Ubuntu/Debian, with Python 3.12 already installed:

```sh
sudo apt-get update
sudo apt-get install -y build-essential cmake git curl ffmpeg zstd python3-venv
```

The following follows the [upstream CMake build](https://github.com/ggml-org/whisper.cpp/tree/v1.9.4).
It pins **v1.9.4**, verified at commit
[`927cfce34f31707e17f2bff35c349632fb9e2c3a`](https://github.com/ggml-org/whisper.cpp/commit/927cfce34f31707e17f2bff35c349632fb9e2c3a).
Use a fresh `.local/whisper.cpp` directory:

```sh
mkdir -p .local models
git clone --depth 1 --branch v1.9.4 https://github.com/ggml-org/whisper.cpp.git .local/whisper.cpp
git -C .local/whisper.cpp rev-parse HEAD
# Stop if the printed commit does not match the full pin above.
cmake -S .local/whisper.cpp -B .local/whisper.cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build .local/whisper.cpp/build --config Release --parallel 4
.local/whisper.cpp/build/bin/whisper-cli --help
```

The pinned [CLI parser](https://github.com/ggml-org/whisper.cpp/blob/v1.9.4/examples/cli/cli.cpp)
accepts the worker's `--carry-initial-prompt`, `-ojf` (full JSON), `-mc 0`
(two arguments, not `-mc0`), and `--vad --vad-model PATH` options. This is a
source compatibility check, not a successful inference test.

## 2. Multilingual speech model and VAD

This example uses multilingual `large-v3`; it is a provisioning choice, not a
measured best model for RU/KZ. Do not substitute an English-only `.en` model.
The pinned [GGML manifest](https://github.com/ggml-org/whisper.cpp/blob/v1.9.4/models/README.md)
publishes **SHA-1**, not SHA-256, for these converted weights:

```sh
curl -fL --retry 3 -o models/ggml-large-v3.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin
.venv/bin/python - <<'PY'
import hashlib
with open('models/ggml-large-v3.bin', 'rb') as f:
    actual = hashlib.file_digest(f, 'sha1').hexdigest()
assert actual == 'ad82bf6a9043ceed055076d0fd39f5f186ff8062', actual
print('Whisper model matches the published SHA-1')
PY
curl -fL --retry 3 -o models/ggml-silero-v6.2.0.bin https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v6.2.0.bin
```

The [Whisper VAD instructions](https://github.com/ggml-org/whisper.cpp/tree/v1.9.4#voice-activity-detection-vad)
identify Silero v6.2.0 and this download repository. No expected digest for this
VAD file was independently verified here. Its URL is mutable. VAD filters speech
regions; it does not separate or name speakers.

## 3. Required diarization assets

Install the worker's local dependencies and the verified
[sherpa-onnx 1.13.8 release](https://pypi.org/project/sherpa-onnx/1.13.8/), whose
published files include Python 3.12 macOS and Linux wheels:

```sh
.venv/bin/python -m pip install -e 'mac-worker[local]' 'sherpa-onnx==1.13.8'
curl -fL --retry 3 -o models/segmentation.tar.bz2 https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2
tar -xjf models/segmentation.tar.bz2 -C models
curl -fL --retry 3 -o models/nemo_en_titanet_small.onnx https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/nemo_en_titanet_small.onnx
```

These filenames and release URLs come from the
[official diarization recipe](https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/models.html);
`speaker-recongition-models` is the upstream spelling. The segmentation archive
contains `model.onnx`, `model.int8.onnx`, `LICENSE` and `README.md`; retain them.
No expected model hashes for these two assets were verified here. These release
tags do not constitute immutable content pins. Record local SHA-256 values after
provisioning for later reproduction; they establish local identity, not upstream
authenticity. The English-trained embedding's RU/KZ separation remains untested.

## 4. Ollama and the local Qwen model

Use **Ollama v0.34.3**. The
[release assets and SHA-256 values](https://github.com/ollama/ollama/releases/expanded_assets/v0.34.3)
were checked; choose the correct OS/architecture.
On macOS, download the pinned DMG, check its hash, mount it, and drag `Ollama.app`
to Applications as described in the [official macOS instructions](https://docs.ollama.com/macos):

```sh
curl -fL --retry 3 -o .local/Ollama.dmg https://github.com/ollama/ollama/releases/download/v0.34.3/Ollama.dmg
printf '%s  %s\n' 7bde8d83cc7c2ac54e3dc51f618f4357e3b976f29f01f3efee896a301576b44f .local/Ollama.dmg | shasum -a 256 -c -
hdiutil attach .local/Ollama.dmg
# After installation, use this CLI without needing a PATH symlink:
export MI_OLLAMA_CLI=/Applications/Ollama.app/Contents/Resources/ollama
```

For a fresh Linux x86-64 installation, download the pinned package and use the
[official manual extraction layout](https://docs.ollama.com/linux#manual-install):

```sh
curl -fL --retry 3 -o .local/ollama-linux-amd64.tar.zst https://github.com/ollama/ollama/releases/download/v0.34.3/ollama-linux-amd64.tar.zst
printf '%s  %s\n' e83a089fd0cd2f79ee2933cca2085846a2065f497adbc6467c402177c68423f9 .local/ollama-linux-amd64.tar.zst | sha256sum -c -
sudo tar --zstd -xf .local/ollama-linux-amd64.tar.zst -C /usr
export MI_OLLAMA_CLI=/usr/bin/ollama
```

Linux ARM64 uses `ollama-linux-arm64.tar.zst` from the same release; its SHA-256 is
`cb1d3c178d48b302dbe42b4fb0ce25ef6282e02eac25496cfc07f5333e2264dd`.
Stop any existing Ollama app/service before starting the foreground server below,
so the environment applies to the process actually listening on port 11434:

```sh
OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 "$MI_OLLAMA_CLI" serve
```

In a second terminal, set `MI_OLLAMA_CLI` to the same executable and explicitly
provision the [local model](https://ollama.com/library/qwen3.5:4b):

```sh
OLLAMA_HOST=127.0.0.1:11434 "$MI_OLLAMA_CLI" pull qwen3.5:4b
OLLAMA_HOST=127.0.0.1:11434 "$MI_OLLAMA_CLI" list
```

Record the resulting model ID with your acceptance results. `qwen3.5:4b` is a
mutable tag, not an immutable pin; the inspected catalog showed `2a654d98e6fb`.
The [Ollama FAQ](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features)
documents `OLLAMA_NO_CLOUD=1` and loopback binding. Confirm its startup log reports
cloud disabled. This setting disables cloud features, not all network access:
finish all pulls before disconnecting external networking for runtime checks.

## 5. Wire the assets into the station

Edit `.local/single-machine/config.json` with absolute paths and string values;
replace `/ABS/REPO` and `/ABS/FFMPEG` with your checkout and installed executable:

```json
{
  "MI_WHISPER_BINARY": "/ABS/REPO/.local/whisper.cpp/build/bin/whisper-cli",
  "MI_WHISPER_MODEL": "/ABS/REPO/models/ggml-large-v3.bin",
  "MI_WHISPER_VAD_MODEL": "/ABS/REPO/models/ggml-silero-v6.2.0.bin",
  "MI_FFMPEG_BINARY": "/ABS/FFMPEG",
  "MI_OLLAMA_URL": "http://127.0.0.1:11434",
  "MI_OLLAMA_MODEL": "qwen3.5:4b",
  "MI_ENABLE_DIARIZATION": "true",
  "MI_DIARIZATION_BACKEND": "sherpa-onnx",
  "MI_SEGMENTATION_MODEL": "/ABS/REPO/models/sherpa-onnx-pyannote-segmentation-3-0/model.onnx",
  "MI_EMBEDDING_MODEL": "/ABS/REPO/models/nemo_en_titanet_small.onnx"
}
```

Configure the Unicode PDF font described in [LOCAL_SETUP.md](LOCAL_SETUP.md), run
`.venv/bin/python scripts/run-local.py doctor`, then
`.venv/bin/python scripts/run-local.py start`. Select **Separate speakers** for
each audio import; it is selected by default when local diarization is available. Disabling it leaves the meeting case
incomplete. Anonymous speaker IDs need human mapping to participant names.

A passing doctor checks availability, not RU/KZ/code-switching accuracy. Before
claiming acceptance, run consented or synthetic Russian, Kazakh and mixed-language
recordings with multiple speakers while external networking is disconnected;
compare words, speaker turns, named task owners and deadlines with a fixed human
reference, include absent/uncertain owners or dates, and inspect PDF/DOCX exports.
No such model-based acceptance, memory requirement or runtime has been verified
for this provisioning recipe.

## License boundaries

- [Whisper code and weights](https://github.com/openai/whisper#license) and
  [whisper.cpp](https://github.com/ggml-org/whisper.cpp/blob/v1.9.4/LICENSE) use MIT;
  [Silero VAD](https://github.com/snakers4/silero-vad) also declares MIT.
- [Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B/blob/main/LICENSE) is Apache-2.0;
  the [Ollama model license](https://ollama.com/library/qwen3.5:4b/blobs/7339fa418c9a)
  agrees. Retain applicable license/notice files when redistributing weights.
- sherpa-onnx's Apache-2.0 software license does not relicense its models.
  [Pyannote segmentation 3.0](https://huggingface.co/pyannote/segmentation-3.0)
  declares MIT; its original Hugging Face distribution also has access conditions.
  Retain the converted archive's license. NVIDIA's
  [TitaNet-S model card](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/nemo/models/titanet_small)
  points to the [NeMo toolkit Apache-2.0 license](https://github.com/NVIDIA-NeMo/Speech/blob/main/LICENSE).
  Keep these model-specific terms and attribution; do not assume another sherpa
  segmentation/embedding model has the same license.
