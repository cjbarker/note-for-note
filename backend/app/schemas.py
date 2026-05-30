"""Pydantic response models for the API."""
from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    ffmpeg_available: bool


class Stats(BaseModel):
    note_count: int
    duration_seconds: float
    tempo_bpm: float


class TranscribeResponse(BaseModel):
    musicXml: str
    midiBase64: str
    stats: Stats
