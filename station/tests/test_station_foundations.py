"""Station concurrency and transport regressions from the technical review."""
import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from meeting_station.models import Manifest
from meeting_station.worker import MacClient, WorkerUnavailable
from test_station import client, settings, submit, ready, FakeMac


def test_stale_cancel_ack_cannot_erase_new_retry(client):
    identity = submit(client).json()['id']
    worker, store, mac = client.app.state.worker, client.app.state.store, client.app.state.mac
    asyncio.run(worker.run_once())
    store.cancel(identity)
    original = mac.json
    async def cancel_then_retry(method, path, **kw):
        remote = await original(method, path, **kw)
        if path.endswith('/cancel'):
            store.retry(identity)
        return remote
    mac.json = cancel_then_retry
    asyncio.run(worker.run_once())
    assert store.get(identity)['stage'] == 'queued'
    assert store.work()['action'] == 'retry'
    asyncio.run(worker.run_once())
    assert mac.jobs[identity]['stage'] == 'queued'
    assert store.get(identity)['stage'] == 'queued'


def test_stale_missing_job_or_failure_does_not_modify_new_intent(client):
    identity = submit(client).json()['id']
    store = client.app.state.store
    row = store.work()
    store.cancel(identity)
    store.retry(identity)
    before = store.get(identity)
    store.remote_missing(identity, generation=row['generation'])
    store.defer(identity, 'stale failure', generation=row['generation'], terminal=True)
    assert store.get(identity) == before


def test_stale_result_completion_cannot_complete_retried_job(client):
    identity = submit(client).json()['id']
    store = client.app.state.store
    old_generation = store.work()['generation']
    store.cancel(identity)
    store.retry(identity)
    store.complete(identity, {'job': {'id': identity}, 'protocol': {}, 'transcript': {}, 'exports': {}}, generation=old_generation)
    assert store.get(identity)['stage'] == 'queued'


def test_cancel_and_retry_during_first_upload_retains_remote_existence(client):
    identity = submit(client).json()['id']
    store, mac, worker = client.app.state.store, client.app.state.mac, client.app.state.worker
    upload = mac.upload
    async def interleave(job, source):
        remote = await upload(job, source)
        store.cancel(identity)
        store.retry(identity)
        return remote
    mac.upload = interleave
    asyncio.run(worker.run_once())
    assert store.get(identity)['stage'] == 'queued'
    assert store.get(identity)['station']['worker_submitted']
    asyncio.run(worker.run_once())
    assert len(mac.uploads) == 1


@pytest.mark.parametrize('terminal', ['cancelled', 'failed'])
def test_retry_conflict_while_old_inference_exits_keeps_retry_command(client, terminal):
    identity = submit(client).json()['id']
    store, mac, worker = client.app.state.store, client.app.state.mac, client.app.state.worker
    asyncio.run(worker.run_once())
    store.cancel(identity)
    store.retry(identity)
    mac.jobs[identity] = {'id': identity, 'stage': terminal}
    original = mac.json
    busy = [True]
    async def retry_busy(method, path, **kw):
        if path.endswith('/retry') and busy[0]:
            raise WorkerUnavailable('Old inference still active', 'ENGINE_HTTP_409')
        return await original(method, path, **kw)
    mac.json = retry_busy
    asyncio.run(worker.run_once())
    assert store.get(identity)['stage'] == 'queued'
    assert store.get(identity)['error_code'] == 'ENGINE_RETRY_PENDING'
    ready(client)
    assert store.work()['action'] == 'retry'
    busy[0] = False
    asyncio.run(worker.run_once())
    assert store.get(identity)['stage'] == 'queued'
    assert store.get(identity)['error_code'] is None
    assert mac.jobs[identity]['stage'] == 'queued'


def test_invalid_speaker_range_is_rejected_before_archival(client):
    response = client.post('/v1/jobs', data={'manifest_json': json.dumps({
        'meeting_id': 'fixture', 'min_speakers': 3, 'max_speakers': 1}), 'transcript': 'Synthetic meeting'})
    assert response.status_code == 422
    assert client.app.state.store.list() == []
    assert list(client.app.state.store.sources.iterdir()) == []
    with pytest.raises(ValueError): Manifest(meeting_id='fixture', min_speakers=3, max_speakers=1)


@pytest.mark.parametrize('status', [400, 409, 413, 415, 422])
def test_deterministic_rejected_upload_stops_retrying_but_keeps_source(client, status):
    identity = submit(client).json()['id']
    async def reject(*args):
        raise WorkerUnavailable('Synthetic invalid upload', 'ENGINE_HTTP_' + str(status))
    client.app.state.mac.upload = reject
    asyncio.run(client.app.state.worker.run_once())
    store = client.app.state.store
    assert store.get(identity)['stage'] == 'failed'
    assert store.source(identity).read_bytes() == b'test audio'
    ready(client)
    assert not asyncio.run(client.app.state.worker.run_once())


@pytest.mark.parametrize('kind,parts', [('pdf', [b'%', b'P', b'DF', b'-1.7\nfixture']),
                                      ('docx', [b'P', b'K', b'\x03', b'\x04fixture'])])
def test_export_signature_can_span_every_transport_chunk(settings, tmp_path, kind, parts):
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for part in parts:
                yield part
    async def run():
        mac = MacClient(settings, transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=Stream())))
        target = tmp_path / ('meeting.' + kind)
        try:
            await mac.export('fixture', kind, target)
            assert target.read_bytes() == b''.join(parts)
        finally:
            await mac.close()
    asyncio.run(run())


def test_slow_polling_jobs_cannot_starve_a_new_upload(client, monkeypatch):
    import meeting_station.store as module
    now = [1000.0]
    monkeypatch.setattr(module.time, 'time', lambda: now[0])
    worker, store = client.app.state.worker, client.app.state.store
    one, two = submit(client).json()['id'], submit(client).json()['id']
    asyncio.run(worker.run_once())
    asyncio.run(worker.run_once())
    now[0] += 3
    third = submit(client).json()['id']
    assert store.work()['id'] == third
    asyncio.run(worker.run_once())
    assert [identity for identity, _ in client.app.state.mac.uploads] == [one, two, third]
    # Polling remains fair among already submitted jobs, too.
    assert store.work()['id'] == one


def test_recording_limit_matches_worker_and_pcm_byte_budget(settings):
    assert replace(settings, max_audio_seconds=14400).recording_seconds == 14400
    assert replace(settings, max_audio_seconds=10).recording_seconds == 10
    assert replace(settings, max_upload_bytes=4096 + 32000 * 3).recording_seconds == 3
    assert replace(settings, max_upload_bytes=32).recording_seconds == 0


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
@pytest.mark.parametrize('field', ['poll_seconds', 'request_timeout', 'max_audio_seconds'])
def test_station_resource_limits_must_be_finite(settings, field, value):
    with pytest.raises(ValueError): replace(settings, **{field: value})


def test_browser_receives_same_duration_limit_as_local_recorder(settings):
    from meeting_station.browser import BrowserCapture, BrowserClient
    async def run():
        browser = BrowserClient(replace(settings, max_audio_seconds=60))
        try:
            assert BrowserCapture(None, browser).capture_limits() == {'max_seconds': 60}
        finally:
            await browser.close()
    asyncio.run(run())
