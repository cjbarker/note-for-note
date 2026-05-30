# Note-for-Note 🎹 → 🎼

Play piano, get sheet music. Note-for-Note takes audio of a piano performance —
**uploaded as a file or recorded live in the browser** — and performs
**Automatic Music Transcription (AMT)**, converting the sound wave note-for-note
into rendered, downloadable sheet music. You can also **play the transcription
back in the browser** (sampled piano) to QA the result by ear.

Piano is *polyphonic* (chords / many notes at once), so this uses
[Spotify's **basic-pitch**](https://github.com/spotify/basic-pitch) neural model
rather than simple pitch detection. The resulting MIDI is quantized and converted
to **MusicXML** with [music21](https://www.music21.org/), then engraved in the
browser with [OpenSheetMusicDisplay](https://opensheetmusicdisplay.org/).

```
audio (file or mic)
   └─ browser: decode + downmix → mono WAV  (fast path)
       └─ POST /api/transcribe
           ├─ backend: decode any format (ffmpeg fallback) → 22.05 kHz mono WAV
           ├─ basic-pitch → polyphonic MIDI
           ├─ music21 → quantize → MusicXML
           └─ → { musicXml, midiBase64, stats }
               └─ frontend: OpenSheetMusicDisplay renders the score
                              + html-midi-player plays the MIDI back (sampled piano)
```

## Architecture

| Layer    | Tech                                            |
|----------|-------------------------------------------------|
| Frontend | React + TypeScript + Vite, OpenSheetMusicDisplay, html-midi-player |
| Backend  | FastAPI (Python), basic-pitch, music21, librosa  |
| Audio    | Web Audio API (client) + ffmpeg (server)         |

```
backend/   FastAPI app + transcription pipeline (see backend/README.md)
frontend/  React/Vite single-page app
```

### Hybrid audio decoding
The browser normalizes any input to a mono WAV before upload (the *fast path*,
sidestepping cross-browser codec quirks). The backend can **also** decode raw
compressed audio (mp3/m4a/webm/…) via **ffmpeg**, so the `POST /api/transcribe`
API is usable by any client — `curl`, mobile, other front-ends — not just this UI.

## Quick start

### Backend
Dependencies are managed with [uv](https://docs.astral.sh/uv/).
```bash
cd backend
sudo apt-get install -y ffmpeg            # decodes non-WAV uploads server-side
uv sync                                   # create .venv + install from uv.lock
uv run uvicorn app.main:app --reload      # serves http://localhost:8000
```
Check it: `curl localhost:8000/api/health` → `{"status":"ok","model_loaded":true,...}`

> A `Dockerfile` is provided (`backend/Dockerfile`) that bundles ffmpeg + deps for deployment.

### Frontend
```bash
cd frontend
npm install
cp .env.example .env          # optional: point VITE_API_URL at your backend
npm run dev                   # serves http://localhost:5173
```
Open http://localhost:5173, upload a piano clip **or** click *Record mic*, and the
sheet music renders with an in-browser **playback** control (sampled piano +
piano-roll) and download buttons for MusicXML and MIDI.

## Testing
```bash
cd backend && uv run pytest
```
The suite synthesizes known tones in-memory and runs the full
decode → transcribe → notation pipeline (it loads the model, so first run is slow).

## Scope (v1) & known limitations
- **Piano only** — single instrument, no source separation.
- Time signature defaults to **4/4**; key is estimated by music21.
- Recordings are transcribed **after you stop** (no real-time streaming yet).
- Accuracy is model-bounded: fast/dense passages, soft notes, and sustain-pedal
  blur can transcribe imperfectly. Detection thresholds are tunable in
  `backend/app/transcription.py` (`TranscriptionParams`).
