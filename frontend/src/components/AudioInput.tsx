// Two ways to provide piano audio: upload a file, or record from the mic.
// Both paths normalize to a mono WAV blob (via audio/wav.ts) before handing it
// up to the parent, which sends it to the backend for transcription.
import { useCallback, useEffect, useRef, useState } from "react";
import { blobToWav } from "../audio/wav";

type MicPermission = "granted" | "denied" | "prompt" | "unknown";

interface Props {
  onAudioReady: (wav: Blob, sourceName: string) => void;
  disabled: boolean;
}

export default function AudioInput({ onAudioReady, disabled }: Props) {
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [prepError, setPrepError] = useState<string | null>(null);
  const [micPermission, setMicPermission] = useState<MicPermission>("unknown");

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  // Check microphone permission status on mount (and re-check when needed).
  const checkMicPermission = useCallback(async () => {
    if (typeof navigator.permissions === "undefined") {
      setMicPermission("unknown");
      return;
    }
    try {
      const result = await navigator.permissions.query({ name: "microphone" as PermissionName });
      setMicPermission(result.state);
      // Listen for runtime changes to the permission.
      result.onchange = () => setMicPermission(result.state);
    } catch {
      // Permissions API not supported or error — fall back to unknown.
      setMicPermission("unknown");
    }
  }, []);

  useEffect(() => {
    void checkMicPermission();
    return () => clearTimer();
  }, [checkMicPermission]);

  const handleFile = useCallback(
    async (file: File) => {
      setPrepError(null);
      try {
        const wav = await blobToWav(file);
        onAudioReady(wav, file.name);
      } catch (err) {
        setPrepError(
          `Could not read "${file.name}". Try a WAV/MP3 file. (${(err as Error).message})`
        );
      }
    },
    [onAudioReady]
  );

  const startRecording = useCallback(async () => {
    setPrepError(null);

    // If permission is already denied, don't even try — guide the user.
    if (micPermission === "denied") {
      setPrepError(
        "Microphone access is blocked. Please allow microphone access in your browser settings and try again."
      );
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Re-check permission after a successful stream is obtained.
      void checkMicPermission();
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        clearTimer();
        setRecording(false);
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
        try {
          const wav = await blobToWav(blob);
          onAudioReady(wav, "mic-recording.wav");
        } catch (err) {
          setPrepError(`Could not process recording. (${(err as Error).message})`);
        }
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
      setElapsed(0);
      timerRef.current = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    } catch (err) {
      // Re-check permission status after a failed attempt.
      void checkMicPermission();
      setPrepError(`Microphone unavailable. (${(err as Error).message})`);
    }
  }, [onAudioReady, micPermission, checkMicPermission]);

  const stopRecording = useCallback(() => {
    mediaRecorderRef.current?.stop();
  }, []);

  return (
    <div className="audio-input">
      <div className="input-row">
        <label className={`button ${disabled ? "disabled" : ""}`}>
          Upload audio
          <input
            type="file"
            accept="audio/*"
            disabled={disabled || recording}
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleFile(f);
              e.target.value = "";
            }}
          />
        </label>

        {recording ? (
          <button className="button recording" onClick={stopRecording}>
            ◼ Stop ({elapsed}s)
          </button>
        ) : (
          <button
            className={`button ${micPermission === "denied" ? "denied" : ""}`}
            onClick={startRecording}
            disabled={disabled || micPermission === "denied"}
          >
            ● Record mic
          </button>
        )}
      </div>

      {micPermission === "denied" && (
        <p className="error mic-permission-warning">
          ⚠ Microphone access has been blocked. Go to your browser's site settings and allow
          microphone access, then refresh the page.
        </p>
      )}

      {prepError && <p className="error">{prepError}</p>}
    </div>
  );
}
