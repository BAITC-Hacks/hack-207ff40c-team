#!/usr/bin/env python3
"""Run the existing worker and station on one machine, without Go or downloads."""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = ROOT / ".local" / "single-machine"
DEFAULT_CONFIG = {
    "MI_WHISPER_BINARY": "",
    "MI_WHISPER_MODEL": "",
    "MI_FFMPEG_BINARY": "ffmpeg",
    "MI_OLLAMA_URL": "http://127.0.0.1:11434",
    "MI_OLLAMA_MODEL": "qwen3.5:4b",
    "MI_ENABLE_DIARIZATION": "true",
    "MI_PDF_FONT": "",
}
ALLOWED_CONFIG = set(DEFAULT_CONFIG) | {
    "MI_WHISPER_MODEL_EN", "MI_WHISPER_VAD_MODEL", "MI_WHISPER_PROMPT",
    "MI_OLLAMA_CONTEXT", "MI_OLLAMA_TIMEOUT", "MI_PROTOCOL_CHUNK_CHARS",
    "MI_SEGMENTATION_MODEL", "MI_EMBEDDING_MODEL", "MI_DIARIZATION_BACKEND",
    "MI_DIARIZATION_MODEL", "MI_AUDIO_TIMEOUT", "MI_MAX_AUDIO_SECONDS", "MI_MAX_UPLOAD_BYTES",
}
REQUIRED_MODULES = ("fastapi", "httpx", "pydantic", "pydantic_settings", "multipart", "reportlab", "uvicorn")


def initialize(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, value in (
        ("config.json", DEFAULT_CONFIG),
        ("tokens.json", {"station": secrets.token_urlsafe(32), "worker": secrets.token_urlsafe(32)}),
    ):
        target = directory / name
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(descriptor, "w") as output:
            json.dump(value, output, indent=2)
            output.write("\n")


def read_configuration(directory):
    config = json.loads((directory / "config.json").read_text())
    if not isinstance(config, dict) or any(key not in ALLOWED_CONFIG or not isinstance(value, str) for key, value in config.items()):
        raise ValueError("config.json must contain supported string settings only; see docs/LOCAL_SETUP.md")
    config = dict(DEFAULT_CONFIG, **config)
    parsed = urlsplit(config["MI_OLLAMA_URL"])
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("MI_OLLAMA_URL must be an HTTP loopback address without credentials or a path")
    if not config["MI_OLLAMA_MODEL"] or "cloud" in config["MI_OLLAMA_MODEL"].lower() or "://" in config["MI_OLLAMA_MODEL"]:
        raise ValueError("Select an installed local Ollama model")
    return config


def read_tokens(directory):
    path = directory / "tokens.json"
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("tokens.json must be a private regular file (chmod 600)")
    tokens = json.loads(path.read_text())
    if not isinstance(tokens, dict) or set(tokens) != {"station", "worker"}:
        raise ValueError("Invalid local token file; do not substitute deployed station credentials")
    if any(not isinstance(value, str) or len(value) < 32 or value != value.strip() for value in tokens.values()) or tokens["station"] == tokens["worker"]:
        raise ValueError("Local station and worker tokens must be distinct and at least 32 characters")
    return tokens


def executable(value):
    return bool(value and shutil.which(value))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_json(url, timeout=2):
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or parsed.username or parsed.password:
        raise ValueError("Local setup checks require an HTTP loopback URL without credentials")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(url, timeout=timeout) as response:
        return json.load(response)


def prerequisites(config, frontend, probe=True):
    """Return structural failures separately from missing inference resources."""
    required, inference = [], []
    if sys.version_info < (3, 11):
        required.append("Python 3.11 or newer is required")
    missing = [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]
    if missing:
        required.append("Missing Python packages: " + ", ".join(missing))
    try:
        marker = json.loads((frontend / "meeting-build.json").read_text())
        if marker != {"version": 1, "station": True, "local": True} or not (frontend / "index.html").is_file():
            raise ValueError("Wrong frontend build")
    except (OSError, ValueError):
        required.append("Build the UI with VITE_MEETING_STATION=true VITE_MEETING_LOCAL=true")
    for key in ("MI_WHISPER_BINARY", "MI_FFMPEG_BINARY"):
        if not executable(config[key]):
            inference.append(key + " must name an installed executable")
    for key in ("MI_WHISPER_MODEL", "MI_WHISPER_MODEL_EN", "MI_WHISPER_VAD_MODEL", "MI_PDF_FONT"):
        value = config.get(key, "")
        if (key == "MI_WHISPER_MODEL" or value) and (not value or not Path(value).is_file() or Path(value).stat().st_size == 0):
            inference.append(key + " must name a nonempty local file")
    if config.get("MI_ENABLE_DIARIZATION", "false").lower() == "true":
        if config.get("MI_DIARIZATION_BACKEND", "sherpa-onnx") != "sherpa-onnx":
            inference.append("This local setup path supports the sherpa-onnx diarization backend")
        if importlib.util.find_spec("sherpa_onnx") is None:
            inference.append("Diarization requires the mac-worker[local] dependencies")
        for key in ("MI_SEGMENTATION_MODEL", "MI_EMBEDDING_MODEL"):
            if not config.get(key) or not Path(config[key]).is_file():
                inference.append(key + " must name a local ONNX file")
    if probe:
        try:
            response = local_json(config["MI_OLLAMA_URL"].rstrip("/") + "/api/tags")
            if not isinstance(response, dict) or not isinstance(response.get("models"), list):
                raise ValueError("Ollama returned an invalid model inventory")
            names = {model.get("name") for model in response["models"] if isinstance(model, dict)}
            if config["MI_OLLAMA_MODEL"] not in names:
                inference.append("Configured Ollama model is not installed: " + config["MI_OLLAMA_MODEL"])
        except (OSError, ValueError, urllib.error.URLError):
            inference.append("Ollama is unavailable on its configured loopback URL; start it separately")
    return required, inference


def child_environment(config, tokens, directory, port, worker_port):
    # Do not inherit another deployment's addresses, credentials, TLS or .env.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("MI_")}
    environment.update(config)
    environment.update({
        "MI_API_TOKEN": tokens["worker"], "MI_STATION_TOKEN": tokens["station"],
        "MI_STATION_WORKER_TOKEN": tokens["worker"],
        "MI_DATA_DIR": str(directory / "worker"), "MI_STATION_DATA_DIR": str(directory / "station"),
        "MI_BIND_HOST": "127.0.0.1", "MI_BIND_PORT": str(worker_port),
        "MI_STATION_BIND_HOST": "127.0.0.1", "MI_STATION_BIND_PORT": str(port),
        "MI_STATION_WORKER_URL": "http://127.0.0.1:" + str(worker_port),
        "MI_STATION_MAX_UPLOAD_BYTES": config.get("MI_MAX_UPLOAD_BYTES", str(512 * 1024 * 1024)),
        "MI_ALLOWED_ORIGINS": "http://127.0.0.1:" + str(port) + ",http://localhost:" + str(port),
        "MI_HF_OFFLINE": "true", "MI_SEMANTIC_VERIFICATION": "true",
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
        "PYTHONPATH": os.pathsep.join((str(ROOT / "station/src"), str(ROOT / "mac-worker/src"))),
        "PYTHONUNBUFFERED": "1",
    })
    return environment


def stop_children(children, timeout=8):
    for child in children:
        if child.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    for child in children:
        try:
            child.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.wait()


def free_port(port):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))


def start(args, config, tokens):
    if not all(0 < port < 65536 for port in (args.port, args.worker_port)):
        raise ValueError("Ports must be between 1 and 65535")
    if args.port == args.worker_port:
        raise ValueError("Station and worker ports must differ")
    free_port(args.port)
    free_port(args.worker_port)
    environment = child_environment(config, tokens, args.state_dir, args.port, args.worker_port)
    environment["MI_LOCAL_FRONTEND"] = str(args.frontend)
    children = []

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        for role in ("_worker", "_station"):
            children.append(subprocess.Popen([sys.executable, str(Path(__file__).resolve()), role],
                                             cwd=ROOT, env=environment, start_new_session=True))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("A local service exited during startup; inspect its error above")
            try:
                local_json("http://127.0.0.1:{}/health".format(args.worker_port))
                local_json("http://127.0.0.1:{}/api/meeting-worker/health".format(args.port))
                break
            except (OSError, ValueError, urllib.error.URLError):
                time.sleep(0.1)
        else:
            raise RuntimeError("Local services did not become healthy within 20 seconds")
        print("Open http://127.0.0.1:{}/meeting-intelligence".format(args.port), flush=True)
        print("Pair with the station token from the private tokens.json file; Ctrl-C stops both services.", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.25)
        raise RuntimeError("A local service exited; stopping the other service")
    except KeyboardInterrupt:
        print("Stopping local services; saved recordings remain in " + str(args.state_dir), flush=True)
    finally:
        stop_children(children)
        signal.signal(signal.SIGTERM, previous)


def service(role):
    import uvicorn
    if role == "_worker":
        from meeting_worker.config import Settings
        from meeting_worker.main import create_app
        config = Settings(_env_file=None)
        uvicorn.run(create_app(config), host="127.0.0.1", port=config.bind_port, workers=1, access_log=False)
    else:
        from meeting_station.config import Settings
        from meeting_station.local import create_local_app
        config = Settings.from_env()
        uvicorn.run(create_local_app(config, os.environ["MI_LOCAL_FRONTEND"]),
                    host="127.0.0.1", port=config.bind_port, workers=1, access_log=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "doctor", "start", "token"))
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--frontend", type=Path, default=ROOT / "web/frontend/dist")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--worker-port", type=int, default=8765)
    parser.add_argument("--allow-missing-models", action="store_true", help="Start an archive/UI for setup only; inference may fail")
    args = parser.parse_args(argv)
    args.state_dir, args.frontend = args.state_dir.resolve(), args.frontend.resolve()
    os.umask(0o077)
    try:
        if args.command == "init":
            initialize(args.state_dir)
            print("Local settings created/preserved in " + str(args.state_dir))
            print("Edit config.json with installed model paths, then run doctor. No models were downloaded.")
            return 0
        tokens = read_tokens(args.state_dir)
        if args.command == "token":
            print(tokens["station"])
            return 0
        config = read_configuration(args.state_dir)
        required, inference = prerequisites(config, args.frontend)
        for problem in required:
            print("SETUP: " + problem)
        for problem in inference:
            print("INFERENCE: " + problem)
        if required or (inference and (args.command == "doctor" or not args.allow_missing_models)):
            print("See docs/LOCAL_SETUP.md. No dependency or model downloads are performed.")
            return 1
        if args.command == "doctor":
            print("Setup checks passed; model files and Ollama inventory do not establish model accuracy.")
            return 0
        if inference:
            print("Starting with missing inference prerequisites. Reports are not ready; this is a setup check.", flush=True)
        start(args, config, tokens)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print("Local setup error: " + str(exc), file=sys.stderr)
        print("Run init first and follow docs/LOCAL_SETUP.md.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] in ("_worker", "_station"):
        service(sys.argv[1])
    else:
        raise SystemExit(main())
