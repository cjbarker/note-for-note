# Note-for-Note — Backend

FastAPI service that transcribes piano audio to sheet music.

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
| POST   | `/api/transcribe` | multipart `file` (any audio format) → `{musicXml, midiBase64, stats}` |

`stats` = `{note_count, duration_seconds, tempo_bpm}`. Uploads are capped at 25 MB
and transcription runs in a threadpool so the event loop stays responsive.

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip wheel "setuptools<81"
pip install -r requirements.txt
sudo apt-get install -y ffmpeg          # for non-WAV decoding
uvicorn app.main:app --reload
```

### Notes on dependencies
- **`setuptools<81`**: `resampy` (pulled in by basic-pitch) imports `pkg_resources`,
  which setuptools removed in v81. The pin also stays new enough to build
  `pretty_midi`'s legacy `setup.py`.
- On Linux/Python 3.11, basic-pitch installs the **TensorFlow** runtime. The first
  request (or app startup) loads the model — expect a few seconds of warm-up.

## Test
```bash
pytest          # full decode → transcribe → notation smoke test
```

## Tuning transcription
Edit `TranscriptionParams` in `app/transcription.py`:
`onset_threshold`, `frame_threshold`, `minimum_note_length_ms`, and the piano
frequency bounds. Lower thresholds detect more (and more spurious) notes.
