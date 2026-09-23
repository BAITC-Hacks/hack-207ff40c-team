"""Opt-in check of real Python child processes and the built frontend, without inference."""
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest


@pytest.mark.skipif(os.getenv("MI_RUN_LOCAL_HTTP_TESTS") != "1", reason="Requires explicit local socket access and the built local frontend")
def test_real_local_services_and_clean_shutdown(tmp_path):
    root = Path(__file__).resolve().parents[2]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    state = tmp_path / "local-http"
    subprocess.run([sys.executable, "scripts/run-local.py", "init", "--state-dir", str(state)],
                   cwd=root, check=True, capture_output=True)
    probes = [socket.socket(), socket.socket()]
    try:
        for probe in probes:
            probe.bind(("127.0.0.1", 0))
        ports = [probe.getsockname()[1] for probe in probes]
    finally:
        for probe in probes:
            probe.close()
    process = subprocess.Popen([sys.executable, "scripts/run-local.py", "start", "--state-dir", str(state),
                                "--port", str(ports[0]), "--worker-port", str(ports[1]), "--allow-missing-models"],
                               cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = "http://127.0.0.1:" + str(ports[0])
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            assert process.poll() is None, process.stdout.read()
            try:
                with opener.open(base + "/meeting-intelligence", timeout=1) as response:
                    html = response.read().decode()
                break
            except urllib.error.URLError:
                time.sleep(0.1)
        else:
            pytest.fail("Local HTTP startup timed out")
        javascript = re.search(r'<script[^>]+src="([^"]+)"', html).group(1)
        with opener.open(base + javascript) as response:
            assert response.status == 200
        with opener.open(base + "/meeting-build.json") as response:
            assert json.load(response) == {"version": 1, "station": True, "local": True}
        with opener.open(base + "/api/meeting-worker/health") as response:
            assert json.load(response)["role"] == "station"
        with pytest.raises(urllib.error.HTTPError) as error:
            opener.open(base + "/api/meeting-worker/v1/jobs")
        assert error.value.code == 401
        token = json.loads((state / "tokens.json").read_text())["station"]
        headers = {"Authorization": "Bearer " + token}
        request = urllib.request.Request(base + "/api/meeting-worker/v1/capabilities", headers=headers)
        with opener.open(request) as response:
            capabilities = json.load(response)
        assert capabilities["station"]["worker_connected"] is True
        assert capabilities["readiness"]["whisper-cpp"]["ready"] is False
        request = urllib.request.Request(base + "/api/meeting-worker/v1/jobs", headers=headers)
        with opener.open(request) as response:
            assert json.load(response) == []
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
        output = process.communicate(timeout=15)[0]
        assert process.returncode == 0, output
    for port in ports:
        with socket.socket() as probe:
            # Closed listeners can leave TCP TIME_WAIT entries; connect tests
            # whether a service remains rather than whether the port can bind.
            assert probe.connect_ex(("127.0.0.1", port)) != 0
