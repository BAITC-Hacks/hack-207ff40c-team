"""Run a model stage in a disposable process that can be timed out and cancelled."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from .config import Settings
from .local_audio import command, inherit_stage_process_group
from .schemas import Transcript


def run_model(operation, config, audio, *, profile=None, language='auto', transcript=None,
              min_speakers=None, max_speakers=None, cancelled=None):
    # Loading native ML libraries on the queue's thread cannot be interrupted.
    # A separate process releases their threads/device allocations when it exits.
    with tempfile.TemporaryDirectory(prefix='model-', dir=config.data_dir / 'work') as temporary:
        directory = Path(temporary)
        request, output = directory / 'request.json', directory / 'result.json'
        payload = dict(operation=operation, config=config.model_dump(mode='json', exclude={'api_token', 'hf_token'}),
            audio=str(audio.resolve()), profile=profile, language=language,
            transcript=transcript.model_dump(mode='json') if transcript else None,
            min_speakers=min_speakers, max_speakers=max_speakers)
        # Resolve paths before changing the child's working directory.
        # All scratch files belong to the supervising parent's directory, so
        # SIGKILL cannot leave an adapter's TemporaryDirectory behind.
        payload['config']['data_dir'] = str(directory.resolve())
        (directory / 'work').mkdir(mode=0o700)
        for key in ('shyngys_model', 'gigaam_model', 'distil_model', 'diarization_model',
                    'whisper_binary', 'whisper_model', 'whisper_model_en', 'whisper_vad_model',
                    'segmentation_model', 'embedding_model', 'ffmpeg_binary'):
            value = payload['config'][key]
            if value and Path(value).exists():
                payload['config'][key] = str(Path(value).resolve())
        request.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        request.chmod(0o600)
        command([sys.executable, '-m', 'meeting_worker.model_process', str(request), str(output)],
                directory, config.audio_timeout, cancelled=cancelled)
        if not output.is_file() or output.stat().st_size > 16 * 1024 * 1024:
            raise RuntimeError('Model returned no transcript or exceeded the 16 MiB transcript limit')
        return Transcript.model_validate_json(output.read_bytes())


def main():
    inherit_stage_process_group()
    payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    config = Settings(_env_file=None, **payload['config'])
    if payload['operation'] == 'asr':
        from .asr import get_adapter
        result = get_adapter(payload['profile'], config).transcribe(Path(payload['audio']), payload['language'])
    elif payload['operation'] == 'diarize':
        from .diarization import diarize
        result = diarize(Path(payload['audio']), Transcript.model_validate(payload['transcript']), config,
                         payload['min_speakers'], payload['max_speakers'])
    else:
        raise ValueError('Unknown model operation')
    output = Path(sys.argv[2])
    output.write_text(result.model_dump_json(), encoding='utf-8')
    output.chmod(0o600)


if __name__ == '__main__':
    main()
