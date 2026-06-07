// API client for the transcription backend.

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export interface TranscriptionStats {
  note_count: number;
  duration_seconds: number;
  tempo_bpm: number;
  time_signature: string;
  key_signature: string;
}

export interface TranscriptionOutput {
  musicXml: string;
  midiBase64: string;
  stats: TranscriptionStats;
}

// Turn a non-OK response into an Error, preferring the backend's `detail` message.
export async function extractFetchError(res: Response): Promise<Error> {
  let detail = `Request failed (${res.status})`;
  try {
    const body = await res.json();
    if (body?.detail) detail = body.detail;
  } catch {
    /* non-JSON error body */
  }
  return new Error(detail);
}

// POST an audio blob (WAV fast path, or any format the server can decode) and
// return the transcription result.
export async function transcribe(
  audio: Blob,
  filename = "recording.wav"
): Promise<TranscriptionOutput> {
  const form = new FormData();
  form.append("file", audio, filename);

  const res = await fetch(`${API_BASE}/api/transcribe`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) throw await extractFetchError(res);

  return (await res.json()) as TranscriptionOutput;
}

// Re-render notation (tempo / time signature / split point) from already-transcribed MIDI.
// Fast — the backend skips the neural inference and only re-runs music21.
export async function renotate(
  midiBase64: string,
  tempo: number,
  timeSignature: string,
  splitPoint?: number
): Promise<TranscriptionOutput> {
  const body: Record<string, unknown> = { midiBase64, tempo, timeSignature };
  if (splitPoint !== undefined) body.splitPoint = splitPoint;
  const res = await fetch(`${API_BASE}/api/renotate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) throw await extractFetchError(res);

  return (await res.json()) as TranscriptionOutput;
}

// Decode the base64 MIDI from the API into a downloadable Blob.
export function midiBlobFromBase64(b64: string): Blob {
  const binary = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  return new Blob([binary], { type: "audio/midi" });
}
