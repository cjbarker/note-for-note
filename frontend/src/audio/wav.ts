// Client-side audio normalization (the "fast path" of the hybrid decode design).
//
// Both the file-upload and the microphone path decode their source to an
// AudioBuffer via the Web Audio API, then encode it here to a mono 16-bit PCM
// WAV. The backend can also decode raw audio with ffmpeg, but sending WAV keeps
// uploads consistent and avoids cross-browser codec surprises.

export const TARGET_SAMPLE_RATE = 22050; // matches basic-pitch on the server

// Downmix a (possibly multi-channel) AudioBuffer to a mono Float32Array.
function toMono(buffer: AudioBuffer): Float32Array {
  const { numberOfChannels, length } = buffer;
  if (numberOfChannels === 1) return buffer.getChannelData(0).slice();

  const mono = new Float32Array(length);
  for (let ch = 0; ch < numberOfChannels; ch++) {
    const data = buffer.getChannelData(ch);
    for (let i = 0; i < length; i++) mono[i] += data[i];
  }
  for (let i = 0; i < length; i++) mono[i] /= numberOfChannels;
  return mono;
}

// Resample a mono signal to a target rate using an OfflineAudioContext.
async function resampleMono(
  mono: Float32Array,
  inputRate: number,
  targetRate: number
): Promise<Float32Array> {
  if (inputRate === targetRate) return mono;

  const frames = Math.ceil((mono.length * targetRate) / inputRate);
  const offline = new OfflineAudioContext(1, frames, targetRate);
  const srcBuffer = offline.createBuffer(1, mono.length, inputRate);
  // Copy into a fresh ArrayBuffer-backed view so the typed-array type matches
  // copyToChannel's signature (which rejects ArrayBufferLike-backed views).
  srcBuffer.copyToChannel(new Float32Array(mono), 0);

  const src = offline.createBufferSource();
  src.buffer = srcBuffer;
  src.connect(offline.destination);
  src.start();

  const rendered = await offline.startRendering();
  return rendered.getChannelData(0).slice();
}

// Encode a mono Float32 signal as a 16-bit PCM WAV Blob.
function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const bytesPerSample = 2;
  const dataSize = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };

  writeString(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true); // byte rate
  view.setUint16(32, bytesPerSample, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeString(36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += bytesPerSample;
  }
  return new Blob([view], { type: "audio/wav" });
}

// Decode arbitrary audio bytes (mp3/m4a/webm/wav/...) into an AudioBuffer.
async function decode(bytes: ArrayBuffer): Promise<AudioBuffer> {
  const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
  try {
    // decodeAudioData detaches the buffer in some browsers, so pass a copy.
    return await ctx.decodeAudioData(bytes.slice(0));
  } finally {
    void ctx.close();
  }
}

// Public API: turn any audio Blob into a normalized mono WAV Blob.
export async function blobToWav(input: Blob): Promise<Blob> {
  const bytes = await input.arrayBuffer();
  const audioBuffer = await decode(bytes);
  const mono = toMono(audioBuffer);
  const resampled = await resampleMono(mono, audioBuffer.sampleRate, TARGET_SAMPLE_RATE);
  return encodeWav(resampled, TARGET_SAMPLE_RATE);
}
