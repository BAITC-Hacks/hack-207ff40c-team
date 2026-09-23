"""Revisioned human review. Original audio, transcript text and citations are immutable."""
from __future__ import annotations

import hashlib
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from .bundle import sync_directory, write_exports
from .protocol import derive_summary
from .schemas import ActionItem, Evidence, JobResult, JobStage, ReviewRequest


class ReviewError(Exception):
    def __init__(self, message, status=409):
        self.status = status
        super().__init__(message)


def findings(protocol):
    return [*protocol.topics, *protocol.decisions, *protocol.open_questions, *protocol.risks, *protocol.action_items]


def apply_review(original: JobResult, request: ReviewRequest) -> JobResult:
    """Pure validation/change step; transport retries cannot duplicate a review."""
    # Preserve the fingerprint of requests saved before new_actions existed.
    digest = hashlib.sha256(request.model_dump_json(exclude={"new_actions"} if not request.new_actions else set()).encode()).hexdigest()
    for event in original.review_history:
        if event["request_id"] == str(request.request_id):
            if event["request_sha256"] != digest:
                raise ReviewError("This review request ID belongs to different changes")
            return original
    if request.expected_revision != original.review_revision:
        raise ReviewError("The report changed. Reload it before saving your review")
    result = original.model_copy(deep=True)
    all_items = findings(result.protocol)
    ids = [item.id for item in all_items]
    if len(set(ids)) != len(ids):
        raise ReviewError("The report contains duplicate finding IDs; review cannot safely identify an item", 422)
    known_speakers = {segment.speaker for segment in result.transcript.segments if segment.speaker}
    if set(request.speaker_names) - known_speakers:
        raise ReviewError("A speaker mapping refers to an unknown speaker", 422)
    changes = []
    for speaker, name in request.speaker_names.items():
        before = result.speaker_names.get(speaker)
        if name:
            result.speaker_names[speaker] = name
        else:
            result.speaker_names.pop(speaker, None)
        changes.append({"kind": "speaker", "id": speaker, "before": before, "after": name or None})
    for segment in result.transcript.segments:
        segment.speaker_name = result.speaker_names.get(segment.speaker)
    result.protocol.metadata.participants = list(dict.fromkeys(result.speaker_names.values()))
    action_by_id = {item.id: item for item in result.protocol.action_items}
    finding_by_id = {item.id: item for item in all_items if item.id not in action_by_id}
    for review in request.actions:
        item = action_by_id.get(review.id)
        if item is None:
            raise ReviewError("An action review refers to an unknown action", 422)
        before = item.model_dump(mode="json")
        updates = review.model_dump(exclude={"id"})
        updates["assignee"] = updates["assignee"] or None
        updates["deadline_text"] = updates["deadline_text"] or None
        if any(getattr(item, key) != value for key, value in updates.items() if key != "review_status"):
            # A previous model check is about the old wording, never a human edit.
            item.source_check = "unavailable"
        for key, value in updates.items():
            setattr(item, key, value)
        changes.append({"kind": "action", "id": item.id, "before": before, "after": item.model_dump(mode="json")})
    for review in request.findings:
        item = finding_by_id.get(review.id)
        if item is None:
            raise ReviewError("A finding review refers to an unknown non-action finding", 422)
        before = item.review_status
        item.review_status = review.review_status
        changes.append({"kind": "finding", "id": item.id, "before": before, "after": item.review_status})
    if request.new_actions:
        source_by_id = {segment.id: segment for segment in result.transcript.segments}
        if len(source_by_id) != len(result.transcript.segments):
            raise ReviewError("Transcript passage IDs are ambiguous; a new action cannot be linked safely", 422)
        for index, addition in enumerate(request.new_actions, 1):
            if set(addition.segment_ids) - source_by_id.keys():
                raise ReviewError("A new action refers to an unknown transcript passage", 422)
            selected = set(addition.segment_ids)
            passages = [segment for segment in result.transcript.segments if segment.id in selected]
            if any(not segment.text.strip() for segment in passages):
                raise ReviewError("Select transcript passages containing source text", 422)
            speaker = passages[0].speaker if all(segment.speaker == passages[0].speaker for segment in passages) else None
            starts = [segment.start for segment in passages if segment.start is not None]
            ends = [segment.end for segment in passages if segment.end is not None]
            identity = f"action_manual_{request.request_id.hex}_{index:03d}"
            if identity in ids:
                raise ReviewError("A generated action ID already belongs to this report", 422)
            item = ActionItem(
                id=identity, task=addition.task, assignee=addition.assignee or None,
                deadline_text=addition.deadline_text or None, deadline_date=addition.deadline_date,
                priority=addition.priority, review_status=addition.review_status, source_check="unavailable",
                audio_warning=any(segment.needs_review for segment in passages),
                evidence=Evidence(segment_ids=[segment.id for segment in passages],
                    quote=" ".join(segment.text for segment in passages), speaker=speaker,
                    speaker_name=result.speaker_names.get(speaker),
                    start=min(starts) if starts else None, end=max(ends) if ends else None))
            result.protocol.action_items.append(item)
            all_items.append(item)
            ids.append(identity)
            changes.append({"kind": "action", "id": identity, "before": None, "after": item.model_dump(mode="json")})
    for item in all_items:
        item.evidence.speaker_name = result.speaker_names.get(item.evidence.speaker)
    # Derive the summary again so rejected/superseded wording cannot survive in it.
    # The projection treats an explicit human confirmation as review evidence;
    # source_check on the saved items continues to describe automated verification.
    summary_view = result.protocol.model_copy(deep=True)
    for item in findings(summary_view):
        if item.review_status == "human_confirmed":
            item.source_check = "passed"
    derive_summary(summary_view, result.job.manifest, result.protocol.metadata.report_language or result.transcript.language)
    result.protocol.executive_summary = summary_view.executive_summary
    result.protocol.executive_summary_sources = summary_view.executive_summary_sources
    result.review_revision += 1
    result.review_history.append({
        "revision": result.review_revision, "request_id": str(request.request_id),
        "request_sha256": digest, "reviewer": request.reviewer,
        "reviewed_at": datetime.now(UTC).isoformat(), "note": request.note,
        "changes": changes,
    })
    return result


def save_review(config, store, job_id: str, request: ReviewRequest) -> JobResult:
    """Caller serializes reviews; publish a new immutable bundle with one DB update."""
    job = store.get(job_id)
    if job is None:
        raise ReviewError("Job not found", 404)
    if job.stage != JobStage.COMPLETED or not job.result_path:
        raise ReviewError("Only a completed report can be reviewed")
    original = JobResult.model_validate_json(Path(job.result_path).read_text(encoding="utf-8"))
    result = apply_review(original, request)
    if result is original:
        return original
    suffix = f"review-{result.review_revision}-{request.request_id}"
    directory = config.data_dir / "exports" / job.id / suffix
    path = config.data_dir / "results" / f"{job.id}.{suffix}.json"
    temporary = path.with_suffix(".partial")
    published = False
    try:
        result.exports = write_exports(directory, result.protocol, result.transcript, config.pdf_font or None)
        result.job = job.model_copy(update={"result_path": str(path), "updated_at": datetime.now(UTC)})
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(result.model_dump_json(indent=2))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
        sync_directory(path.parent)
        # Readers still see the previous complete bundle until this atomic commit.
        store.update(job.id, JobStage.COMPLETED, allowed={JobStage.COMPLETED}, result_path=str(path))
        published = True
        return result
    finally:
        temporary.unlink(missing_ok=True)
        if not published:
            path.unlink(missing_ok=True)
            shutil.rmtree(directory, ignore_errors=True)
