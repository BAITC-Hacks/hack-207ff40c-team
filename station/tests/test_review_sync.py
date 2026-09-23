"""Station recovery after an ambiguous review acknowledgement; fake worker transport."""
import copy
from uuid import uuid4

from fastapi.testclient import TestClient

from meeting_station.config import Settings
from meeting_station.main import create_app
from meeting_station.models import Manifest
from meeting_station.worker import WorkerUnavailable


class ReviewingWorker:
    def __init__(self, identity):
        self.result = {"job": {"id": identity}, "review_revision": 0,
            "transcript": {"raw_text": "Synthetic test", "segments": []},
            "protocol": {"metadata": {"title": "Synthetic review"}}, "exports": {"docx": "worker-path"}}
        self.fail_exports = False

    async def close(self):
        pass

    async def json(self, method, path, **kwargs):
        if method == "POST":
            if kwargs["json"]["expected_revision"] != self.result["review_revision"]:
                raise WorkerUnavailable("Conflict", "ENGINE_HTTP_409")
            self.result["review_revision"] += 1
        return copy.deepcopy(self.result)

    async def export(self, job_id, kind, target, revision=None):
        if self.fail_exports:
            raise WorkerUnavailable("Synthetic connection lost after the review committed")
        assert revision == self.result["review_revision"]
        target.write_bytes(("revision-" + str(revision)).encode())


def test_reload_can_recover_after_remote_commit_and_failed_export_download(tmp_path):
    identity = str(uuid4())
    token = "station-review-sync-fixture-token"
    worker = ReviewingWorker(identity)
    settings = Settings(token=token, worker_token="worker-review-sync-fixture-token", data_dir=tmp_path)
    with TestClient(create_app(settings, mac=worker, start_worker=False)) as client:
        client.headers["Authorization"] = "Bearer " + token
        store = client.app.state.store
        store.create(identity, Manifest(meeting_id=identity).model_dump(mode="json"), "text", "fixture.txt", "fixture.txt", 14, "synthetic")
        store.complete(identity, copy.deepcopy(worker.result))
        directory = store.exports / identity
        directory.mkdir()
        (directory / "meeting.pdf").write_bytes(b"previous-complete-report")
        worker.fail_exports = True
        path = "/v1/jobs/" + identity
        failed = client.post(path + "/review", json={"request_id": str(uuid4()), "expected_revision": 0})
        assert failed.status_code == 503
        assert worker.result["review_revision"] == 1
        assert client.get(path + "/result").json()["review_revision"] == 0
        assert client.get(path + "/export/pdf").content == b"previous-complete-report"
        worker.fail_exports = False
        # A reloaded browser no longer has the first idempotency key. Conflict
        # handling must synchronize the committed version before asking to reload.
        conflict = client.post(path + "/review", json={"request_id": str(uuid4()), "expected_revision": 0})
        assert conflict.status_code == 409
        assert client.get(path + "/result").json()["review_revision"] == 1
        assert client.get(path + "/export/pdf").content == b"revision-1"
        assert client.get(path + "/export/docx").content == b"revision-1"
        assert (directory / "meeting.pdf").read_bytes() == b"previous-complete-report"
        saved = client.post(path + "/review", json={"request_id": str(uuid4()), "expected_revision": 1})
        assert saved.status_code == 200 and saved.json()["review_revision"] == 2
