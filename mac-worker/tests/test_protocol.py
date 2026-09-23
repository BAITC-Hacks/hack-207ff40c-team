import hashlib
import json
from pathlib import Path

import httpx
import pytest

from meeting_worker.config import Settings
from meeting_worker.protocol import _verify_facts, validate_evidence
from meeting_worker.schemas import (
    ActionItem, Evidence, MeetingMetadata, MeetingProtocol, Transcript, TranscriptSegment,
)


def test_evidence_is_copied_from_transcript() -> None:
    transcript = Transcript(
        language="ru", model="fixture", raw_text="Айбек подготовит отчёт.",
        segments=[TranscriptSegment(
            id="seg_00001", start=10, end=13, speaker="SPEAKER_01",
            text="Айбек подготовит отчёт.",
        )],
    )
    protocol = MeetingProtocol(
        metadata=MeetingMetadata(),
        action_items=[ActionItem(
            id="action_01", task="Подготовить отчёт", assignee="Айбек",
            evidence=Evidence(segment_ids=["seg_00001"]),
        )],
    )

    checked = validate_evidence(protocol, transcript)
    item = checked.action_items[0]
    assert item.source_check == "passed"
    assert item.evidence.quote == "Айбек подготовит отчёт."
    assert item.evidence.start == 10
    assert item.evidence.speaker == "SPEAKER_01"


def test_missing_evidence_requires_review() -> None:
    transcript = Transcript(language="kk", model="fixture", raw_text="", segments=[])
    protocol = MeetingProtocol(
        metadata=MeetingMetadata(),
        action_items=[ActionItem(id="action_01", task="Есеп дайындау")],
    )
    checked = validate_evidence(protocol, transcript)
    assert checked.action_items[0].source_check == "unavailable"
    assert checked.action_items[0].review_status == "needs_review"


def test_generated_speaker_names_are_never_trusted():
    transcript = Transcript(model="fixture", raw_text="Есеп дайындау", segments=[
        TranscriptSegment(id="s1", speaker="SPEAKER_01", text="Есеп дайындау")])
    protocol = MeetingProtocol(metadata=MeetingMetadata(), action_items=[
        ActionItem(id="a1", task="Есеп дайындау", evidence=Evidence(segment_ids=["s1"], speaker_name="Invented director"))])
    checked = validate_evidence(protocol, transcript)
    assert checked.action_items[0].evidence.speaker_name is None
    transcript.segments[0].speaker_name = "Айдана"
    checked = validate_evidence(protocol, transcript)
    assert checked.action_items[0].evidence.speaker_name == "Айдана"
    checked.action_items[0].evidence.segment_ids = ["missing"]
    assert validate_evidence(checked, transcript).action_items[0].evidence.speaker_name is None


def test_overview_requests_only_segment_ids_even_when_evidence_schema_grows():
    from meeting_worker.protocol import synthesize_overview
    from meeting_worker.schemas import JobManifest
    transcript = Transcript(model="fixture", raw_text="Report", segments=[TranscriptSegment(id="s1", text="Report")])
    def respond(request):
        payload = json.loads(request.content)
        assert set(payload["format"]["$defs"]["Evidence"]["properties"]) == {"segment_ids"}
        return httpx.Response(200, json={"done": True, "message": {"content": json.dumps({"title": "Report", "language": "en", "summary": [], "topics": []})}})
    with httpx.Client(base_url="http://127.0.0.1", transport=httpx.MockTransport(respond)) as client:
        synthesize_overview(MeetingProtocol(metadata=MeetingMetadata()), transcript,
            JobManifest(meeting_id="fixture"), Settings(_env_file=None), client, 24000)


def test_summary_copies_only_reviewed_facts_with_matching_provenance():
    from meeting_worker.protocol import derive_summary
    from meeting_worker.schemas import JobManifest, ProtocolItem
    protocol = MeetingProtocol(metadata=MeetingMetadata(),
        executive_summary=['All other proposed tasks were explicitly cancelled.'],
        decisions=[ProtocolItem(id='decision_001', text='Postpone the launch until the report is complete.',
                                source_check='passed', evidence=Evidence(segment_ids=['s3'], quote='We decided to postpone the launch until the report is complete.'))],
        action_items=[ActionItem(id='action_001', task='Send launch report', assignee='Timur', deadline_text='Monday',
                                 source_check='passed', evidence=Evidence(segment_ids=['s2'], quote='Timur will send it Monday.'))],
        risks=[ProtocolItem(id='risk_001', text='All other proposed tasks were explicitly cancelled.',
                            source_check='failed', review_status='needs_review', evidence=Evidence(segment_ids=['s2']))])
    derive_summary(protocol, JobManifest(meeting_id='fixture', output_language='en'))
    assert protocol.executive_summary == [
        'Postpone the launch until the report is complete.',
        'Timur is responsible for the task “Send launch report”.', 'The deadline for “Send launch report” is Monday.']
    assert [item.item_id for item in protocol.executive_summary_sources] == ['decision_001', 'action_001', 'action_001']
    assert protocol.executive_summary_sources[1].evidence.segment_ids == ['s2']
    protocol.action_items[0].evidence.segment_ids.append('later-mutation')
    assert protocol.executive_summary_sources[1].evidence.segment_ids == ['s2']


def test_summary_excludes_unavailable_and_needs_review_facts_and_keeps_output_language():
    from meeting_worker.protocol import derive_summary
    from meeting_worker.schemas import JobManifest, ProtocolItem
    protocol = MeetingProtocol(metadata=MeetingMetadata(),
        decisions=[ProtocolItem(id='d1', text='Unverified decision')],
        action_items=[ActionItem(id='a1', task='Отправить отчёт', assignee='Тимур', deadline_text='понедельник',
                                 source_check='passed', evidence=Evidence(segment_ids=['s1'])),
                      ActionItem(id='a2', task='Needs review', source_check='passed', review_status='needs_review')])
    derive_summary(protocol, JobManifest(meeting_id='fixture', output_language='same'), 'ru')
    assert protocol.executive_summary == ['Отправить отчёт.', 'За задачу «Отправить отчёт» отвечает Тимур.',
                                           'Срок задачи «Отправить отчёт»: понедельник.']
    assert len(protocol.executive_summary_sources) == 3


def test_sparse_speech_summary_is_not_padded_with_invented_information():
    from meeting_worker.protocol import derive_summary
    from meeting_worker.schemas import JobManifest, ProtocolItem
    manifest = JobManifest(meeting_id='sparse')
    protocol = MeetingProtocol(metadata=MeetingMetadata(), decisions=[ProtocolItem(
        id='decision_001', text='Proceed with the test', source_check='passed', evidence=Evidence(segment_ids=['s1']))])
    derive_summary(protocol, manifest)
    assert protocol.executive_summary == ['Proceed with the test.']
    assert len(protocol.executive_summary_sources) == 1
    protocol.decisions.clear()
    derive_summary(protocol, manifest)
    assert protocol.executive_summary == [] and protocol.executive_summary_sources == []


def test_summary_keeps_five_fact_limit_with_aligned_sources():
    from meeting_worker.protocol import derive_summary
    from meeting_worker.schemas import JobManifest, ProtocolItem
    protocol = MeetingProtocol(metadata=MeetingMetadata(), decisions=[ProtocolItem(
        id=f'decision_{index}', text=f'Verified outcome {index}', source_check='passed', evidence=Evidence(segment_ids=[f's{index}']))
        for index in range(7)])
    derive_summary(protocol, JobManifest(meeting_id='many'))
    assert len(protocol.executive_summary) == len(protocol.executive_summary_sources) == 5
    assert [item.item_id for item in protocol.executive_summary_sources] == [f'decision_{index}' for index in range(5)]


def test_summary_balances_decisions_actions_and_risks():
    from meeting_worker.protocol import derive_summary
    from meeting_worker.schemas import JobManifest, ProtocolItem
    supported = lambda item_id, text: ProtocolItem(id=item_id, text=text, source_check='passed', evidence=Evidence(segment_ids=[item_id]))
    protocol = MeetingProtocol(metadata=MeetingMetadata(),
        decisions=[supported(f'd{index}', f'Decision {index}') for index in range(4)],
        action_items=[ActionItem(id=f'a{index}', task=f'Task {index}', assignee='Owner', source_check='passed', evidence=Evidence(segment_ids=[f'a{index}'])) for index in range(2)],
        risks=[supported('r1', 'Power loss could interrupt recording')])
    derive_summary(protocol, JobManifest(meeting_id='balanced'))
    assert [source.item_id for source in protocol.executive_summary_sources] == ['d0', 'a0', 'd1', 'a1', 'r1']


def test_citation_validation_rejects_reversed_negation():
    from meeting_worker.schemas import ProtocolItem
    transcript = Transcript(model='fixture', raw_text='Processing resumes without duplicates.', segments=[
        TranscriptSegment(id='s1', text='Processing resumes without duplicates.')])
    protocol = MeetingProtocol(metadata=MeetingMetadata(), risks=[ProtocolItem(
        id='r1', text='Processing could resume with duplicates.', evidence=Evidence(segment_ids=['s1']))])
    checked = validate_evidence(protocol, transcript)
    assert checked.risks[0].source_check == 'failed'
    assert checked.risks[0].review_status == 'needs_review'


def test_citation_validation_preserves_matching_negative_claim():
    from meeting_worker.schemas import ProtocolItem
    transcript = Transcript(model='fixture', raw_text='We are not adopting cloud transcription.', segments=[
        TranscriptSegment(id='s1', text='We are not adopting cloud transcription.')])
    protocol = MeetingProtocol(metadata=MeetingMetadata(), decisions=[ProtocolItem(
        id='d1', text='Cloud transcription was not adopted.', evidence=Evidence(segment_ids=['s1']))])
    assert validate_evidence(protocol, transcript).decisions[0].source_check == 'passed'


def test_citation_validation_does_not_reject_a_task_that_checks_for_absence():
    transcript = Transcript(model='fixture', raw_text='Test that processing resumes without duplicates.', segments=[
        TranscriptSegment(id='s1', text='Test that processing resumes without duplicates.')])
    protocol = MeetingProtocol(metadata=MeetingMetadata(), action_items=[ActionItem(
        id='a1', task='Check processing for duplicates', evidence=Evidence(segment_ids=['s1']))])
    assert validate_evidence(protocol, transcript).action_items[0].source_check == 'passed'


def test_citation_validation_never_preserves_unchecked_summary():
    transcript = Transcript(model='fixture', raw_text='Send the report.', segments=[TranscriptSegment(id='s1', text='Send the report.')])
    protocol = MeetingProtocol(metadata=MeetingMetadata(), executive_summary=['All other proposed tasks were explicitly cancelled.'])
    assert validate_evidence(protocol, transcript).executive_summary == []


VERIFICATION_FIXTURE = Path(__file__).with_name('fixtures') / 'protocol_verification.json'
VERIFICATION_CASES = json.loads(VERIFICATION_FIXTURE.read_text())['cases']


def test_adversarial_verification_fixture_is_frozen():
    assert hashlib.sha256(VERIFICATION_FIXTURE.read_bytes()).hexdigest() == (
        'c41d1b1272b9a9ac5dc99f886bd10eac3de763f53fbd4654e00935fac3c429c0')


def verification_case(case):
    transcript = Transcript(model='synthetic-fixture', language=case['language'], raw_text='',
        segments=[TranscriptSegment(**segment) for segment in case['segments']])
    protocol = MeetingProtocol(metadata=MeetingMetadata(), action_items=[ActionItem(
        id='action_001', **case['claim'], evidence=Evidence(segment_ids=case['cited_ids']))])
    return validate_evidence(protocol, transcript), transcript


@pytest.mark.parametrize('case', VERIFICATION_CASES, ids=lambda case: case['id'])
def test_verifier_sends_all_fields_and_complete_chronological_context(case):
    protocol, transcript = verification_case(case)
    requests = []

    def handler(request):
        assert request.url.host == '127.0.0.1' and request.url.path == '/api/chat'
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload['truncate'] is False and payload['shift'] is False
        prompt = payload['messages'][0]['content']
        assert 'conditional' in prompt and 'cancelled' in prompt
        assert 'deadline_date' in prompt and 'same task' in prompt
        claims = json.loads(payload['messages'][1]['content'])
        assert claims[0]['claim'] == case['claim']
        assert [source['id'] for source in claims[0]['evidence']] == case['cited_ids']
        context = json.loads(payload['messages'][2]['content'])
        expected = [segment for _, segment in sorted(enumerate(case['segments']),
            key=lambda pair: (pair[1].get('start', pair[0]), pair[0]))]
        assert context['context_complete'] is True
        assert [segment['id'] for segment in context['chronological_transcript']] == [segment['id'] for segment in expected]
        assert [segment['text'] for segment in context['chronological_transcript']] == [segment['text'] for segment in expected]
        # These are fixed independent verdicts, not an LLM accuracy evaluation.
        return httpx.Response(200, json={'done': True, 'message': {'content': json.dumps({
            'verdicts': [{'id': 0, 'supported': case['supported']}]})}})

    with httpx.Client(base_url='http://127.0.0.1', transport=httpx.MockTransport(handler),
                      trust_env=False, follow_redirects=False) as client:
        _verify_facts(protocol, transcript, Settings(_env_file=None), client, 20000)
    assert len(requests) == 1
    assert protocol.action_items[0].source_check == ('passed' if case['supported'] else 'failed')
    assert protocol.action_items[0].review_status == ('unreviewed' if case['supported'] else 'needs_review')


def test_verifier_does_not_pass_citations_when_complete_context_cannot_fit():
    protocol, transcript = verification_case(VERIFICATION_CASES[0])
    transcript.segments.append(TranscriptSegment(id='large', start=60, text='Обсуждение. ' * 1000))

    def handler(request):
        pytest.fail('Incomplete context must not be sent as a complete semantic check')

    with httpx.Client(base_url='http://127.0.0.1', transport=httpx.MockTransport(handler)) as client:
        _verify_facts(protocol, transcript, Settings(_env_file=None), client, 5000)
    assert protocol.action_items[0].source_check == 'unavailable'
    assert protocol.action_items[0].review_status == 'needs_review'
    assert any('complete chronological transcript' in warning for warning in transcript.warnings)


@pytest.mark.parametrize('response', [
    {'done': False, 'message': {'content': '{"verdicts":[{"id":0,"supported":true}]}'}},
    {'done': True, 'done_reason': 'length', 'message': {'content': '{"verdicts":[{"id":0,"supported":true}]}'}},
    {'done': True, 'message': {'content': '{"verdicts":[]}'}},
    {'done': True, 'message': {'content': '{"verdicts":[{"id":false,"supported":true}]}'}},
    {'done': True, 'message': {'content': '{"verdicts":[{"id":0,"supported":"true"}]}'}},
    {'done': True, 'message': {'content': '{"verdicts":[{"id":0,"supported":true},{"id":0,"supported":false}]}'}},
    {'done': True, 'message': {'content': 'invalid JSON'}},
])
def test_incomplete_or_invalid_verification_never_leaves_a_passed_claim(response):
    protocol, transcript = verification_case(VERIFICATION_CASES[-1])
    with httpx.Client(base_url='http://127.0.0.1', transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=response))) as client:
        with pytest.raises(RuntimeError, match='verification was incomplete or invalid'):
            _verify_facts(protocol, transcript, Settings(_env_file=None), client, 20000)
    assert protocol.action_items[0].source_check == 'unavailable'
    assert protocol.action_items[0].review_status == 'needs_review'


def test_transport_failure_never_leaves_a_passed_claim():
    protocol, transcript = verification_case(VERIFICATION_CASES[-1])

    def handler(request):
        raise httpx.ReadTimeout('synthetic timeout', request=request)

    with httpx.Client(base_url='http://127.0.0.1', transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match='Local Ollama request failed'):
            _verify_facts(protocol, transcript, Settings(_env_file=None), client, 20000)
    assert protocol.action_items[0].source_check == 'unavailable'
    assert protocol.action_items[0].review_status == 'needs_review'


def test_invalid_later_verdict_cannot_partially_approve_a_batch():
    protocol, transcript = verification_case(VERIFICATION_CASES[-1])
    protocol.action_items.append(protocol.action_items[0].model_copy(update={'id': 'action_002'}, deep=True))
    response = {'done': True, 'message': {'content': json.dumps({'verdicts': [
        {'id': 0, 'supported': True}, {'id': 1, 'supported': 'true'}]})}}
    with httpx.Client(base_url='http://127.0.0.1', transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=response))) as client:
        with pytest.raises(RuntimeError, match='verification was incomplete or invalid'):
            _verify_facts(protocol, transcript, Settings(_env_file=None), client, 20000)
    assert all(item.source_check == 'unavailable' and item.review_status == 'needs_review'
               for item in protocol.action_items)


def test_disabled_semantic_verification_cannot_report_citation_only_pass(monkeypatch):
    from meeting_worker.protocol import call_ollama
    from meeting_worker.schemas import JobManifest
    protocol, transcript = verification_case(VERIFICATION_CASES[0])
    original_client = httpx.Client

    def handler(request):
        if request.url.path == '/api/show':
            return httpx.Response(200, json={'model_info': {'fixture': True}, 'details': {'format': 'gguf'}})
        payload = json.loads(request.content)
        assert 'verdicts' not in payload['format']['properties']
        return httpx.Response(200, json={'done': True, 'message': {'content': protocol.model_dump_json()}})

    def client(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return original_client(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr('meeting_worker.protocol.httpx.Client', client)
    result = call_ollama(transcript, JobManifest(meeting_id='synthetic'),
                         Settings(_env_file=None, semantic_verification=False))
    assert result.action_items[0].source_check == 'unavailable'
    assert result.action_items[0].review_status == 'needs_review'
    assert any('verification is disabled' in warning for warning in transcript.warnings)
