# Note-for-Note — Backend

FastAPI service that transcribes piano audio to sheet music. Dependencies are
managed with [**uv**](https://docs.astral.sh/uv/).

## Pipeline

```
app/audio.py          decode any format → mono 22.05 kHz WAV
                      (soundfile fast path for WAV; librosa/ffmpeg for the rest)
app/transcription.py  basic-pitch (polyphonic) → PrettyMIDI; model cached at startup
app/notation.py       PrettyMIDI → music21 → quantize (16th grid) → MusicXML
app/main.py           FastAPI routes, CORS, upload limits, threadpool offload
app/schemas.py        Pydantic response models
```

## Endpoints

| Method | Path              | Description |
|--------|-------------------|-------------|
| GET    | `/api/health`     | `{status, model_loaded, ffmpeg_available}` |
| POST   | `/api/transcribe` | multipart `file` (any audio format) + optional `tempo`, `time_signature` → `{musicXml, midiBase64, stats}` |
| POST   | `/api/renotate`   | JSON `{midiBase64, tempo, timeSignature, splitPoint?}` → `{musicXml, stats}` (fast; re-runs only music21, not the model) |

`stats` = `{note_count, duration_seconds, tempo_bpm, time_signature}`. Uploads are
capped at 25 MB and 10 minutes of audio; `tempo` must be positive and
`time_signature` must match `N/N` (else HTTP 400/413). Transcription runs in a
threadpool so the event loop stays responsive. Notation renders a treble+bass
**grand staff** (split at middle C); tempo (auto-estimated via librosa,
user-overridable) drives note durations.

## Run

Prerequisites: [uv](https://docs.astral.sh/uv/getting-started/installation/) and
ffmpeg (`sudo apt-get install -y ffmpeg`, for non-WAV decoding).

```bash
uv sync                                   # create .venv + install from uv.lock
uv run uvicorn app.main:app --reload      # serves http://localhost:8000
```

`uv sync` reads `pyproject.toml` / `uv.lock` and provisions an isolated `.venv`
automatically — no manual virtualenv activation needed.

### Notes on dependencies
- **`setuptools<81`** is a runtime dependency: `resampy` (pulled in by basic-pitch)
  imports `pkg_resources`, which setuptools removed in v81.
- On Linux/Python 3.11, basic-pitch installs the **TensorFlow** runtime. The first
  request (or app startup) loads the model — expect a few seconds of warm-up.

## Test
```bash
uv run pytest          # full decode → transcribe → notation smoke test
```
The suite synthesizes known tones in-memory and runs the whole pipeline (it loads
the model, so the first run is slow).

## Tuning transcription
Edit `TranscriptionParams` in `app/transcription.py`:
`onset_threshold`, `frame_threshold`, `minimum_note_length_ms`, and the piano
frequency bounds. Lower thresholds detect more (and more spurious) notes.

## Managing dependencies
```bash
uv add <package>          # add a runtime dependency (updates pyproject.toml + uv.lock)
uv add --dev <package>    # add a dev dependency
uv lock --upgrade         # refresh the lockfile
```
