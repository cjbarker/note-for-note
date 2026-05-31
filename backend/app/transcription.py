"""Polyphonic piano transcription using Spotify's basic-pitch.

basic-pitch is a lightweight neural network that converts audio to MIDI,
detecting multiple simultaneous notes (chords) — essential for piano. We wrap
its ``predict`` API, constrain the pitch range to a piano keyboard, and expose
the detection thresholds as tunable parameters.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

import pretty_midi

# Piano keyboard range: A0 (~27.5 Hz) to C8 (~4186 Hz). Constraining the model
# to this range reduces spurious out-of-range detections.
PIANO_MIN_FREQ = 27.5
PIANO_MAX_FREQ = 4186.0


@dataclass
class TranscriptionParams:
    """Tunable detection thresholds (basic-pitch defaults are 0.5 / 0.3 / 127.7ms)."""

    onset_threshold: float = 0.5
    frame_threshold: float = 0.3
    minimum_note_length_ms: float = 127.70
    minimum_frequency: float = PIANO_MIN_FREQ
    maximum_frequency: float = PIANO_MAX_FREQ


# basic-pitch's model is loaded lazily and cached, so the (slow) first import /
# model load happens once rather than on every request. The lock makes the
# double-checked init safe when concurrent requests race on the first load.
_MODEL = None
_MODEL_LOCK = threading.Lock()


def _get_model():
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                from basic_pitch import ICASSP_2022_MODEL_PATH
                from basic_pitch.inference import Model

                _MODEL = Model(ICASSP_2022_MODEL_PATH)
    return _MODEL


def warm_up() -> bool:
    """Eagerly load the model (e.g. on app startup). Returns True on success."""
    try:
        _get_model()
        return True
    except Exception:  # noqa: BLE001 - health endpoint reports this
        return False


def is_model_loaded() -> bool:
    return _MODEL is not None


def transcribe_wav(
    wav_path: str, params: TranscriptionParams | None = None
) -> pretty_midi.PrettyMIDI:
    """Run basic-pitch on a WAV file and return a PrettyMIDI object."""
    from basic_pitch.inference import predict

    params = params or TranscriptionParams()
    model = _get_model()

    _model_output, midi_data, _note_events = predict(
        wav_path,
        model_or_model_path=model,
        onset_threshold=params.onset_threshold,
        frame_threshold=params.frame_threshold,
        minimum_note_length=params.minimum_note_length_ms,
        minimum_frequency=params.minimum_frequency,
        maximum_frequency=params.maximum_frequency,
    )
    return midi_data
