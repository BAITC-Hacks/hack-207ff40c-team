import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from meeting_station.config import Settings
from meeting_station.local import create_local_app

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("local_launcher", ROOT / "scripts/run-local.py")
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)
TOKEN = "local-station-test-token-1234567890"


@pytest.fixture
def frontend(tmp_path):
    directory = tmp_path / "dist"
    directory.mkdir()
    (directory / "index.html").write_text("<!doctype html><title>Meeting Station</title>")
    (directory / "meeting-build.json").write_text(json.dumps({"version": 1, "station": True, "local": True}))
    (directory / "asset.js").write_text("/* static fixture */")
    return directory


def test_local_host_serves_ui_but_authenticates_every_archive_request(tmp_path, frontend):
    settings = Settings(token=TOKEN, worker_token="worker-test-token-1234567890", data_dir=tmp_path / "archive")
    app = create_local_app(settings, frontend, start_worker=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/meeting-intelligence").status_code == 200
        assert client.get("/asset.js").status_code == 200
        assert client.get("/api/meeting-worker/health").json()["role"] == "station"
        assert client.get("/api/meeting-worker/v1/jobs").status_code == 401
        assert client.post("/api/meeting-worker/v1/jobs", content="malformed").status_code == 401
        assert client.get("/api/v1/auth/registration-status").status_code == 404
        assert client.get("/v1/jobs").status_code == 404
        assert client.get("/.local/tokens.json").status_code == 404
        assert client.get("/", headers={"Host": "public-attacker.example"}).status_code == 400
        client.headers["Authorization"] = "Bearer " + TOKEN
        assert client.get("/api/meeting-worker/v1/jobs").json() == []
        # An incorrect prefix rewrite applies the generic 2 MiB request limit.
        # This verifies the real multipart route and durable archive, not ASR.
        audio = b"local routing fixture" * 120000
        job_id = str(uuid4())
        response = client.post("/api/meeting-worker/v1/jobs", data={"manifest_json": json.dumps({"meeting_id": job_id})},
                               files={"audio": ("fixture.wav", audio, "audio/wav")})
        assert response.status_code == 202
        saved = response.json()["id"]
        assert client.get("/api/meeting-worker/v1/jobs/" + saved + "/audio").content == audio
        assert TOKEN not in client.get("/meeting-intelligence").text
    assert (tmp_path / "archive/station.sqlite3").is_file()


def test_local_host_rejects_lan_bind_and_wrong_ui(tmp_path, frontend):
    settings = Settings(token=TOKEN, worker_token="worker-test-token-1234567890", data_dir=tmp_path)
    (frontend / "meeting-build.json").write_text('{"version":1,"station":true,"local":false}')
    with pytest.raises(ValueError, match="VITE_MEETING_LOCAL"):
        create_local_app(settings, frontend)
    from dataclasses import replace
    with pytest.raises(ValueError, match="loopback"):
        create_local_app(replace(settings, bind_host="0.0.0.0"), frontend)


def test_launcher_tokens_are_distinct_private_and_preserved(tmp_path):
    launcher.initialize(tmp_path)
    original = launcher.read_tokens(tmp_path)
    assert original["station"] != original["worker"]
    assert (tmp_path / "tokens.json").stat().st_mode & 0o077 == 0
    launcher.initialize(tmp_path)
    assert launcher.read_tokens(tmp_path) == original
    os.chmod(tmp_path / "tokens.json", 0o644)
    with pytest.raises(ValueError, match="private"):
        launcher.read_tokens(tmp_path)


def test_local_upload_limit_is_consistent_between_station_and_worker(tmp_path):
    config = dict(launcher.DEFAULT_CONFIG, MI_MAX_UPLOAD_BYTES="1048576")
    env = launcher.child_environment(config, {"station": TOKEN, "worker": "local-worker-test-token-1234567890"}, tmp_path, 8766, 8765)
    assert env["MI_STATION_MAX_UPLOAD_BYTES"] == env["MI_MAX_UPLOAD_BYTES"] == "1048576"


@pytest.mark.parametrize("value", ["https://cloud.example", "http://127.0.0.1:11434/path", "http://secret@127.0.0.1:11434"])
def test_launcher_rejects_nonlocal_or_ambiguous_ollama_configuration(tmp_path, value):
    launcher.initialize(tmp_path)
    (tmp_path / "config.json").write_text(json.dumps({"MI_OLLAMA_URL": value}))
    with pytest.raises(ValueError, match="loopback"):
        launcher.read_configuration(tmp_path)


def test_launcher_does_not_inherit_deployed_tokens_addresses_or_model_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("MI_API_TOKEN", "unrelated-existing-deployment-secret")
    monkeypatch.setenv("MI_TLS_KEY_FILE", "/unrelated/private-key")
    monkeypatch.setenv("MI_BIND_HOST", "0.0.0.0")
    monkeypatch.setenv("MI_ASR_KK_RU", "gigaam")
    config = dict(launcher.DEFAULT_CONFIG)
    tokens = {"station": "new-station-credential", "worker": "new-worker-credential"}
    environment = launcher.child_environment(config, tokens, tmp_path, 9876, 9875)
    assert environment["MI_API_TOKEN"] == tokens["worker"]
    assert environment["MI_STATION_TOKEN"] == tokens["station"]
    assert environment["MI_BIND_HOST"] == "127.0.0.1"
    assert environment["MI_STATION_WORKER_URL"] == "http://127.0.0.1:9875"
    assert "MI_TLS_KEY_FILE" not in environment and "MI_ASR_KK_RU" not in environment
    assert environment["MI_HF_OFFLINE"] == "true"


def test_launcher_stops_owned_processes():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    try:
        launcher.stop_children([child], timeout=2)
        assert child.poll() is not None
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_doctor_distinguishes_missing_models_from_missing_ui(frontend):
    required, inference = launcher.prerequisites(dict(launcher.DEFAULT_CONFIG), frontend, probe=False)
    assert not required
    assert any("MI_WHISPER_MODEL" in item for item in inference)
    assert any("MI_WHISPER_BINARY" in item for item in inference)
    (frontend / "index.html").unlink()
    required, _ = launcher.prerequisites(dict(launcher.DEFAULT_CONFIG), frontend, probe=False)
    assert any("Build the UI" in item for item in required)
