"""Unit tests for the audio + notation helpers that don't need the model."""

from __future__ import annotations

import io

import numpy as np
import pretty_midi

from app import audio, notation
from tests.helpers import SR, sine, wav_bytes


def test_load_audio_downmixes_stereo_to_mono():
    mono = sine(440.0, 0.2)
    stereo = np.stack([mono, mono], axis=1)  # shape (n, 2)
    out, sr = audio.load_audio(wav_bytes(stereo), "stereo.wav")
    assert out.ndim == 1
    assert len(out) == len(mono)
    assert sr == SR


def test_decode_and_wav_returns_samples_and_resamples():
    data = wav_bytes(sine(440.0, 0.3, sr=44100), sr=44100)
    path, samples, sr = audio.decode_and_wav(data, "tone.wav")
    try:
        assert sr == audio.TARGET_SR
        assert samples.ndim == 1 and samples.size > 0
    finally:
        audio._safe_unlink(path)


def test_estimate_tempo_on_empty_returns_default():
    assert audio.estimate_tempo(np.zeros(0, dtype=np.float32), SR) == 120.0


def test_estimate_tempo_on_silence_is_finite_positive():
    bpm = audio.estimate_tempo(np.zeros(SR, dtype=np.float32), SR)
    assert np.isfinite(bpm) and bpm > 0


def test_duration_seconds():
    assert audio.duration_seconds(np.zeros(SR), SR) == 1.0
    assert audio.duration_seconds(np.zeros(10), 0) == 0.0


def test_safe_unlink_is_noop_on_missing_file():
    audio._safe_unlink("/tmp/does-not-exist-xyz.wav")  # must not raise


def test_retempo_preserves_notes_changes_tempo_metadata():
    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    inst = pretty_midi.Instrument(program=0)
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=60, start=0.0, end=0.5))
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=64, start=0.5, end=1.0))
    midi.instruments.append(inst)

    out = notation._retempo_midi(midi, 90)

    notes = out.instruments[0].notes
    assert [n.pitch for n in notes] == [60, 64]
    assert [round(n.start, 3) for n in notes] == [0.0, 0.5]  # note seconds preserved
    _times, tempi = out.get_tempo_changes()
    assert abs(float(tempi[0]) - 90.0) < 1.0


def test_compute_stats_defaults_tempo_for_single_note():
    midi = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=60, start=0.0, end=0.5))
    midi.instruments.append(inst)

    stats = notation.compute_stats(midi)
    assert stats.note_count == 1
    assert stats.tempo_bpm == 120.0
    assert stats.time_signature == "4/4"


def test_midi_bytes_round_trips():
    midi = pretty_midi.PrettyMIDI(initial_tempo=100)
    inst = pretty_midi.Instrument(program=0)
    inst.notes.append(pretty_midi.Note(velocity=80, pitch=60, start=0.0, end=0.5))
    midi.instruments.append(inst)

    data = notation.midi_bytes(midi)
    reloaded = pretty_midi.PrettyMIDI(io.BytesIO(data))
    assert sum(len(i.notes) for i in reloaded.instruments) == 1
