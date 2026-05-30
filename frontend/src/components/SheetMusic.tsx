// Renders the transcribed MusicXML as engraved sheet music using
// OpenSheetMusicDisplay, plus download buttons for the MusicXML and MIDI.
import { useEffect, useRef } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { midiBlobFromBase64, type TranscriptionResult } from "../api";

interface Props {
  result: TranscriptionResult;
}

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function SheetMusic({ result }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null);

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
      .load(result.musicXml)
      .then(() => {
        if (!cancelled) osmdRef.current?.render();
      })
      .catch((err) => {
        console.error("OSMD failed to render MusicXML:", err);
      });

    return () => {
      cancelled = true;
    };
  }, [result.musicXml]);

  const { stats } = result;

  return (
    <div className="sheet-music">
      <div className="stats">
        <span>{stats.note_count} notes</span>
        <span>{stats.duration_seconds.toFixed(1)}s</span>
        <span>~{stats.tempo_bpm} BPM</span>
      </div>

      <div className="downloads">
        <button
          className="button small"
          onClick={() =>
            download(new Blob([result.musicXml], { type: "application/xml" }), "transcription.musicxml")
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
