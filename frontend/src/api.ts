// API client for the transcription backend.

const API_BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export interface TranscriptionStats {
  note_count: number;
  duration_seconds: number;
  tempo_bpm: number;
  time_signature: string;
}

export interface RenotateResult {
  musicXml: string;
  stats: TranscriptionStats;
}

export interface TranscriptionResult {
  musicXml: string;
  midiBase64: string;
  stats: TranscriptionStats;
}

// POST an audio blob (WAV fast path, or any format the server can decode) and
// return the transcription result.
export async function transcribe(
  audio: Blob,
  filename = "recording.wav"
): Promise<TranscriptionResult> {
  const form = new FormData();
  form.append("file", audio, filename);

  const res = await fetch(`${API_BASE}/api/transcribe`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }

  return (await res.json()) as TranscriptionResult;
}

// Re-render notation (tempo / time signature) from already-transcribed MIDI.
// Fast — the backend skips the neural inference and only re-runs music21.
export async function renotate(
  midiBase64: string,
  tempo: number,
  timeSignature: string
): Promise<RenotateResult> {
  const res = await fetch(`${API_BASE}/api/renotate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ midiBase64, tempo, timeSignature }),
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }

  return (await res.json()) as RenotateResult;
}

// Decode the base64 MIDI from the API into a downloadable Blob.
export function midiBlobFromBase64(b64: string): Blob {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: "audio/midi" });
}
