"""FastAPI application: piano audio -> sheet music.

Pipeline per request:
  upload (any audio format) -> audio.write_normalized_wav (ffmpeg fallback)
    -> transcription.transcribe_wav (basic-pitch, polyphonic)
    -> notation.midi_to_musicxml (music21) -> JSON {musicXml, midiBase64, stats}
"""
from __future__ import annotations

import base64
import os
import shutil

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool

from . import audio, notation, transcription
from .schemas import HealthResponse, Stats, TranscribeResponse

# Cap uploads to keep memory/CPU bounded (basic-pitch + music21 are not free).
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB

app = FastAPI(title="Note-for-Note", version="0.1.0")

# Allow the Vite dev server (and a configurable extra origin) to call the API.
_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
if os.environ.get("FRONTEND_ORIGIN"):
    _origins.append(os.environ["FRONTEND_ORIGIN"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    # Warm the model so the first real request isn't slow. Failure is tolerated;
    # /api/health will report model_loaded=false.
    transcription.warm_up()


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        model_loaded=transcription.is_model_loaded(),
        ffmpeg_available=shutil.which("ffmpeg") is not None,
    )


def _run_pipeline(data: bytes, filename: str | None) -> TranscribeResponse:
    """Blocking transcription pipeline; run inside a threadpool."""
    wav_path = audio.write_normalized_wav(data, filename)
    try:
        midi = transcription.transcribe_wav(wav_path)
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass

    music_xml = notation.midi_to_musicxml(midi)
    stats = notation.compute_stats(midi)
    midi_b64 = base64.b64encode(notation.midi_bytes(midi)).decode("ascii")

    return TranscribeResponse(
        musicXml=music_xml,
        midiBase64=midi_b64,
        stats=Stats(
            note_count=stats.note_count,
            duration_seconds=stats.duration_seconds,
            tempo_bpm=stats.tempo_bpm,
        ),
    )


@app.post("/api/transcribe", response_model=TranscribeResponse)
async def transcribe(file: UploadFile = File(...)) -> TranscribeResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
        )

    try:
        return await run_in_threadpool(_run_pipeline, data, file.filename)
    except audio.AudioDecodeError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}") from exc
