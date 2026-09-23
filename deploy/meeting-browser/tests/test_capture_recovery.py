import importlib.util
import io
from pathlib import Path
from uuid import uuid4
import wave

import pytest


def load():
    path = Path(__file__).parents[1] / "controller.py"
    spec = importlib.util.spec_from_file_location("recovery_controller", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wav_bytes(*, unfinalized=False, odd=False):
    output = io.BytesIO()
    pcm = b"\x01\x03" * 16000
    with wave.open(output, "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        stream.writeframes(pcm)
    data = output.getvalue()
    if unfinalized:
        data = data[:4] + b"\xff" * 4 + data[8:40] + b"\xff" * 4 + data[44:]
    if odd:
        data += b"\x01"
    return data, pcm


@pytest.mark.parametrize("odd", [False, True])
def test_restart_preserves_original_and_serves_valid_recovered_copy(tmp_path, odd):
    module = load()
    controller = module.Controller(tmp_path)
    recording_id = str(uuid4())
    original, pcm = wav_bytes(unfinalized=True, odd=odd)
    controller.path(recording_id, ".wav").write_bytes(original)
    controller.save({"id": recording_id, "state": "recording", "error": None})
    restarted = module.Controller(tmp_path)
    record = restarted.record(recording_id)
    assert record["state"] == "interrupted"
    assert record["audio_recovered"] is True
    assert "recovered" in record["error"]
    assert record["audio_received"] is True
    assert restarted.path(recording_id, ".wav").read_bytes() == original
    recovered = restarted.audio_path(record)
    assert recovered.name.endswith(".recovered.wav")
    assert recovered.stat().st_size == record["bytes"]
    with wave.open(str(recovered), "rb") as stream:
        assert stream.getparams()[:4] == (1, 2, 16000, 16000)
        assert stream.readframes(stream.getnframes()) == pcm
    assert recovered.stat().st_mode & 0o777 == 0o600
    assert not list(recovered.parent.glob("*.partial"))
    assert module.Controller(tmp_path).record(recording_id)["audio_recovered"] is True


def test_normal_finalization_does_not_rewrite_audio(tmp_path):
    module = load()
    controller = module.Controller(tmp_path)
    recording_id = str(uuid4())
    original, _ = wav_bytes()
    controller.path(recording_id, ".wav").write_bytes(original)
    controller.save({"id": recording_id, "state": "recording", "error": None})
    record = controller.finalize(recording_id)
    assert record["state"] == "stopped"
    assert not record.get("audio_recovered")
    assert controller.audio_path(record).read_bytes() == original


@pytest.mark.parametrize("invalid", [b"not audio", None])
def test_unrecoverable_or_oversized_capture_remains_retained(tmp_path, invalid):
    module = load()
    controller = module.Controller(tmp_path, max_bytes=100)
    recording_id = str(uuid4())
    original = invalid if invalid is not None else wav_bytes(unfinalized=True)[0]
    controller.path(recording_id, ".wav").write_bytes(original)
    controller.save({"id": recording_id, "state": "recording", "error": None})
    record = controller.finalize(recording_id, forced=True)
    assert record["state"] == "interrupted"
    assert not record.get("audio_recovered")
    assert controller.audio_path(record).read_bytes() == original
    assert not controller.path(recording_id, ".recovered.wav").exists()


@pytest.mark.parametrize("limit,requested,expected", [(30, 14400, 30), (100, 12, 12), (100, None, 100)])
def test_capture_uses_minimum_duration_limit(tmp_path, monkeypatch, limit, requested, expected):
    from types import SimpleNamespace
    module = load()
    controller = module.Controller(tmp_path, max_seconds=limit)
    commands = []
    monkeypatch.setattr(module.subprocess, "Popen", lambda argv, **kw: commands.append(argv) or SimpleNamespace())
    monkeypatch.setattr(module.threading, "Thread", lambda **kw: SimpleNamespace(start=lambda: None))
    controller.start(str(uuid4()), requested)
    assert float(commands[0][commands[0].index("-t") + 1]) == expected


@pytest.mark.parametrize("limit", [-1, 0, float("nan"), float("inf"), True])
def test_capture_rejects_invalid_duration_before_starting(tmp_path, monkeypatch, limit):
    module = load()
    controller = module.Controller(tmp_path)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kw: pytest.fail("invalid capture was started"))
    with pytest.raises(module.ControllerError):
        controller.start(str(uuid4()), limit)
