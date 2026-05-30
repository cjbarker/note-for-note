"""End-to-end pipeline tests.

We synthesize known-pitch sine tones in-memory, run them through the full
decode -> transcribe -> notation pipeline, and assert the output is sensible.
These tests load the basic-pitch model and are therefore slow-ish; they double
as the project's smoke test.
"""
from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf

from app import audio, notation, transcription

SR = 22050


def _sine(freq: float, seconds: float, sr: int = SR, amp: float = 0.5) -> np.ndarray:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _wav_bytes(samples: np.ndarray, sr: int = SR) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, samples, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _melody_wav() -> bytes:
    # C4, E4, G4, C5 — a clear, well-separated arpeggio basic-pitch can latch onto.
    freqs = [261.63, 329.63, 392.00, 523.25]
    parts = []
    for f in freqs:
        parts.append(_sine(f, 0.6))
        parts.append(np.zeros(int(SR * 0.1), dtype=np.float32))  # gap between notes
    return _wav_bytes(np.concatenate(parts))


def test_load_audio_wav_roundtrip():
    samples = _sine(440.0, 0.5)
    out, sr = audio.load_audio(_wav_bytes(samples), "tone.wav")
    assert sr == SR
    assert out.ndim == 1
    assert len(out) == len(samples)


def test_write_normalized_wav_resamples():
    samples = _sine(440.0, 0.5, sr=44100)
    path = audio.write_normalized_wav(_wav_bytes(samples, sr=44100), "tone.wav")
    out, sr = sf.read(path)
    assert sr == audio.TARGET_SR


def test_full_pipeline_detects_notes():
    wav = _melody_wav()
    path = audio.write_normalized_wav(wav, "melody.wav")
    midi = transcription.transcribe_wav(path)

    note_count = sum(len(inst.notes) for inst in midi.instruments)
    assert note_count >= 1, "expected at least one note from the arpeggio"

    xml = notation.midi_to_musicxml(midi)
    assert "<score-partwise" in xml or "<?xml" in xml

    stats = notation.compute_stats(midi)
    assert stats.note_count == note_count
    assert stats.duration_seconds > 0


def test_non_wav_requires_ffmpeg_or_raises():
    # Random bytes with an mp3 extension should not crash hard — either ffmpeg
    # decodes (unlikely for noise) or we get a clean AudioDecodeError.
    with pytest.raises(audio.AudioDecodeError):
        audio.load_audio(b"not real audio data", "junk.mp3")
