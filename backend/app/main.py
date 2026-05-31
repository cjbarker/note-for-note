"""FastAPI application: piano audio -> sheet music.

Pipeline per request:
  upload (any audio format) -> audio.decode_and_wav (ffmpeg fallback)
    -> estimate tempo (librosa) unless supplied
    -> transcription.transcribe_wav (basic-pitch, polyphonic)
    -> notation.midi_to_musicxml (music21: grand staff, tempo, time signature)
    -> JSON {musicXml, midiBase64, stats}

A separate /api/renotate re-runs only the (fast) notation step from the returned
MIDI, so the UI can change tempo/time-signature without re-running inference.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from . import audio, notation, transcription
from .schemas import (
    TIME_SIG_PATTERN,
    HealthResponse,
    RenotateRequest,
    RenotateResponse,
    Stats,
    TranscribeResponse,
)

# Cap uploads to keep memory/CPU bounded (basic-pitch + music21 are not free).
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
# Cap audio duration so a single long clip can't monopolize a threadpool worker.
MAX_AUDIO_SECONDS = 600  # 10 minutes

logger = logging.getLogger("note_for_note")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the model so the first real request isn't slow. Failure is tolerated;
    # /api/health will report model_loaded=false.
    transcription.warm_up()
    yield


app = FastAPI(title="Note-for-Note", version="0.3.0", lifespan=lifespan)

# Allow the Vite dev server (and a configurable extra origin) to call the API.
_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
if os.environ.get("FRONTEND_ORIGIN"):
    _origins.append(os.environ["FRONTEND_ORIGIN"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def _validate_time_signature(time_signature: str) -> None:
    if not re.fullmatch(TIME_SIG_PATTERN, time_signature):
        raise HTTPException(
            status_code=400,
            detail=f'Invalid time signature "{time_signature}"; expected e.g. "4/4".',
        )


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        model_loaded=transcription.is_model_loaded(),
        ffmpeg_available=shutil.which("ffmpeg") is not None,
    )


def _to_stats(stats: notation.TranscriptionStats) -> Stats:
    return Stats(
        note_count=stats.note_count,
        duration_seconds=stats.duration_seconds,
        tempo_bpm=stats.tempo_bpm,
        time_signature=stats.time_signature,
    )


def _run_pipeline(
    data: bytes,
    filename: str | None,
    tempo: float | None,
    time_signature: str,
) -> TranscribeResponse:
    """Blocking transcription pipeline; run inside a threadpool."""
    wav_path, samples, sr = audio.decode_and_wav(data, filename)
    try:
        duration = audio.duration_seconds(samples, sr)
        if duration > MAX_AUDIO_SECONDS:
            raise audio.InputError(f"Audio too long ({duration:.0f}s; max {MAX_AUDIO_SECONDS}s).")
        if tempo is None:
            tempo = audio.estimate_tempo(samples, sr)
        midi = transcription.transcribe_wav(wav_path)
    finally:
        audio._safe_unlink(wav_path)

    music_xml = notation.midi_to_musicxml(midi, tempo=tempo, time_signature=time_signature)
    stats = notation.compute_stats(midi, tempo_bpm=tempo, time_signature=time_signature)
    midi_b64 = base64.b64encode(notation.midi_bytes(midi)).decode("ascii")

    return TranscribeResponse(musicXml=music_xml, midiBase64=midi_b64, stats=_to_stats(stats))


@app.post("/api/transcribe", response_model=TranscribeResponse)
async def transcribe(
    file: UploadFile = File(...),
    tempo: float | None = Form(default=None),
    time_signature: str = Form(default="4/4"),
) -> TranscribeResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
        )
    if tempo is not None and tempo <= 0:
        raise HTTPException(status_code=400, detail="Tempo must be a positive BPM.")
    _validate_time_signature(time_signature)

    try:
        return await run_in_threadpool(_run_pipeline, data, file.filename, tempo, time_signature)
    except audio.InputError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except audio.AudioDecodeError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Transcription failed (filename=%r)", file.filename)
        raise HTTPException(status_code=500, detail="Transcription failed. Please try again or contact support.") from exc


def _run_renotate(req: RenotateRequest) -> RenotateResponse:
    """Fast notation-only re-render from previously transcribed MIDI."""
    midi_data = base64.b64decode(req.midiBase64)
    music_xml, stats, out_midi = notation.renotate_from_midi_bytes(
        midi_data,
        tempo=req.tempo,
        time_signature=req.timeSignature,
        split_point=req.splitPoint,
    )
    midi_b64 = base64.b64encode(out_midi).decode("ascii")
    return RenotateResponse(musicXml=music_xml, midiBase64=midi_b64, stats=_to_stats(stats))


@app.post("/api/renotate", response_model=RenotateResponse)
async def renotate(req: RenotateRequest) -> RenotateResponse:
    if not req.midiBase64:
        raise HTTPException(status_code=400, detail="Missing midiBase64.")
    try:
        return await run_in_threadpool(_run_renotate, req)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Renotation failed")
        raise HTTPException(status_code=400, detail="Renotation failed. Please try again.") from exc
