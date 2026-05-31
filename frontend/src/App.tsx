import { lazy, Suspense, useState } from "react";
import AudioInput from "./components/AudioInput";
import ErrorBoundary from "./components/ErrorBoundary";
import { transcribe, type TranscriptionResult } from "./api";

// Lazy-loaded so OpenSheetMusicDisplay (the bulk of the bundle) isn't shipped on
// the landing page — it loads only once the first transcription returns.
const SheetMusic = lazy(() => import("./components/SheetMusic"));

export default function App() {
  const [result, setResult] = useState<TranscriptionResult | null>(null);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceName, setSourceName] = useState<string | null>(null);

  const handleAudioReady = async (wav: Blob, name: string) => {
    setError(null);
    setResult(null);
    setBusy(true);
    setSourceName(name);
    setAudioBlob(wav); // keep the normalized WAV for A/B playback vs the MIDI
    try {
      const res = await transcribe(wav, name.replace(/\.[^.]+$/, "") + ".wav");
      setResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app">
      <header>
        <h1>Note-for-Note</h1>
        <p className="tagline">Play piano → get sheet music. Upload a clip or record live.</p>
      </header>

      <AudioInput onAudioReady={handleAudioReady} disabled={busy} />

      {sourceName && !error && <p className="source">Source: {sourceName}</p>}

      {busy && (
        <p className="status">
          Transcribing… (the first run loads the model and may take a moment)
        </p>
      )}
      {error && <p className="error">{error}</p>}

      {result && (
        <ErrorBoundary label="the score">
          <Suspense fallback={<p className="status">Loading score…</p>}>
            <SheetMusic result={result} audioBlob={audioBlob} />
          </Suspense>
        </ErrorBoundary>
      )}

      <footer>
        <p>
          Polyphonic transcription via Spotify <code>basic-pitch</code> · notation by{" "}
          <code>music21</code> · rendered with OpenSheetMusicDisplay. Piano only (v1).
        </p>
      </footer>
    </div>
  );
}
