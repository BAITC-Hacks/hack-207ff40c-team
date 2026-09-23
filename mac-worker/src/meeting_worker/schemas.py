from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class JobStage(StrEnum):
    QUEUED = "queued"
    PREPROCESSING = "preprocessing"
    TRANSCRIBING = "transcribing"
    DIARIZING = "diarizing"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Evidence(BaseModel):
    segment_ids: list[str] = Field(default_factory=list)
    quote: str | None = None
    speaker: str | None = None
    speaker_name: str | None = None
    start: float | None = None
    end: float | None = None


class ProtocolItem(BaseModel):
    id: str
    text: str
    evidence: Evidence = Field(default_factory=Evidence)
    source_check: Literal["passed", "failed", "unavailable"] = "unavailable"
    audio_warning: bool = False
    review_status: Literal[
        "unreviewed", "needs_review", "human_confirmed", "rejected"
    ] = "unreviewed"


class Topic(ProtocolItem):
    title: str


class ActionItem(BaseModel):
    id: str
    task: str
    assignee: str | None = None
    deadline_text: str | None = None
    deadline_date: date | None = None
    priority: Literal["low", "medium", "high", "urgent", "not_specified"] = (
        "not_specified"
    )
    evidence: Evidence = Field(default_factory=Evidence)
    source_check: Literal["passed", "failed", "unavailable"] = "unavailable"
    audio_warning: bool = False
    review_status: Literal[
        "unreviewed", "needs_review", "human_confirmed", "rejected"
    ] = "unreviewed"

    @field_validator("assignee", "deadline_text", mode="before")
    @classmethod
    def normalize_unknown(cls, value):
        if isinstance(value, str) and value.strip().lower() in {"null", "none", "unknown", "not specified", "not_specified", "n/a"}:
            return None
        return value


class MeetingMetadata(BaseModel):
    meeting_id: str | None = None
    title: str = "Meeting"
    meeting_date: date | None = None
    timezone: str | None = None
    language: str = "auto"
    report_language: str | None = None
    duration_seconds: float | None = None
    participants: list[str] = Field(default_factory=list)


class SummarySource(BaseModel):
    """Provenance for the string at the same index in executive_summary."""
    item_id: str
    evidence: Evidence
    audio_warning: bool = False


class MeetingOverview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    language: Literal['en', 'ru', 'kk'] = 'en'
    summary: list[ProtocolItem] = Field(default_factory=list, max_length=5)
    topics: list[Topic] = Field(default_factory=list, max_length=8)


class MeetingProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    metadata: MeetingMetadata
    executive_summary: list[str] = Field(default_factory=list, max_length=5)
    executive_summary_sources: list[SummarySource] = Field(default_factory=list, max_length=5)
    topics: list[Topic] = Field(default_factory=list)
    decisions: list[ProtocolItem] = Field(default_factory=list)
    open_questions: list[ProtocolItem] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    risks: list[ProtocolItem] = Field(default_factory=list)


class TranscriptToken(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    text: str
    probability: float = Field(ge=0, le=1)


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    id: str
    start: float | None = None
    end: float | None = None
    text: str = Field(max_length=1000000)
    speaker: str | None = None
    speaker_name: str | None = None
    language: str | None = None
    tokens: list[TranscriptToken] = Field(default_factory=list)
    needs_review: bool = False

    @model_validator(mode="after")
    def valid_interval(self):
        if self.start is not None and self.start < 0:
            raise ValueError("Negative transcript start")
        if self.end is not None and (self.end < 0 or (self.start is not None and self.end < self.start)):
            raise ValueError("Invalid transcript interval")
        return self


class Transcript(BaseModel):
    schema_version: str = "1.0"
    language: str = "auto"
    model: str
    raw_text: str
    segments: list[TranscriptSegment]
    warnings: list[str] = Field(default_factory=list)


class JobManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.0"
    meeting_id: str = Field(min_length=1, max_length=200)
    title: str = Field(default="Meeting", min_length=1, max_length=200)
    language_mode: Literal["kk_ru", "kk", "ru", "en", "auto"] = "auto"
    vocabulary: str = Field(default="", max_length=400)
    output_language: Literal["same", "kk", "ru", "en"] = "same"
    meeting_date: date | None = None
    timezone: str | None = None
    diarization: bool = False
    min_speakers: int | None = Field(default=None, ge=1, le=20)
    max_speakers: int | None = Field(default=None, ge=1, le=20)

    @model_validator(mode="after")
    def speaker_bounds(self):
        if self.min_speakers is not None and self.max_speakers is not None and self.min_speakers > self.max_speakers:
            raise ValueError("Minimum speakers cannot exceed maximum")
        return self


class JobRecord(BaseModel):
    id: str
    meeting_id: str
    stage: JobStage
    progress_current: int = 0
    progress_total: int = 0
    source_kind: Literal["audio", "text"]
    source_path: str
    source_sha256: str
    manifest: JobManifest
    created_at: datetime
    updated_at: datetime
    error_code: str | None = None
    error_message: str | None = None
    result_path: str | None = None


class JobResult(BaseModel):
    job: JobRecord
    transcript: Transcript
    protocol: MeetingProtocol
    exports: dict[str, str]
    review_revision: int = 0
    speaker_names: dict[str, str] = Field(default_factory=dict)
    review_history: list[dict] = Field(default_factory=list)


class ActionReview(BaseModel):
    """Only a person at the authenticated review endpoint can submit this contract."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=200)
    task: str = Field(min_length=1, max_length=4000)
    assignee: str | None = Field(default=None, max_length=200)
    deadline_text: str | None = Field(default=None, max_length=500)
    deadline_date: date | None = None
    priority: Literal["low", "medium", "high", "urgent", "not_specified"] = "not_specified"
    review_status: Literal["human_confirmed", "needs_review", "rejected"]


class FindingReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=200)
    review_status: Literal["human_confirmed", "needs_review", "rejected"]


class NewActionReview(BaseModel):
    """A human-added commitment must point to existing, immutable source text."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    task: str = Field(min_length=1, max_length=4000)
    assignee: str | None = Field(default=None, max_length=200)
    deadline_text: str | None = Field(default=None, max_length=500)
    deadline_date: date | None = None
    priority: Literal["low", "medium", "high", "urgent", "not_specified"] = "not_specified"
    segment_ids: list[str] = Field(min_length=1, max_length=200)
    review_status: Literal["human_confirmed", "needs_review"]

    @field_validator("segment_ids")
    @classmethod
    def distinct_source_passages(cls, ids):
        if any(not identity or len(identity) > 200 for identity in ids) or len(set(ids)) != len(ids):
            raise ValueError("Select distinct nonempty transcript passage IDs")
        return ids


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    expected_revision: int = Field(ge=0)
    reviewer: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=2000)
    speaker_names: dict[str, str] = Field(default_factory=dict, max_length=50)
    actions: list[ActionReview] = Field(default_factory=list, max_length=200)
    findings: list[FindingReview] = Field(default_factory=list, max_length=200)
    new_actions: list[NewActionReview] = Field(default_factory=list, max_length=50)

    @field_validator("speaker_names")
    @classmethod
    def named_speakers(cls, names):
        if any(not key.strip() or len(key) > 200 or len(name.strip()) > 200 for key, name in names.items()):
            raise ValueError("Speaker IDs and names must be at most 200 characters")
        return {key: name.strip() for key, name in names.items()}

    @model_validator(mode="after")
    def distinct_changes(self):
        ids = [item.id for item in self.actions] + [item.id for item in self.findings]
        if len(ids) != len(set(ids)):
            raise ValueError("Each finding can be reviewed only once per request")
        if not (self.speaker_names or self.actions or self.findings or self.new_actions):
            raise ValueError("Provide a speaker mapping or finding review")
        return self
