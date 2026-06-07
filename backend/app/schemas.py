"""Pydantic request/response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Shared time-signature pattern (e.g. "4/4", "6/8").
TIME_SIG_PATTERN = r"^\d{1,2}/\d{1,2}$"


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    ffmpeg_available: bool


class Stats(BaseModel):
    note_count: int
    duration_seconds: float
    tempo_bpm: float
    time_signature: str = "4/4"
    key_signature: str = ""


class TranscribeResponse(BaseModel):
    musicXml: str
    midiBase64: str
    stats: Stats


class RenotateRequest(BaseModel):
    midiBase64: str
    tempo: float | None = Field(default=None, gt=0)
    timeSignature: str = Field(default="4/4", pattern=TIME_SIG_PATTERN)
    splitPoint: int = Field(default=60, ge=0, le=127, title="Split point (MIDI note, 0-127)")


class RenotateResponse(BaseModel):
    musicXml: str
    midiBase64: str
    stats: Stats
