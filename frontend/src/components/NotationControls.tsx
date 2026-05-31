// Tempo + time-signature controls. Changing either re-renders the notation via
// the fast /api/renotate endpoint (no neural re-inference), so the user can dial
// in correct note durations and barring after transcription.
import { useEffect, useRef, useState } from "react";
import { renotate, type TranscriptionStats } from "../api";

interface Props {
  midiBase64: string;
  stats: TranscriptionStats;
  onRenotated: (musicXml: string, stats: TranscriptionStats, midiBase64: string) => void;
}

const TIME_SIGNATURES = ["4/4", "3/4", "2/4", "6/8", "3/8", "2/2"];

export default function NotationControls({ midiBase64, stats, onRenotated }: Props) {
  const [bpm, setBpm] = useState(Math.round(stats.tempo_bpm));
  const [timeSig, setTimeSig] = useState(stats.time_signature);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset the controls to the server's values when a *new* transcription loads.
  useEffect(() => {
    setBpm(Math.round(stats.tempo_bpm));
    setTimeSig(stats.time_signature);
    setError(null);
    // Keyed on midiBase64 so a renotate (which updates stats) doesn't reset us.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [midiBase64]);

  // Debounced re-notation when the user changes a control.
  const onRenotatedRef = useRef(onRenotated);
  onRenotatedRef.current = onRenotated;
  useEffect(() => {
    // Skip when the controls already match the current notation (incl. mount
    // and the state right after a successful renotate) — avoids redundant calls.
    if (bpm === Math.round(stats.tempo_bpm) && timeSig === stats.time_signature) return;

    const handle = window.setTimeout(async () => {
      setBusy(true);
      setError(null);
      try {
        const r = await renotate(midiBase64, bpm, timeSig);
        onRenotatedRef.current(r.musicXml, r.stats, r.midiBase64);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setBusy(false);
      }
    }, 500);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bpm, timeSig]);

  return (
    <div className="notation-controls">
      <label htmlFor="nfn-tempo">
        Tempo
        <input
          id="nfn-tempo"
          type="number"
          min={20}
          max={300}
          value={bpm}
          onChange={(e) => setBpm(Number(e.target.value))}
        />
        <span className="unit">BPM</span>
      </label>
      <label htmlFor="nfn-timesig">
        Time
        <select id="nfn-timesig" value={timeSig} onChange={(e) => setTimeSig(e.target.value)}>
          {TIME_SIGNATURES.map((ts) => (
            <option key={ts} value={ts}>
              {ts}
            </option>
          ))}
        </select>
      </label>
      {busy && (
        <span className="notation-status" role="status">
          re-rendering…
        </span>
      )}
      {error && (
        <span className="error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
