from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.0"
    meeting_id: str = Field(min_length=1, max_length=200)
    title: str = Field(default="Meeting", min_length=1, max_length=200)
    language_mode: Literal["kk_ru", "kk", "ru", "en", "auto"] = "auto"
    vocabulary: str = Field(default="", max_length=400)
    output_language: Literal["same", "kk", "ru", "en"] = "same"
    meeting_date: Optional[date] = None
    timezone: Optional[str] = Field(default=None, max_length=100)
    diarization: bool = False
    min_speakers: Optional[int] = Field(default=None, ge=1, le=20)
    max_speakers: Optional[int] = Field(default=None, ge=1, le=20)

    @model_validator(mode='after')
    def speaker_bounds(self):
        if self.min_speakers is not None and self.max_speakers is not None and self.min_speakers > self.max_speakers:
            raise ValueError('min_speakers must be <= max_speakers')
        return self


class RecordingStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="Board recording", min_length=1, max_length=200)
    language_mode: Literal["kk_ru", "kk", "ru", "en", "auto"] = "auto"
    vocabulary: str = Field(default="", max_length=400)
    output_language: Literal["same", "kk", "ru", "en"] = "same"
    diarization: bool = False
