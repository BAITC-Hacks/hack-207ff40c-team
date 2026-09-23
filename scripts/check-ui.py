#!/usr/bin/env python3
"""Exercise the real review interface against a clearly labeled synthetic report.

Seeds expected model output; does NOT run or measure speech/language models.
All browser/API requests stay on loopback. Never opens an existing user archive.
"""
from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "station/src"), str(ROOT / "mac-worker/src")]


def seed(state):
    from meeting_worker.bundle import write_exports
    from meeting_worker.config import Settings
    from meeting_worker.schemas import ActionItem, Evidence, JobManifest, JobRecord, JobResult, JobStage, MeetingMetadata, MeetingProtocol, Transcript, TranscriptSegment
    from meeting_worker.store import JobStore
    from meeting_station.store import Store
    spec = importlib.util.spec_from_file_location("launcher", ROOT / "scripts/run-local.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    launcher.initialize(state)
    config = Settings(_env_file=None, api_token=launcher.read_tokens(state)["worker"], data_dir=state / "worker")
    config.prepare()
    identity = "11111111-1111-4111-8111-111111111111"
    title = "Планирование проекта · учебный пример"
    manifest = JobManifest(meeting_id=identity, title=title, output_language="ru", language_mode="kk_ru")
    transcript = Transcript(model="synthetic-fixture-no-inference", language="kk_ru",
        raw_text="Мен есепті дайындаймын. Уточнение: отчёт подготовит Тимур к понедельнику.",
        warnings=["Учебный пример: данные подготовлены для проверки интерфейса. Распознавание речи и ИИ-извлечение не запускались."],
        segments=[TranscriptSegment(id="s1", start=0, end=4, speaker="SPEAKER_00", text="Мен есепті дайындаймын."),
                  TranscriptSegment(id="s2", start=4, end=10, speaker="SPEAKER_01", text="Уточнение: отчёт подготовит Тимур к понедельнику.")])
    protocol = MeetingProtocol(metadata=MeetingMetadata(meeting_id=identity, title=title, report_language="ru"),
        action_items=[ActionItem(id="a1", task="Подготовить отчёт", assignee="Айдана", deadline_text="в пятницу", source_check="passed",
            evidence=Evidence(segment_ids=["s2"], quote=transcript.segments[1].text, speaker="SPEAKER_01", start=4, end=10))])
    import hashlib
    station = Store(state / "station")
    for empty in (False, True):
        if empty:
            identity = "33333333-3333-4333-8333-333333333333"
            title = "Без извлечённых поручений · учебный пример"
            manifest = manifest.model_copy(update={"meeting_id": identity, "title": title})
            protocol = MeetingProtocol(metadata=MeetingMetadata(meeting_id=identity, title=title, report_language="ru"))
        source = config.data_dir / "sources" / (identity + ".txt")
        source.write_text(transcript.raw_text)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        result_path = config.data_dir / "results" / (identity + ".json")
        now = datetime.now(UTC)
        job = JobRecord(id=identity, meeting_id=identity, stage=JobStage.COMPLETED, source_kind="text", source_path=str(source),
            source_sha256=digest, manifest=manifest, created_at=now, updated_at=now, result_path=str(result_path))
        result = JobResult(job=job, transcript=transcript, protocol=protocol,
            exports=write_exports(config.data_dir / "exports" / identity, protocol, transcript))
        result_path.write_text(result.model_dump_json())
        JobStore(config.data_dir / "worker.sqlite3").put(job)
        shutil.copyfile(source, station.sources / source.name)
        station.create(identity, manifest.model_dump(mode="json"), "text", source.name, source.name, source.stat().st_size, digest)
        directory = station.exports / identity
        directory.mkdir()
        for kind, path in result.exports.items():
            shutil.copyfile(path, directory / ("meeting." + kind))
        station.complete(identity, result.model_dump(mode="json"))
    station.close()
    return launcher


def main():
    artifacts = ROOT / ".local/ui-artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="meeting-ui-") as temporary:
        state = Path(temporary)
        launcher = seed(state)
        probes = [socket.socket(), socket.socket()]
        try:
            for probe in probes:
                probe.bind(("127.0.0.1", 0))
            port, worker_port = [probe.getsockname()[1] for probe in probes]
        finally:
            for probe in probes:
                probe.close()
        with (artifacts / "services.log").open("w") as log:
            process = subprocess.Popen([sys.executable, "scripts/run-local.py", "start", "--state-dir", str(state),
                "--port", str(port), "--worker-port", str(worker_port), "--allow-missing-models"],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                base = "http://127.0.0.1:" + str(port)
                for _ in range(150):
                    if process.poll() is not None:
                        raise RuntimeError("Local service exited; inspect .local/ui-artifacts/services.log")
                    try:
                        launcher.local_json(base + "/api/meeting-worker/health", timeout=1)
                        break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Local service did not become ready")
                environment = dict(os.environ, MI_UI_BASE_URL=base, MI_UI_STATE_DIR=str(state), MI_UI_ARTIFACTS=str(artifacts))
                environment.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".local/browsers"))
                run = subprocess.run([str(ROOT / "web/frontend/node_modules/.bin/playwright"), "test", "--config", "e2e/playwright.config.ts"],
                    cwd=ROOT / "web/frontend", env=environment, timeout=150)
                if run.returncode:
                    return run.returncode
                from pypdf import PdfReader
                for name in ("review", "missed-action"):
                    with ZipFile(artifacts / (name + ".docx")) as document:
                        xml = document.read("word/document.xml").decode()
                        assert "Тимур" in xml and "2026-09-28" in xml
                    text = " ".join(page.extract_text() for page in PdfReader(artifacts / (name + ".pdf")).pages)
                    assert "Тимур" in text and "2026-09-28" in text
                print("Browser review, missed-action recovery, reload, DOCX/PDF download and document contents: PASS (synthetic supplied output; no model inference).")
            finally:
                launcher.stop_children([process], timeout=15)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
