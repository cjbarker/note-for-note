# Note-4-Note — Frontend

React + TypeScript + Vite single-page app. It captures piano audio (file upload or
live mic), sends it to the backend for transcription, renders the resulting
MusicXML as a grand staff with [OpenSheetMusicDisplay](https://opensheetmusicdisplay.org/),
and offers tempo/time-signature re-notation, playback (with a score-follow cursor),
A/B against the original recording, and PDF/PNG/SVG export.

## Prerequisites

- Node 22+
- A running backend (see `../backend/README.md`). Point the app at it with
  `VITE_API_URL` (defaults to `http://localhost:8000`).

## Setup & run

```bash
npm install
cp .env.example .env      # optional: set VITE_API_URL
npm run dev               # http://localhost:5173
```

## Scripts

| Script            | Purpose                                  |
| ----------------- | ---------------------------------------- |
| `npm run dev`     | Vite dev server with HMR                 |
| `npm run build`   | Type-check (`tsc -b`) + production build |
| `npm run preview` | Serve the production build locally       |
| `npm run test`    | Vitest unit tests (jsdom)                |
| `npm run lint`    | ESLint (flat config, `--max-warnings=0`) |
| `npm run format`  | Prettier check                           |

## Configuration

- `VITE_API_URL` — backend base URL, read in `src/api.ts`. See `.env.example`.

## Structure

```
src/
├── App.tsx                     top-level state; lazy-loads the score UI
├── api.ts                      transcribe() / renotate() + error helpers
├── export.ts                   client-side PDF/PNG/SVG export (lazy jsPDF/svg2pdf)
├── audio/wav.ts                Web Audio → mono 16-bit WAV (upload + mic)
├── lib/download.ts             shared blob-download helper
├── components/
│   ├── AudioInput.tsx          file upload + mic recording
│   ├── SheetMusic.tsx          OSMD render, controls, players, exports, cursor
│   ├── NotationControls.tsx    tempo/time-signature (debounced /api/renotate)
│   ├── MidiPlayer.tsx          html-midi-player (sampled piano + piano-roll)
│   └── ErrorBoundary.tsx       guards the score subtree from render crashes
└── test/setup.ts               Vitest + jest-dom setup
```

## Notes

- **Bundle:** OpenSheetMusicDisplay, the MIDI player (Tone.js + @magenta/music), and
  the PDF libs are code-split and loaded on demand, keeping initial load light.
- **Custom elements:** `html-midi-player` ships no types; `src/html-midi-player.d.ts`
  declares `<midi-player>` / `<midi-visualizer>` for TSX.
