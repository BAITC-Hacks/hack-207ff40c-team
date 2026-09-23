from __future__ import annotations

import threading
import os
import wave
from datetime import UTC, datetime
from pathlib import Path

from .config import Settings
from .bundle import result_bytes, sync_directory, write_exports
from .protocol import call_ollama
from .schemas import (
    JobRecord, JobResult, JobStage, MeetingMetadata, Transcript, TranscriptSegment,
)
from .store import JobStore
from .local_audio import ProcessingCancelled, command
from .model_process import run_model


def _text_transcript(path: Path, language: str) -> Transcript:
    text = path.read_text(encoding="utf-8").strip()
    blocks = [block.strip() for block in text.splitlines() if block.strip()]
    segments = [
        TranscriptSegment(id=f"seg_{idx:05d}", text=block, language=language)
        for idx, block in enumerate(blocks or [text], start=1)
    ]
    return Transcript(language=language, model="provided-text", raw_text=text, segments=segments)


class Pipeline:
    def __init__(self, config: Settings, store: JobStore):
        self.config = config
        self.store = store
        # One heavy model job at a time prevents unified-memory exhaustion on a MacBook Air.
        self._inference_lock = threading.Lock()
        self.active_job: str | None = None
        self._stopping = threading.Event()

    def stop(self):
        self._stopping.set()

    def cancelled(self, job_id):
        job = self.store.get(job_id)
        return self._stopping.is_set() or job is None or job.stage == JobStage.CANCELLED

    def check_cancelled(self, job_id):
        if self.cancelled(job_id):
            raise ProcessingCancelled('Processing stopped; saved source can be retried')

    def run(self, job_id: str) -> None:
        with self._inference_lock:
            self.active_job = job_id
            try:
                self._run_locked(job_id)
            finally:
                self.active_job = None

    def _run_locked(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job is None or job.stage == JobStage.CANCELLED:
            return
        try:
            source = Path(job.source_path)
            self.check_cancelled(job.id)
            if job.source_kind == "text":
                transcript = _text_transcript(source, job.manifest.language_mode)
            else:
                profile = self.config.asr_en if job.manifest.language_mode == "en" else self.config.asr_kk_ru
                if job.manifest.diarization and profile == 'gigaam':
                    raise RuntimeError('GigaAM currently has no timed segment contract. Select whisper-cpp, shyngys or mlx-distil-whisper for diarization')
                job = self.store.update(job.id, JobStage.PREPROCESSING)
                wav = self.config.data_dir / "work" / f"{job.id}.wav"
                command([self.config.ffmpeg_binary, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                    "-protocol_whitelist", "file,pipe", "-format_whitelist", "wav,mp3,mov,matroska,webm,ogg,caf,flac",
                    "-i", str(source), "-map", "0:a:0", "-vn", "-t", str(self.config.max_audio_seconds + 1),
                    "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
                    self.config.data_dir / "work", min(300, self.config.audio_timeout),
                    cancelled=lambda: self.cancelled(job.id))
                with wave.open(str(wav), "rb") as audio:
                    duration = audio.getnframes() / audio.getframerate()
                if duration <= 0 or duration > self.config.max_audio_seconds:
                    raise RuntimeError("Audio is empty or exceeds the configured duration limit")
                self.check_cancelled(job.id)
                job = self.store.update(job.id, JobStage.TRANSCRIBING)
                language = job.manifest.language_mode if job.manifest.language_mode in {"en", "ru", "kk"} else "auto"
                asr_config = self.config.model_copy(update={"whisper_prompt": job.manifest.vocabulary})
                transcript = run_model('asr', asr_config, wav, profile=profile, language=language,
                                       cancelled=lambda: self.cancelled(job.id))

                self.check_cancelled(job.id)
                if job.manifest.diarization:
                    if not self.config.enable_diarization:
                        raise RuntimeError("Diarization was requested but is disabled on this worker")
                    job = self.store.update(job.id, JobStage.DIARIZING)
                    transcript = run_model('diarize', self.config, wav, transcript=transcript,
                        min_speakers=job.manifest.min_speakers, max_speakers=job.manifest.max_speakers,
                        cancelled=lambda: self.cancelled(job.id))

            self.check_cancelled(job.id)
            transcript_path = self.config.data_dir / "work" / f"{job.id}.transcript.json"
            transcript_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
            transcript_path.chmod(0o600)
            if self.store.get(job.id).stage == JobStage.CANCELLED:
                return
            job = self.store.update(job.id, JobStage.EXTRACTING)
            protocol = call_ollama(transcript, job.manifest, self.config)
            self.check_cancelled(job.id)
            job = self.store.update(job.id, JobStage.VALIDATING)
            protocol.metadata = MeetingMetadata(
                meeting_id=job.id,
                title=protocol.metadata.title or job.manifest.title,
                meeting_date=job.manifest.meeting_date,
                timezone=job.manifest.timezone,
                language=transcript.language,
                report_language=protocol.metadata.report_language or (job.manifest.output_language if job.manifest.output_language != 'same' else transcript.language),
                duration_seconds=duration if job.source_kind == "audio" else None,
                participants=protocol.metadata.participants,
            )
            # call_ollama already validated citations and reviewed final claims.
            # Revalidating here would erase semantic review failures.

            if self.store.get(job.id).stage == JobStage.CANCELLED:
                return

            job = self.store.update(job.id, JobStage.EXPORTING)
            export_dir = self.config.data_dir / "exports" / job.id
            paths = write_exports(export_dir, protocol, transcript, self.config.pdf_font or None)

            result_path = self.config.data_dir / "results" / f"{job.id}.json"
            completed = job.model_copy(update={"stage": JobStage.COMPLETED, "result_path": str(result_path),
                                               "updated_at": datetime.now(UTC)})
            result = JobResult(
                job=completed, transcript=transcript, protocol=protocol,
                exports={name: str(path) for name, path in paths.items()},
            )
            temporary = result_path.with_suffix(".partial")
            self.check_cancelled(job.id)
            with temporary.open("wb") as output:
                temporary.chmod(0o600)
                output.write(result_bytes(result))
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(result_path)
            sync_directory(result_path.parent)
            # Publish completion only after the result and exports are readable.
            self.store.update(job.id, JobStage.COMPLETED, result_path=str(result_path))
        except Exception as exc:
            current = self.store.get(job.id)
            if current and current.stage != JobStage.CANCELLED:
                self.store.update(
                    job.id, JobStage.FAILED,
                    error_code=type(exc).__name__.upper(),
                    error_message=str(exc)[:1000] if isinstance(exc, RuntimeError) else "Local processing failed; saved source can be retried.",
                )
