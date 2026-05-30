"""End-to-end pipeline tests.

We synthesize known-pitch sine tones in-memory, run them through the full
decode -> transcribe -> notation pipeline, and assert the output is sensible.
The basic-pitch model load + inference is slow, so the transcribed MIDI is
produced once via a session-scoped fixture and reused across notation tests.
"""
from __future__ import annotations

import base64
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


@pytest.fixture(scope="session")
def melody_midi():
    """Transcribe the arpeggio once; reused across notation tests (slow step)."""
    path = audio.write_normalized_wav(_melody_wav(), "melody.wav")
    return transcription.transcribe_wav(path)


def _count_measures(xml: str) -> int:
    return xml.count("<measure ")


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


def test_estimate_tempo_returns_plausible():
    # A steady pulse train should yield a finite, positive BPM in a sane range.
    pulse = np.zeros(int(SR * 4), dtype=np.float32)
    for i in range(8):  # a click every 0.5s -> 120 BPM
        pulse[int(i * 0.5 * SR)] = 1.0
    bpm = audio.estimate_tempo(pulse, SR)
    assert np.isfinite(bpm) and 30.0 <= bpm <= 300.0


def test_full_pipeline_detects_notes(melody_midi):
    note_count = sum(len(inst.notes) for inst in melody_midi.instruments)
    assert note_count >= 1, "expected at least one note from the arpeggio"

    xml = notation.midi_to_musicxml(melody_midi)
    assert "<score-partwise" in xml or "<?xml" in xml

    stats = notation.compute_stats(melody_midi)
    assert stats.note_count == note_count
    assert stats.duration_seconds > 0


def test_grand_staff_in_musicxml(melody_midi):
    xml = notation.midi_to_musicxml(melody_midi)
    # A grand staff exports as a 2-staff part and/or a braced part-group.
    assert (
        "<staves>2</staves>" in xml
        or "<staff>2</staff>" in xml
        or "brace" in xml
    ), "expected a two-staff grand staff in the MusicXML"


def test_tempo_affects_note_durations(melody_midi):
    # Same audio seconds: a faster tempo means more beats, hence more measures.
    slow = notation.midi_to_musicxml(melody_midi, tempo=60)
    fast = notation.midi_to_musicxml(melody_midi, tempo=240)
    assert _count_measures(fast) > _count_measures(slow)


def test_renotate_round_trips(melody_midi):
    midi_b64 = base64.b64encode(notation.midi_bytes(melody_midi)).decode("ascii")
    data = base64.b64decode(midi_b64)
    xml, stats = notation.renotate_from_midi_bytes(data, tempo=90, time_signature="3/4")
    assert "<score-partwise" in xml or "<?xml" in xml
    assert stats.time_signature == "3/4"
    assert stats.tempo_bpm == 90.0
    assert stats.note_count == sum(len(i.notes) for i in melody_midi.instruments)


def test_non_wav_requires_ffmpeg_or_raises():
    # Random bytes with an mp3 extension should not crash hard — either ffmpeg
    # decodes (unlikely for noise) or we get a clean AudioDecodeError.
    with pytest.raises(audio.AudioDecodeError):
        audio.load_audio(b"not real audio data", "junk.mp3")
