import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import {
  midiBlobFromBase64,
  type TranscriptionResult,
  type TranscriptionStats,
} from "../api";
import NotationControls from "./NotationControls";
import { exportPdf, exportPng, exportSvg } from "../export";
import { downloadBlob } from "../lib/download";

// Lazy-loaded: html-midi-player pulls in Tone.js + @magenta/music (~2 MB), which
// we only need once a transcription exists. Splitting it keeps initial load light.
const MidiPlayer = lazy(() => import("./MidiPlayer"));

interface Props {
  result: TranscriptionResult;
  audioBlob: Blob | null;
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
  // MIDI follows re-notation (tempo changes) so playback/download match the score.
  const [midiBase64, setMidiBase64] = useState(result.midiBase64);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  async function runExport(fn: () => Promise<void> | void) {
    setExporting(true);
    setExportError(null);
    try {
      await fn();
    } catch (err) {
      setExportError((err as Error).message);
    } finally {
      setExporting(false);
    }
  }
  useEffect(() => {
    setMusicXml(result.musicXml);
    setStats(result.stats);
    setMidiBase64(result.midiBase64);
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
        onRenotated={(xml, st, midi) => {
          setMusicXml(xml);
          setStats(st);
          setMidiBase64(midi);
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
              <MidiPlayer midiBase64={midiBase64} />
            </Suspense>
          </div>
        </div>
      )}

      {stats.note_count > 0 && (
        <div className="exports">
          <span className="exports-label">Export chart:</span>
          <button
            className="button small"
            disabled={exporting}
            onClick={() => runExport(() => exportPdf(musicXml, "transcription.pdf"))}
          >
            PDF
          </button>
          <button
            className="button small"
            disabled={exporting}
            onClick={() => runExport(() => exportPng(musicXml, "transcription.png"))}
          >
            PNG
          </button>
          <button
            className="button small"
            disabled={exporting}
            onClick={() =>
              runExport(() => {
                const svg = containerRef.current?.querySelector("svg");
                if (!svg) throw new Error("Score isn't rendered yet.");
                exportSvg(svg as SVGElement, "transcription.svg");
              })
            }
          >
            SVG
          </button>
          {exporting && <span className="notation-status">exporting…</span>}
          {exportError && <span className="error">{exportError}</span>}
        </div>
      )}

      <div className="downloads">
        <button
          className="button small"
          onClick={() =>
            downloadBlob(new Blob([musicXml], { type: "application/xml" }), "transcription.musicxml")
          }
        >
          Download MusicXML
        </button>
        <button
          className="button small"
          onClick={() => downloadBlob(midiBlobFromBase64(midiBase64), "transcription.mid")}
        >
          Download MIDI
        </button>
      </div>

      <div className="score" ref={containerRef} />
    </div>
  );
}
