import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import {
  midiBlobFromBase64,
  type TranscriptionResult,
  type TranscriptionStats,
} from "../api";
import NotationControls from "./NotationControls";

// Lazy-loaded: html-midi-player pulls in Tone.js + @magenta/music (~2 MB), which
// we only need once a transcription exists. Splitting it keeps initial load light.
const MidiPlayer = lazy(() => import("./MidiPlayer"));

interface Props {
  result: TranscriptionResult;
  audioBlob: Blob | null;
}

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// Plays back the user's original recording, for A/B comparison with the MIDI.
function OriginalAudio({ blob }: { blob: Blob }) {
  const url = useMemo(() => URL.createObjectURL(blob), [blob]);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);
  return <audio className="orig-audio" controls src={url} />;
}

export default function SheetMusic({ result, audioBlob }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null);

  // Notation (musicXml + stats) can be re-rendered client-side via renotate, so
  // track it in state, re-initialized whenever a new transcription arrives.
  const [musicXml, setMusicXml] = useState(result.musicXml);
  const [stats, setStats] = useState<TranscriptionStats>(result.stats);
  useEffect(() => {
    setMusicXml(result.musicXml);
    setStats(result.stats);
  }, [result]);

  useEffect(() => {
    if (!containerRef.current) return;

    if (!osmdRef.current) {
      osmdRef.current = new OpenSheetMusicDisplay(containerRef.current, {
        autoResize: true,
        drawTitle: false,
      });
    }

    let cancelled = false;
    osmdRef.current
      .load(musicXml)
      .then(() => {
        if (!cancelled) osmdRef.current?.render();
      })
      .catch((err) => {
        console.error("OSMD failed to render MusicXML:", err);
      });

    return () => {
      cancelled = true;
    };
  }, [musicXml]);

  return (
    <div className="sheet-music">
      <div className="stats">
        <span>{stats.note_count} notes</span>
        <span>{stats.duration_seconds.toFixed(1)}s</span>
        <span>~{stats.tempo_bpm} BPM</span>
        <span>{stats.time_signature}</span>
      </div>

      <NotationControls
        midiBase64={result.midiBase64}
        stats={stats}
        onRenotated={(xml, st) => {
          setMusicXml(xml);
          setStats(st);
        }}
      />

      {stats.note_count > 0 && (
        <div className="playback">
          <div className="player-block">
            <span className="playback-label">Original audio</span>
            {audioBlob ? (
              <OriginalAudio blob={audioBlob} />
            ) : (
              <span className="muted">unavailable</span>
            )}
          </div>
          <div className="player-block">
            <span className="playback-label">Transcription (QA)</span>
            <Suspense fallback={<span className="playback-loading">Loading player…</span>}>
              <MidiPlayer midiBase64={result.midiBase64} />
            </Suspense>
          </div>
        </div>
      )}

      <div className="downloads">
        <button
          className="button small"
          onClick={() =>
            download(new Blob([musicXml], { type: "application/xml" }), "transcription.musicxml")
          }
        >
          Download MusicXML
        </button>
        <button
          className="button small"
          onClick={() => download(midiBlobFromBase64(result.midiBase64), "transcription.mid")}
        >
          Download MIDI
        </button>
      </div>

      <div className="score" ref={containerRef} />
    </div>
  );
}
