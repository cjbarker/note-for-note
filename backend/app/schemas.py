"""Pydantic request/response models for the API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    ffmpeg_available: bool


class Stats(BaseModel):
    note_count: int
    duration_seconds: float
    tempo_bpm: float
    time_signature: str = "4/4"


class TranscribeResponse(BaseModel):
    musicXml: str
    midiBase64: str
    stats: Stats


class RenotateRequest(BaseModel):
    midiBase64: str
    tempo: float | None = Field(default=None, gt=0)
    timeSignature: str = "4/4"
    splitPoint: int = Field(default=60, ge=0, le=127)


class RenotateResponse(BaseModel):
    musicXml: str
    stats: Stats
