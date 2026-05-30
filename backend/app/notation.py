"""Convert transcribed MIDI into rendered sheet music (MusicXML).

We take the PrettyMIDI produced by basic-pitch, hand it to music21 (which has a
mature MIDI->notation engine), quantize the rhythm to clean up the raw note
timings, estimate the key, and serialize to MusicXML for the frontend to render
with OpenSheetMusicDisplay.
"""
from __future__ import annotations

import io
import tempfile
from dataclasses import dataclass

import pretty_midi


@dataclass
class TranscriptionStats:
    note_count: int
    duration_seconds: float
    tempo_bpm: float


def midi_bytes(midi: pretty_midi.PrettyMIDI) -> bytes:
    """Serialize a PrettyMIDI object to MIDI file bytes (for download/playback)."""
    buf = io.BytesIO()
    midi.write(buf)
    return buf.getvalue()


def compute_stats(midi: pretty_midi.PrettyMIDI) -> TranscriptionStats:
    note_count = sum(len(inst.notes) for inst in midi.instruments)
    duration = midi.get_end_time()
    try:
        tempo = midi.estimate_tempo() if note_count > 1 else 120.0
    except Exception:  # noqa: BLE001 - estimate_tempo needs >=2 onsets
        tempo = 120.0
    return TranscriptionStats(
        note_count=note_count,
        duration_seconds=round(float(duration), 3),
        tempo_bpm=round(float(tempo), 1),
    )


def midi_to_musicxml(midi: pretty_midi.PrettyMIDI, tempo: float | None = None) -> str:
    """Convert a PrettyMIDI object to a MusicXML string.

    Steps: write MIDI to a temp file, parse with music21, quantize rhythm,
    label it as a Piano part, and serialize to MusicXML.
    """
    from music21 import converter, instrument

    with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
        tmp.write(midi_bytes(midi))
        tmp_path = tmp.name

    try:
        # Quantize at MIDI-import time to a 16th-note grid. Using only the (4,)
        # divisor (no triplets) guarantees every duration — notes AND the rests
        # music21 inserts to fill gaps — is expressible in MusicXML. Quantizing
        # during import is more robust than a post-hoc stream.quantize() for the
        # free-timed output basic-pitch produces.
        score = converter.parse(
            tmp_path, quantizePost=True, quarterLengthDivisors=(4,)
        )

        # Present everything as a single Piano part.
        for part in score.parts:
            part.insert(0, instrument.Piano())

        # makeNotation builds measures, beams, accidentals and a key estimate so
        # OSMD has a fully-formed score to render.
        notated = score.makeNotation(inPlace=False)

        out = notated.write("musicxml")
    finally:
        import os

        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    with open(out, "r", encoding="utf-8") as fh:
        xml = fh.read()
    try:
        import os

        os.unlink(out)
    except OSError:
        pass
    return xml
