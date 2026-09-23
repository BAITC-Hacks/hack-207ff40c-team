# Python Adapters Testing

This directory contains the Python adapter scripts for various transcription and diarization models used by Scriberr.

## Running Tests

The tests are located in the `tests/` subdirectory of each adapter folder (e.g., `nvidia/tests/`, `pyannote/tests/`). These tests verify that the Python scripts can be executed and produce the expected output.

To run the tests, you need `uv` installed and the `parakeet` environment set up (which serves as a shared environment for these tests).

### Prerequisites

1.  Ensure you have `uv` installed.
2.  Ensure the `parakeet` and `pyannote` environments set up within `data/whisperx-env/`. This is typically handled by the application startup.
3.  Ensure you have the test data available (e.g., `tests/data/AMI-Corpus-IB4002.Mix-Headset-clip.wav`).

### Running Tests with pytest

```bash
# Run all NVIDIA adapter tests
uv run --with pytest --project data/whisperx-env/parakeet pytest internal/transcription/adapters/py/nvidia/tests

# Run PyAnnote adapter tests
uv run --with pytest --project data/whisperx-env/pyannote pytest internal/transcription/adapters/py/pyannote/tests
```

### Troubleshooting

*   **Audio file not found**: Ensure `tests/data/AMI-Corpus-IB4002.Mix-Headset-clip.wav` exists.
*   **Environment not found**: Ensure `data/whisperx-env/parakeet` and the `pyannote` one exist and is a valid virtual environment. This may not be true if scriberr hasn't run yet.


## Dependency-free contract regressions

`python -m pytest internal/transcription/adapters/py/tests` exercises private chunk
files, malformed chunk durations, CPU/device forwarding, Pyannote 4 output shape,
Voxtral language conditioning and Sortformer's fixed speaker capacity with small
API-shaped fixtures. These tests do not load models or measure ASR accuracy.

The Voxtral adapter fixes its processor/tokenizer API at Transformers 4.57.1 and
mistral-common 1.8.1. Source inspection on 2026-09-23 confirmed this automatic mode:

- [Transformers processor](https://github.com/huggingface/transformers/blob/v4.57.1/src/transformers/models/voxtral/processing_voxtral.py): the required language argument accepts a per-audio list and forwards each item to `TranscriptionRequest.from_openai`; `[None]` supplies one unconditioned request.
- [mistral-common request](https://github.com/mistralai/mistral-common/blob/v1.8.1/src/mistral_common/protocol/transcription/request.py): the language field is optional.
- [mistral-common tokenizer](https://github.com/mistralai/mistral-common/blob/v1.8.1/src/mistral_common/tokens/tokenizers/instruct.py): `encode_transcription` inserts the language prefix only when that field is non-null.

These versions were inspected, not installed or run with speech-model weights.
`language: auto` in the result describes the requested mode, not a detected-language
quality guarantee. Explicit `ru`/`kk` remain explicit hints. Sortformer's bundled
model has four fixed outputs; other requested speaker limits now fail before
inference instead of being ignored. Use Pyannote for a constrained speaker count.
