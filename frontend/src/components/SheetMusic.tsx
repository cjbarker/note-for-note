import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { midiBlobFromBase64, type TranscriptionOutput, type TranscriptionStats } from "../api";
import NotationControls from "./NotationControls";
import { exportPdf, exportPng, exportSvg } from "../export";
import { downloadBlob } from "../lib/download";

// Lazy-loaded: html-midi-player pulls in Tone.js + @magenta/music (~2 MB), which
// we only need once a transcription exists. Splitting it keeps initial load light.
const MidiPlayer = lazy(() => import("./MidiPlayer"));

interface Props {
  result: TranscriptionOutput;
  audioBlob: Blob | null;
}

// Plays back the user's original recording, for A/B comparison with the MIDI.
function OriginalAudio({ blob }: { blob: Blob }) {
  const url = useMemo(() => URL.createObjectURL(blob), [blob]);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);
  return <audio className="orig-audio" controls src={url} aria-label="Original recording" />;
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
  const [renderError, setRenderError] = useState<string | null>(null);

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
        // Enable a follow cursor for score-synced playback (type 0 = standard).
        cursorsOptions: [{ type: 0, color: "#1d7bce", alpha: 0.45, follow: true }],
      });
    }

    let cancelled = false;
    setRenderError(null);
    osmdRef.current
      .load(musicXml)
      .then(() => {
        if (!cancelled) osmdRef.current?.render();
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("OSMD failed to render MusicXML:", err);
        setRenderError((err as Error).message);
      });

    return () => {
      cancelled = true;
    };
  }, [musicXml]);

  // Retry rendering when the user clicks the retry button.
  const handleRetryRender = useCallback(() => {
    setRenderError(null);
    osmdRef.current?.load(musicXml).then(() => {
      osmdRef.current?.render();
    });
  }, [musicXml]);

  // --- Score-follow cursor, driven by the MIDI player's playback events. ---
  // Kept in a ref so the (stable) callbacks always read the current tempo,
  // which maps playback seconds -> musical position (whole notes).
  const bpmRef = useRef(stats.tempo_bpm);
  useEffect(() => {
    bpmRef.current = stats.tempo_bpm;
  }, [stats.tempo_bpm]);

  const handlePlaybackStart = useCallback(() => {
    const cursor = osmdRef.current?.cursor;
    if (!cursor) return;
    cursor.reset();
    cursor.show();
  }, []);

  const handlePlaybackNote = useCallback((startSeconds: number) => {
    const cursor = osmdRef.current?.cursor;
    if (!cursor) return;
    // seconds -> quarter notes (bpm = quarter BPM) -> whole notes (4 quarters).
    const targetWholeNotes = (startSeconds * (bpmRef.current || 120)) / 60 / 4;
    let guard = 0;
    while (
      !cursor.Iterator.EndReached &&
      cursor.Iterator.currentTimeStamp.RealValue < targetWholeNotes - 1e-6 &&
      guard < 5000
    ) {
      cursor.next();
      guard++;
    }
  }, []);

  const handlePlaybackStop = useCallback(() => {
    osmdRef.current?.cursor?.hide();
  }, []);

  return (
    <div className="sheet-music">
      <div className="stats">
        <span>{stats.note_count} notes</span>
        <span>{stats.duration_seconds.toFixed(1)}s</span>
        <span>~{stats.tempo_bpm} BPM</span>
        <span>{stats.time_signature}</span>
        {stats.key_signature && <span>Key: {stats.key_signature}</span>}
      </div>

      <NotationControls
        midiBase64={result.midiBase64}
        stats={stats}
        onRenotated={(xml, st, midi, splitPoint) => {
          setMusicXml(xml);
          setStats(st);
          setMidiBase64(midi);
          if (splitPoint !== undefined) {
            // Update the split point ref so playback cursor stays in sync.
            // (splitPoint doesn't affect playback, only notation.)
          }
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
              <MidiPlayer
                midiBase64={midiBase64}
                onPlaybackStart={handlePlaybackStart}
                onPlaybackNote={handlePlaybackNote}
                onPlaybackStop={handlePlaybackStop}
              />
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
            downloadBlob(
              new Blob([musicXml], { type: "application/xml" }),
              "transcription.musicxml"
            )
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

      {renderError && (
        <div className="error" role="alert">
          <span>Could not render the score: {renderError}</span>
          <button className="button small" onClick={handleRetryRender}>
            Retry
          </button>
        </div>
      )}
      <div className="score" ref={containerRef} />
    </div>
  );
}
