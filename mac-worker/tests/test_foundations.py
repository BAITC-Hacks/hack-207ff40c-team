"""Regression cases for the technical review; all inputs/models are synthetic."""
import json
import os
import sqlite3
import sys
import threading
import time
import types
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from meeting_worker.config import Settings
from meeting_worker.main import create_app
from meeting_worker.schemas import ActionItem, Evidence, JobManifest, JobResult, JobStage, MeetingMetadata, MeetingProtocol, Transcript, TranscriptSegment

TOKEN = 'foundations-synthetic-worker-token'
AUTH = {'Authorization': 'Bearer ' + TOKEN}


def settings(path, **values):
    config = Settings(_env_file=None, data_dir=path, api_token=TOKEN, **values)
    config.prepare()
    return config


def submit(client, **manifest):
    return client.post('/v1/jobs', headers=AUTH,
        data={'manifest_json': json.dumps(dict(meeting_id='fixture', **manifest)), 'transcript': 'Synthetic meeting.'})


def test_deadline_survives_chronological_extraction_chunks(tmp_path, monkeypatch):
    from meeting_worker.protocol import call_ollama
    from datetime import date
    seen = []
    first = TranscriptSegment(id='first', text='Dana sends the report on 2026-10-01.')
    transcript = Transcript(model='fixture', raw_text=first.text, segments=[first,
        TranscriptSegment(id='later', text='Unrelated discussion. ' * 3000)])
    report = MeetingProtocol(metadata=MeetingMetadata(), action_items=[ActionItem(id='a', task='Send report',
        assignee='Dana', deadline_date='2026-10-01', evidence=Evidence(segment_ids=['first']))])
    def respond(request):
        if request.url.path == '/api/show':
            return httpx.Response(200, json={'model_info': {'synthetic': True}, 'details': {'format': 'gguf'}})
        payload = json.loads(request.content)
        dates = payload['format']['$defs']['ActionItem']['properties']['deadline_date']['enum']
        seen.append(dates)
        result = report.model_copy(deep=True)
        if '2026-10-01' not in dates:
            result.action_items[0].deadline_date = None
        return httpx.Response(200, json={'done': True, 'message': {'content': result.model_dump_json()}})
    original = httpx.Client
    monkeypatch.setattr('meeting_worker.protocol.httpx.Client', lambda **kw: original(**kw, transport=httpx.MockTransport(respond)))
    result = call_ollama(transcript, JobManifest(meeting_id='fixture'), settings(tmp_path, semantic_verification=False))
    assert len(seen) >= 2
    assert all('2026-10-01' in dates for dates in seen)
    assert result.action_items[0].deadline_date == date(2026, 10, 1)


def test_model_quotation_cannot_authorize_an_invented_date():
    from meeting_worker.protocol import _raw_schema
    previous = MeetingProtocol(metadata=MeetingMetadata(), action_items=[ActionItem(id='a', task='Report',
        deadline_date='2099-01-01', evidence=Evidence(segment_ids=['first'], quote='2099-01-01'))])
    schema = _raw_schema([TranscriptSegment(id='last', text='Continue.')], previous)
    assert schema['$defs']['ActionItem']['properties']['deadline_date']['enum'] == [None]


def test_calendar_date_is_not_split_between_extraction_requests(tmp_path, monkeypatch):
    from meeting_worker.protocol import call_ollama
    captured = []
    def respond(request):
        if request.url.path == '/api/show':
            return httpx.Response(200, json={'model_info': {'synthetic': True}, 'details': {'format': 'gguf'}})
        payload = json.loads(request.content)
        captured.append(payload)
        return httpx.Response(200, json={'done': True, 'message': {'content': MeetingProtocol(metadata=MeetingMetadata()).model_dump_json()}})
    original = httpx.Client
    monkeypatch.setattr('meeting_worker.protocol.httpx.Client', lambda **kw: original(**kw, transport=httpx.MockTransport(respond)))
    config, manifest = settings(tmp_path, semantic_verification=False), JobManifest(meeting_id='fixture')
    def extract(text):
        return call_ollama(Transcript(model='fixture', raw_text=text,
            segments=[TranscriptSegment(id='long', text=text)]), manifest, config)
    extract('x' * 100000)
    boundary = len(json.loads(captured[0]['messages'][1]['content'])['transcript'][0]['text'])
    # Place a real ISO date across the observed first request boundary. The
    # spaces make it a literal date, and total source length remains unchanged.
    text = 'x' * (boundary - 6) + ' 2026-10-01 ' + 'x' * (100000 - boundary - 6)
    captured.clear()
    extract(text)
    fragments = [json.loads(payload['messages'][1]['content'])['transcript'][0]['text'] for payload in captured]
    assert ''.join(fragments) == text
    containing = [i for i, fragment in enumerate(fragments) if '2026-10-01' in fragment]
    assert len(containing) == 1
    for payload in captured[containing[0]:]:
        assert '2026-10-01' in payload['format']['$defs']['ActionItem']['properties']['deadline_date']['enum']


def test_consumer_recovers_from_db_failure_and_health_exposes_it(tmp_path, monkeypatch):
    from meeting_worker.store import JobStore
    config = settings(tmp_path)
    with TestClient(create_app(config, start_worker=False)) as client:
        identity = submit(client).json()['id']
    failed, release, processed = threading.Event(), threading.Event(), threading.Event()
    claim = JobStore.claim
    count = 0
    def flaky(store):
        nonlocal count
        count += 1
        if count == 1:
            failed.set()
            raise sqlite3.OperationalError('synthetic lock')
        assert release.wait(3)
        return claim(store)
    class Pipeline:
        def __init__(self, config, store): self.store = store
        def run(self, job_id):
            self.store.update(job_id, JobStage.FAILED)
            processed.set()
    monkeypatch.setattr(JobStore, 'claim', flaky)
    with TestClient(create_app(config, pipeline_factory=Pipeline)) as client:
        try:
            assert failed.wait(2)
            deadline = time.monotonic() + 2
            while client.get('/health').status_code != 503 and time.monotonic() < deadline:
                time.sleep(.01)
            assert client.get('/health').status_code == 503
            assert submit(client).status_code == 503
            release.set()
            assert processed.wait(3)
            assert client.get('/health').status_code == 200
            assert client.get('/v1/jobs/' + identity, headers=AUTH).json()['stage'] == 'failed'
        finally:
            release.set()


def test_source_directory_is_synced_before_acceptance(tmp_path, monkeypatch):
    import meeting_worker.main as main
    synced = []
    real_sync = main.sync_directory
    def sync(directory):
        assert list(directory.iterdir())
        real_sync(directory)
        synced.append(directory)
    monkeypatch.setattr(main, 'sync_directory', sync)
    with TestClient(create_app(settings(tmp_path), start_worker=False)) as client:
        original = client.app.state.store.put
        def put(job):
            assert synced == [tmp_path / 'sources']
            original(job)
        monkeypatch.setattr(client.app.state.store, 'put', put)
        assert submit(client).status_code == 202


def test_failed_directory_sync_never_acknowledges_or_commits(tmp_path, monkeypatch):
    def fail(_): raise OSError('synthetic fsync failure')
    monkeypatch.setattr('meeting_worker.main.sync_directory', fail)
    with TestClient(create_app(settings(tmp_path), start_worker=False), raise_server_exceptions=False) as client:
        assert submit(client).status_code == 500
        assert client.app.state.store.list() == []
        assert list((tmp_path / 'sources').iterdir()) == []


def test_expanded_review_is_rejected_before_any_export_or_commit(tmp_path, monkeypatch):
    from meeting_worker import review
    from meeting_worker.schemas import ReviewRequest
    config = settings(tmp_path)
    with TestClient(create_app(config, start_worker=False)) as client:
        identity = submit(client).json()['id']
        path = tmp_path / 'results' / (identity + '.json')
        job = client.app.state.store.update(identity, JobStage.COMPLETED, result_path=str(path))
        text = 'Source passage ' * 14000  # ~200 KiB, repeated by the small review request.
        original = JobResult(job=job, protocol=MeetingProtocol(metadata=MeetingMetadata()),
            transcript=Transcript(model='synthetic', raw_text=text, segments=[TranscriptSegment(id='s1', text=text)]), exports={})
        saved = original.model_dump_json().encode()
        path.write_bytes(saved)
        def export(*args, **kwargs): pytest.fail('Oversized review reached export generation')
        monkeypatch.setattr(review, 'write_exports', export)
        request = ReviewRequest(request_id=uuid4(), expected_revision=0, reviewer='Fixture',
            new_actions=[dict(task='Task ' + str(i), segment_ids=['s1'], review_status='needs_review') for i in range(50)])
        assert len(request.model_dump_json()) < 20000
        with pytest.raises(review.ReviewError) as error:
            review.save_review(config, client.app.state.store, identity, request)
        assert error.value.status == 413
        assert path.read_bytes() == saved
        assert client.app.state.store.get(identity).result_path == str(path)
        assert list((tmp_path / 'exports').iterdir()) == []


def test_long_multilingual_assignment_spans_pages_without_losing_tail(tmp_path):
    from meeting_worker.bundle import write_exports
    text = ('Подготовить финансовый отчёт и проверить данные. Қазақша есеп. ' * 66) + 'Конец поручения.'
    protocol = MeetingProtocol(metadata=MeetingMetadata(), action_items=[ActionItem(id='a', task=text)])
    paths = write_exports(tmp_path, protocol, Transcript(model='fixture', raw_text='', segments=[]))
    reader = PdfReader(paths['pdf'])
    assert len(reader.pages) > 1
    extracted = ' '.join(' '.join(page.extract_text() for page in reader.pages).split())
    assert 'Конец поручения.' in extracted and 'Қазақша есеп.' in extracted
    assert set(paths) == {'pdf', 'json', 'csv', 'ics', 'docx'}


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'), 0, -1])
@pytest.mark.parametrize('field', ['audio_timeout', 'upload_timeout', 'max_audio_seconds', 'ollama_timeout'])
def test_resource_limits_reject_nonfinite_and_nonpositive_values(field, value):
    with pytest.raises(ValueError): Settings(_env_file=None, **{field: value})


def test_calendar_text_normalizes_crlf_and_bare_cr(tmp_path):
    from meeting_worker.exports import export_ics
    path = tmp_path / 'meeting.ics'
    protocol = MeetingProtocol(metadata=MeetingMetadata(), action_items=[ActionItem(id='a',
        task='Report\r\nNext\rLast\nLine', assignee='Name\rEND:VTODO', source_check='passed')])
    export_ics(path, protocol)
    content = path.read_bytes()
    assert b'\r' not in content.replace(b'\r\n', b'')
    assert b'SUMMARY:Report\\nNext\\nLast\\nLine\r\n' in content
    assert content.count(b'\r\nEND:VTODO\r\n') == 1


@pytest.mark.parametrize('directory', [False, True])
def test_pyannote_loader_receives_a_local_config_file(tmp_path, monkeypatch, directory):
    from meeting_worker.diarization import diarize
    config_file = tmp_path / 'config.yaml'
    config_file.write_text('pipeline: {}')
    paths = []
    class Pipeline:
        @staticmethod
        def from_pretrained(path):
            paths.append(path)
            return lambda *args, **kw: types.SimpleNamespace(itertracks=lambda **kw: [])
    monkeypatch.setitem(sys.modules, 'pyannote', types.ModuleType('pyannote'))
    module = types.ModuleType('pyannote.audio')
    module.Pipeline = Pipeline
    monkeypatch.setitem(sys.modules, 'pyannote.audio', module)
    diarize(tmp_path / 'audio.wav', Transcript(model='fixture', raw_text='', segments=[]),
        settings(tmp_path, diarization_backend='pyannote', diarization_model=str(tmp_path if directory else config_file)))
    assert paths == [str(config_file.resolve())]


def test_selected_pyannote_readiness_does_not_depend_on_sherpa(tmp_path, monkeypatch):
    from meeting_worker.asr import capabilities
    config_file = tmp_path / 'config.yaml'
    config_file.write_text('pipeline: {}')
    monkeypatch.setattr('meeting_worker.asr.importlib.util.find_spec', lambda name: object() if name == 'pyannote.audio' else None)
    assert capabilities(settings(tmp_path, diarization_backend='pyannote', diarization_model=str(config_file)))['diarization']['ready']
    assert not capabilities(settings(tmp_path, diarization_backend='pyannote', diarization_model=str(tmp_path / 'missing')))['diarization']['ready']


def test_diarization_rejects_untimed_speech():
    from meeting_worker.diarization import assign_speakers, SpeakerTurn
    transcript = Transcript(model='gigaam-fixture', raw_text='Hello', segments=[TranscriptSegment(id='s1', text='Hello')])
    with pytest.raises(RuntimeError, match='timed ASR'):
        assign_speakers(transcript, [SpeakerTurn(0, 1, 'A')])


@pytest.mark.parametrize('mode', ['timeout', 'cancel'])
def test_hung_model_process_is_killed_and_reaped(tmp_path, mode):
    from meeting_worker.local_audio import command, AudioError, ProcessingCancelled
    pid_file = tmp_path / 'pid'
    script = 'import os,pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(60)'
    start = time.monotonic()
    error = ProcessingCancelled if mode == 'cancel' else AudioError
    with pytest.raises(error):
        command([sys.executable, '-S', '-c', script, str(pid_file)], tmp_path, .4 if mode == 'timeout' else 10,
                cancelled=(lambda: pid_file.exists()) if mode == 'cancel' else None)
    assert time.monotonic() - start < 3
    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError): os.kill(pid, 0)


def test_cancel_after_asr_prevents_diarization_and_extraction(tmp_path, monkeypatch):
    import wave
    import meeting_worker.pipeline as module
    config = settings(tmp_path, enable_diarization=True)
    with TestClient(create_app(config, start_worker=False)) as client:
        identity = submit(client, diarization=True).json()['id']
        client.app.state.store.update(identity, JobStage.PREPROCESSING, source_kind='audio')
        calls = []
        def convert(args, *pos, **kw):
            with wave.open(args[-1], 'wb') as audio:
                audio.setparams((1, 2, 16000, 0, 'NONE', 'PCM'))
                audio.writeframes(b'\0' * 32000)
        def model(operation, *args, **kw):
            calls.append(operation)
            client.app.state.store.update(identity, JobStage.CANCELLED)
            return Transcript(model='fixture', raw_text='Hello', segments=[])
        monkeypatch.setattr(module, 'command', convert)
        monkeypatch.setattr(module, 'run_model', model)
        monkeypatch.setattr(module, 'call_ollama', lambda *args: pytest.fail('Cancelled job reached extraction'))
        client.app.state.pipeline.run(identity)
        assert calls == ['asr']
        assert client.app.state.store.get(identity).stage == JobStage.CANCELLED


def test_gigaam_diarization_is_rejected_before_starting_audio_tools(tmp_path, monkeypatch):
    import meeting_worker.pipeline as module
    with TestClient(create_app(settings(tmp_path, asr_kk_ru='gigaam', enable_diarization=True), start_worker=False)) as client:
        identity = submit(client, diarization=True).json()['id']
        client.app.state.store.update(identity, JobStage.PREPROCESSING, source_kind='audio')
        monkeypatch.setattr(module, 'command', lambda *args, **kw: pytest.fail('Unsupported profile started audio conversion'))
        client.app.state.pipeline.run(identity)
        job = client.app.state.store.get(identity)
        assert job.stage == JobStage.FAILED and 'no timed segment contract' in job.error_message


def test_model_stage_runs_in_real_child_with_offline_config_and_private_cleanup(tmp_path):
    from meeting_worker.model_process import run_model
    ffmpeg, whisper = tmp_path / 'ffmpeg', tmp_path / 'whisper'
    ffmpeg.write_text('#!' + sys.executable + '\nimport sys,wave\nwith wave.open(sys.argv[-1],"wb") as w:\n w.setparams((1,2,16000,0,"NONE","PCM"))\n w.writeframes(b"\\0"*32000)\n')
    whisper.write_text('#!' + sys.executable + '\nimport os,sys,json,pathlib\nassert os.environ["HF_HUB_OFFLINE"] == "1"\nassert os.environ["TRANSFORMERS_OFFLINE"] == "1"\np=pathlib.Path(sys.argv[sys.argv.index("-of")+1]+".json")\np.write_text(json.dumps({"transcription":[{"text":"Есеп дайын","offsets":{"from":0,"to":900}}]}))\n')
    ffmpeg.chmod(0o700)
    whisper.chmod(0o700)
    model, audio = tmp_path / 'model.bin', tmp_path / 'audio.wav'
    model.write_bytes(b'synthetic-model-placeholder')
    audio.write_bytes(b'synthetic-audio-placeholder')
    config = settings(tmp_path, ffmpeg_binary=str(ffmpeg), whisper_binary=str(whisper), whisper_model=str(model), audio_timeout=10)
    result = run_model('asr', config, audio, profile='whisper-cpp')
    assert result.segments[0].text == 'Есеп дайын'
    assert result.segments[0].start == 0 and result.segments[0].end == .9
    assert list((tmp_path / 'work').iterdir()) == []


@pytest.mark.skipif(os.name != 'posix', reason='Local worker process-group deployment targets are Linux and macOS')
@pytest.mark.parametrize('mode', ['cancel', 'timeout'])
def test_model_cancellation_reaps_nested_audio_executable(tmp_path, mode):
    from meeting_worker.local_audio import AudioError, ProcessingCancelled
    from meeting_worker.model_process import run_model
    ffmpeg, whisper, pid_file = tmp_path / 'ffmpeg', tmp_path / 'whisper', tmp_path / 'nested-pids.json'
    ffmpeg.write_text('#!' + sys.executable + '\nimport sys,wave\nwith wave.open(sys.argv[-1],"wb") as w:\n w.setparams((1,2,16000,0,"NONE","PCM"))\n w.writeframes(b"\\0"*32000)\n')
    whisper.write_text('#!' + sys.executable + '\nimport os,time,pathlib,json\n'
        + f'pathlib.Path({str(pid_file)!r}).write_text(json.dumps([os.getppid(),os.getpid()]))\n'
        + 'time.sleep(60)\n')
    ffmpeg.chmod(0o700)
    whisper.chmod(0o700)
    model, audio = tmp_path / 'model.bin', tmp_path / 'audio.wav'
    model.write_bytes(b'synthetic-model-placeholder')
    audio.write_bytes(b'synthetic-audio-placeholder')
    config = settings(tmp_path, ffmpeg_binary=str(ffmpeg), whisper_binary=str(whisper), whisper_model=str(model),
        audio_timeout=1.5 if mode == 'timeout' else 10)
    try:
        with pytest.raises(ProcessingCancelled if mode == 'cancel' else AudioError):
            run_model('asr', config, audio, profile='whisper-cpp',
                cancelled=(lambda: pid_file.exists()) if mode == 'cancel' else None)
        assert pid_file.exists(), 'Synthetic nested executable never started'
        for pid in json.loads(pid_file.read_text()):
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(.02)
            with pytest.raises(ProcessLookupError): os.kill(pid, 0)
        assert list((tmp_path / 'work').iterdir()) == []
    finally:
        if pid_file.exists():
            for pid in json.loads(pid_file.read_text()):
                try: os.kill(pid, 9)
                except ProcessLookupError: pass
