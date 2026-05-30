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
import os
import shutil

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool

from . import audio, notation, transcription
from .schemas import (
    HealthResponse,
    RenotateRequest,
    RenotateResponse,
    Stats,
    TranscribeResponse,
)

# Cap uploads to keep memory/CPU bounded (basic-pitch + music21 are not free).
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB

app = FastAPI(title="Note-for-Note", version="0.2.0")

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
        if tempo is None:
            tempo = audio.estimate_tempo(samples, sr)
        midi = transcription.transcribe_wav(wav_path)
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass

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

    try:
        return await run_in_threadpool(_run_pipeline, data, file.filename, tempo, time_signature)
    except audio.AudioDecodeError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}") from exc


def _run_renotate(req: RenotateRequest) -> RenotateResponse:
    """Fast notation-only re-render from previously transcribed MIDI."""
    midi_data = base64.b64decode(req.midiBase64)
    music_xml, stats = notation.renotate_from_midi_bytes(
        midi_data,
        tempo=req.tempo,
        time_signature=req.timeSignature,
        split_point=req.splitPoint,
    )
    return RenotateResponse(musicXml=music_xml, stats=_to_stats(stats))


@app.post("/api/renotate", response_model=RenotateResponse)
async def renotate(req: RenotateRequest) -> RenotateResponse:
    if not req.midiBase64:
        raise HTTPException(status_code=400, detail="Missing midiBase64.")
    try:
        return await run_in_threadpool(_run_renotate, req)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Renotation failed: {exc}") from exc
