"""Secretary review contract using explicit synthetic model output, not an ASR test."""
import json
from datetime import date
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile
from pypdf import PdfReader

import pytest
from fastapi.testclient import TestClient

from meeting_worker import review
from meeting_worker.bundle import write_exports
from meeting_worker.config import Settings
from meeting_worker.main import create_app
from meeting_worker.schemas import (
    ActionItem, Evidence, JobResult, JobStage, MeetingMetadata,
    MeetingProtocol, Transcript, TranscriptSegment,
)

TOKEN = "review-contract-fixture-token"
AUTH = {"Authorization": "Bearer " + TOKEN}


def seed(client, directory, *, empty=False):
    response = client.post("/v1/jobs", headers=AUTH, data={
        "manifest_json": json.dumps({"meeting_id": "synthetic-review", "output_language": "ru"}),
        "transcript": "Айдана: Мен дайындаймын. Уточнение: Тимур подготовит отчёт к понедельнику.",
    })
    identity = response.json()["id"]
    job = client.app.state.store.get(identity)
    source = Transcript(model="synthetic-supplied-output", language="kk_ru", raw_text=Path(job.source_path).read_text(),
        segments=[TranscriptSegment(id="s1", start=0, end=5, speaker="SPEAKER_00", text="Мен дайындаймын."),
                  TranscriptSegment(id="s2", start=5, end=12, speaker="SPEAKER_01", text="Уточнение: Тимур подготовит отчёт к понедельнику.")])
    protocol = MeetingProtocol(metadata=MeetingMetadata(title="Синтетическое совещание", report_language="ru"),
        action_items=[ActionItem(id="a1", task="Подготовить отчёт", assignee="Айдана", deadline_text="в пятницу",
            source_check="passed", evidence=Evidence(segment_ids=["s2"], speaker="SPEAKER_01", start=5, end=12,
                quote=source.segments[1].text))])
    if empty:
        protocol.action_items = []
    exports = write_exports(directory / "exports" / identity, protocol, source)
    path = directory / "results" / (identity + ".json")
    job = client.app.state.store.update(identity, JobStage.COMPLETED, result_path=str(path))
    result = JobResult(job=job, transcript=source, protocol=protocol, exports=exports)
    path.write_text(result.model_dump_json())
    return identity, result


def change(**overrides):
    payload = {"request_id": str(uuid4()), "expected_revision": 0, "reviewer": "Секретарь",
        "note": "Проверено по исходной записи",
        "speaker_names": {"SPEAKER_00": "Айдана", "SPEAKER_01": "Бекзат"},
        "actions": [{"id": "a1", "task": "Подготовить отчёт", "assignee": "Тимур",
                     "deadline_text": "к понедельнику", "deadline_date": "2026-09-28",
                     "priority": "high", "review_status": "human_confirmed"}]}
    payload.update(overrides)
    return payload


def endpoint(identity):
    return "/v1/jobs/" + identity


# Fixed synthetic missed-action case, specified before implementation. The source
# contains a commitment that the supplied empty extraction deliberately omitted.
MISSED_ACTION = {
    "task": "Подготовить отчёт", "assignee": "Тимур", "deadline_text": "к понедельнику",
    "deadline_date": "2026-09-28", "priority": "not_specified", "segment_ids": ["s2"],
    "review_status": "human_confirmed",
}


def test_missed_action_from_empty_report_keeps_source_and_survives_retry(tmp_path):
    config = Settings(_env_file=None, data_dir=tmp_path, api_token=TOKEN)
    with TestClient(create_app(config, start_worker=False)) as client:
        identity, original = seed(client, tmp_path, empty=True)
        payload = change(request_id="22222222-2222-4222-8222-222222222222", actions=[], new_actions=[MISSED_ACTION])
        response = client.post(endpoint(identity) + "/review", headers=AUTH, json=payload)
        assert response.status_code == 200, response.text
        result = JobResult.model_validate(response.json())
        assert len(result.protocol.action_items) == 1
        action = result.protocol.action_items[0]
        assert action.task == MISSED_ACTION["task"] and action.assignee == "Тимур"
        assert action.source_check == "unavailable" and action.review_status == "human_confirmed"
        assert action.evidence.segment_ids == ["s2"]
        assert action.evidence.quote == original.transcript.segments[1].text
        assert action.evidence.start == 5 and action.evidence.end == 12
        assert action.evidence.speaker == "SPEAKER_01" and action.evidence.speaker_name == "Бекзат"
        assert result.transcript.raw_text == original.transcript.raw_text
        audit = result.review_history[0]["changes"][-1]
        assert audit["before"] is None and audit["after"]["id"] == action.id
        assert "Тимур" in " ".join(result.protocol.executive_summary)
        assert "DUE;VALUE=DATE:20260928" in Path(result.exports["ics"]).read_text()
        pdf = " ".join(page.extract_text() for page in PdfReader(result.exports["pdf"]).pages)
        assert "Тимур" in pdf and "2026-09-28" in pdf
        with ZipFile(result.exports["docx"]) as archive:
            assert "Тимур" in archive.read("word/document.xml").decode()
        repeated = client.post(endpoint(identity) + "/review", headers=AUTH, json=payload)
        assert repeated.status_code == 200
        assert repeated.json()["review_revision"] == 1
        assert repeated.json()["protocol"]["action_items"][0]["id"] == action.id
        assert len(repeated.json()["protocol"]["action_items"]) == 1
        assert len(repeated.json()["review_history"]) == 1
        stale = dict(payload, request_id=str(uuid4()))
        assert client.post(endpoint(identity) + "/review", headers=AUTH, json=stale).status_code == 409


@pytest.mark.parametrize("alter", [
    {"segment_ids": []}, {"segment_ids": ["unknown"]}, {"segment_ids": ["s1", "s1"]},
    {"evidence": {"quote": "Invented commitment"}}, {"review_status": "unreviewed"},
    {"task": "   "},
])
def test_invalid_missed_action_rejects_all_changes_atomically(tmp_path, alter):
    config = Settings(_env_file=None, data_dir=tmp_path, api_token=TOKEN)
    with TestClient(create_app(config, start_worker=False)) as client:
        identity, original = seed(client, tmp_path)
        payload = change(new_actions=[dict(MISSED_ACTION, **alter)])
        response = client.post(endpoint(identity) + "/review", headers=AUTH, json=payload)
        assert response.status_code == 422, response.text
        unchanged = client.get(endpoint(identity) + "/result", headers=AUTH).json()
        assert unchanged["review_revision"] == 0 and unchanged["speaker_names"] == {}
        assert unchanged["protocol"]["action_items"][0]["assignee"] == "Айдана"
        assert len(unchanged["protocol"]["action_items"]) == 1
        assert unchanged["exports"] == original.exports


def test_uncertain_missed_action_keeps_context_without_inventing_owner(tmp_path):
    from meeting_worker.schemas import ReviewRequest
    config = Settings(_env_file=None, data_dir=tmp_path, api_token=TOKEN)
    with TestClient(create_app(config, start_worker=False)) as client:
        _, original = seed(client, tmp_path, empty=True)
    original.transcript.segments[0].needs_review = True
    payload = change(actions=[], new_actions=[dict(MISSED_ACTION, assignee=None, deadline_date=None,
        deadline_text=None, segment_ids=["s2", "s1"], review_status="needs_review")])
    result = review.apply_review(original, ReviewRequest.model_validate(payload))
    action = result.protocol.action_items[0]
    assert action.assignee is None and action.deadline_text is None and action.deadline_date is None
    assert action.audio_warning and action.review_status == "needs_review"
    assert action.evidence.speaker is None and action.evidence.speaker_name is None
    assert action.evidence.segment_ids == ["s1", "s2"]
    assert action.evidence.quote == " ".join(segment.text for segment in original.transcript.segments)
    assert result.protocol.executive_summary == []


def test_review_persists_identity_actions_audit_and_all_exports_across_restart(tmp_path):
    config = Settings(_env_file=None, data_dir=tmp_path, api_token=TOKEN)
    with TestClient(create_app(config, start_worker=False)) as client:
        identity, original = seed(client, tmp_path)
        old_bytes = Path(original.job.result_path).read_bytes()
        payload = change()
        saved = client.post(endpoint(identity) + "/review", headers=AUTH, json=payload)
        assert saved.status_code == 200, saved.text
        result = JobResult.model_validate(saved.json())
        assert result.review_revision == 1
        assert result.transcript.raw_text == original.transcript.raw_text
        assert result.transcript.segments[0].speaker == "SPEAKER_00"
        assert result.transcript.segments[0].speaker_name == "Айдана"
        action = result.protocol.action_items[0]
        assert action.assignee == "Тимур" and action.deadline_date == date(2026, 9, 28)
        assert action.source_check == "unavailable" and action.review_status == "human_confirmed"
        assert action.evidence.quote == original.protocol.action_items[0].evidence.quote
        assert action.evidence.speaker_name == "Бекзат"  # Speaker is not automatically the owner.
        assert "Тимур" in " ".join(result.protocol.executive_summary)
        assert "Айдана" not in " ".join(result.protocol.executive_summary)
        assert result.review_history[0]["changes"][-1]["before"]["assignee"] == "Айдана"
        assert Path(original.job.result_path).read_bytes() == old_bytes
        assert set(result.exports) == {"json", "csv", "pdf", "docx", "ics"}
        for kind in result.exports:
            response = client.get(endpoint(identity) + "/export/" + kind, headers=AUTH, params={"revision": 1})
            assert response.status_code == 200 and response.content
        with ZipFile(result.exports["docx"]) as archive:
            assert "Тимур" in archive.read("word/document.xml").decode()
        assert "DUE;VALUE=DATE:20260928" in Path(result.exports["ics"]).read_text()
        pdf = " ".join(page.extract_text() for page in PdfReader(result.exports["pdf"]).pages)
        assert "2026-09-28" in pdf and "к понедельнику" in pdf
        exported_json = json.loads(Path(result.exports["json"]).read_text())
        assert exported_json["protocol"]["action_items"][0]["assignee"] == "Тимур"
        assert client.get(endpoint(identity) + "/export/pdf", headers=AUTH, params={"revision": 0}).status_code == 409
        repeat = client.post(endpoint(identity) + "/review", headers=AUTH, json=payload)
        assert repeat.json()["review_revision"] == 1 and len(repeat.json()["review_history"]) == 1
        stale = client.post(endpoint(identity) + "/review", headers=AUTH, json=change())
        assert stale.status_code == 409
        conflicting_id = dict(payload, note="Different request")
        assert client.post(endpoint(identity) + "/review", headers=AUTH, json=conflicting_id).status_code == 409
    with TestClient(create_app(config, start_worker=False)) as client:
        restored = client.get(endpoint(identity) + "/result", headers=AUTH).json()
        assert restored["review_revision"] == 1
        assert restored["review_history"][0]["reviewer"] == "Секретарь"


@pytest.mark.parametrize("alter", [
    {"speaker_names": {"NOT_A_SPEAKER": "Unknown"}},
    {"actions": [{"id": "unknown", "task": "Task", "review_status": "human_confirmed"}]},
    {"actions": [{"id": "a1", "task": "   ", "review_status": "human_confirmed"}]},
    {"actions": [{"id": "a1", "task": "Task", "review_status": "human_confirmed", "source_check": "passed"}]},
    {"findings": [{"id": "a1", "review_status": "human_confirmed"}]},
])
def test_invalid_review_has_no_partial_effect(tmp_path, alter):
    config = Settings(_env_file=None, data_dir=tmp_path, api_token=TOKEN)
    with TestClient(create_app(config, start_worker=False)) as client:
        identity, original = seed(client, tmp_path)
        payload = change(**alter)
        assert client.post(endpoint(identity) + "/review", headers=AUTH, json=payload).status_code == 422
        result = client.get(endpoint(identity) + "/result", headers=AUTH).json()
        assert result["review_revision"] == 0
        assert result["speaker_names"] == {}
        assert result["protocol"]["action_items"][0]["assignee"] == "Айдана"


def test_rejected_actions_leave_summary_and_calendar_but_remain_in_reports(tmp_path):
    config = Settings(_env_file=None, data_dir=tmp_path, api_token=TOKEN)
    with TestClient(create_app(config, start_worker=False)) as client:
        identity, _ = seed(client, tmp_path)
        payload = change()
        payload["actions"][0]["review_status"] = "rejected"
        result = client.post(endpoint(identity) + "/review", headers=AUTH, json=payload).json()
        assert result["protocol"]["executive_summary"] == []
        assert "BEGIN:VTODO" not in Path(result["exports"]["ics"]).read_text()
        assert result["protocol"]["action_items"][0]["review_status"] == "rejected"


def test_export_failure_preserves_current_report_and_auth_precedes_parsing(tmp_path, monkeypatch):
    config = Settings(_env_file=None, data_dir=tmp_path, api_token=TOKEN)
    with TestClient(create_app(config, start_worker=False)) as client:
        identity, original = seed(client, tmp_path)
        url = endpoint(identity) + "/review"
        assert client.post(url, content="malformed").status_code == 401
        def unavailable(*args, **kwargs):
            raise OSError("Synthetic filesystem failure")
        monkeypatch.setattr(review, "write_exports", unavailable)
        assert client.post(url, headers=AUTH, json=change()).status_code == 503
        result = client.get(endpoint(identity) + "/result", headers=AUTH).json()
        assert result["review_revision"] == 0
        assert result["exports"] == original.exports
        assert client.get(endpoint(identity) + "/export/pdf", headers=AUTH).status_code == 200
        assert not list((tmp_path / "exports" / identity).glob("review-*"))


def test_speaker_only_review_preserves_resolved_report_language(tmp_path):
    config = Settings(_env_file=None, data_dir=tmp_path, api_token=TOKEN)
    with TestClient(create_app(config, start_worker=False)) as client:
        _, original = seed(client, tmp_path)
        original.job.manifest.output_language = "same"
        from meeting_worker.schemas import ReviewRequest
        updated = review.apply_review(original, ReviewRequest.model_validate(change(actions=[])))
        assert updated.protocol.executive_summary
        assert "ответствен" in " ".join(updated.protocol.executive_summary) or "отвечает" in " ".join(updated.protocol.executive_summary)
