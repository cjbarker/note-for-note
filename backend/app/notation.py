"""Convert transcribed MIDI into rendered sheet music (MusicXML).

We take the PrettyMIDI produced by basic-pitch and hand it to music21 (which has
a mature MIDI->notation engine). The notes are:
  1. re-timed to a chosen/estimated tempo (basic-pitch bakes in 120 BPM, and
     music21 derives note *values* from tempo, so the tempo must be right for
     durations to be correct),
  2. quantized to a 16th-note grid at import,
  3. split by pitch into a treble + bass grand staff, and
  4. given a time signature and metronome mark,
then serialized to MusicXML for the frontend to render with OpenSheetMusicDisplay.
"""
from __future__ import annotations

import io
import os
import tempfile
from dataclasses import dataclass

import pretty_midi

# Default split point between the two hands: middle C (MIDI 60). Notes >= this go
# to the treble (right-hand) staff, below go to the bass (left-hand) staff.
DEFAULT_SPLIT_POINT = 60
DEFAULT_TIME_SIGNATURE = "4/4"


@dataclass
class TranscriptionStats:
    note_count: int
    duration_seconds: float
    tempo_bpm: float
    time_signature: str = DEFAULT_TIME_SIGNATURE


def midi_bytes(midi: pretty_midi.PrettyMIDI) -> bytes:
    """Serialize a PrettyMIDI object to MIDI file bytes (for download/playback)."""
    buf = io.BytesIO()
    midi.write(buf)
    return buf.getvalue()


def compute_stats(
    midi: pretty_midi.PrettyMIDI,
    tempo_bpm: float | None = None,
    time_signature: str = DEFAULT_TIME_SIGNATURE,
) -> TranscriptionStats:
    note_count = sum(len(inst.notes) for inst in midi.instruments)
    duration = midi.get_end_time()
    if tempo_bpm is None:
        try:
            tempo_bpm = midi.estimate_tempo() if note_count > 1 else 120.0
        except Exception:  # noqa: BLE001 - estimate_tempo needs >=2 onsets
            tempo_bpm = 120.0
    return TranscriptionStats(
        note_count=note_count,
        duration_seconds=round(float(duration), 3),
        tempo_bpm=round(float(tempo_bpm), 1),
        time_signature=time_signature,
    )


def _retempo_midi(
    midi: pretty_midi.PrettyMIDI, tempo_bpm: float
) -> pretty_midi.PrettyMIDI:
    """Return a copy of ``midi`` whose tempo metadata is ``tempo_bpm``.

    Note times are stored in seconds (tempo-independent); rewriting the tempo so
    that music21 maps seconds->quarterLengths at the intended BPM is what makes
    the notated durations correct.
    """
    out = pretty_midi.PrettyMIDI(initial_tempo=float(tempo_bpm))
    for inst in midi.instruments:
        new_inst = pretty_midi.Instrument(
            program=inst.program, is_drum=inst.is_drum, name=inst.name
        )
        for n in inst.notes:
            new_inst.notes.append(
                pretty_midi.Note(
                    velocity=n.velocity, pitch=n.pitch, start=n.start, end=n.end
                )
            )
        out.instruments.append(new_inst)
    return out


def _split_to_grand_staff(score, split_point: int):
    """Split a parsed single-part ``score`` into a treble+bass grand staff.

    Returns a new music21 Score containing two PartStaff objects joined by a
    brace StaffGroup. Raises on unexpected structure so the caller can fall back.
    """
    from music21 import clef, layout, note as m21note, stream

    flat = score.flatten()

    treble = stream.PartStaff()
    bass = stream.PartStaff()
    treble.insert(0, clef.TrebleClef())
    bass.insert(0, clef.BassClef())

    for el in flat.notesAndRests:
        offset = el.offset
        if isinstance(el, m21note.Rest):
            # Rests are regenerated per-staff by makeNotation; skip here.
            continue
        if "Chord" in el.classes:
            hi = [p for p in el.pitches if p.midi >= split_point]
            lo = [p for p in el.pitches if p.midi < split_point]
            _insert_pitches(treble, offset, el.duration, hi)
            _insert_pitches(bass, offset, el.duration, lo)
        else:  # a single Note
            target = treble if el.pitch.midi >= split_point else bass
            target.insert(offset, el)

    return treble, bass, layout


def _insert_pitches(part, offset, duration, pitches):
    """Insert ``pitches`` at ``offset`` as a Note or Chord (no-op if empty)."""
    from music21 import chord as m21chord, note as m21note

    if not pitches:
        return
    if len(pitches) == 1:
        el = m21note.Note(pitches[0])
    else:
        el = m21chord.Chord(pitches)
    el.duration.quarterLength = duration.quarterLength
    part.insert(offset, el)


def midi_to_musicxml(
    midi: pretty_midi.PrettyMIDI,
    tempo: float | None = None,
    time_signature: str = DEFAULT_TIME_SIGNATURE,
    split_point: int = DEFAULT_SPLIT_POINT,
) -> str:
    """Convert a PrettyMIDI object to a grand-staff MusicXML string.

    ``tempo`` (BPM) drives note durations; ``time_signature`` (e.g. "3/4") drives
    barring; ``split_point`` (MIDI number) divides treble/bass. If the grand-staff
    split fails for any reason, falls back to a readable single-staff score.
    """
    from music21 import converter, instrument, meter, stream, tempo as m21tempo

    if tempo and tempo > 0:
        midi = _retempo_midi(midi, tempo)

    with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
        tmp.write(midi_bytes(midi))
        tmp_path = tmp.name

    try:
        # Quantize at MIDI-import time to a 16th-note grid. Using only the (4,)
        # divisor (no triplets) guarantees every duration is expressible in
        # MusicXML for the free-timed output basic-pitch produces.
        parsed = converter.parse(tmp_path, quantizePost=True, quarterLengthDivisors=(4,))

        ts = meter.TimeSignature(time_signature)
        mm = m21tempo.MetronomeMark(number=tempo) if tempo and tempo > 0 else None

        try:
            treble, bass, layout = _split_to_grand_staff(parsed, split_point)
            for part in (treble, bass):
                part.insert(0, instrument.Piano())
                part.insert(0, meter.TimeSignature(time_signature))
                if mm is not None:
                    part.insert(0, m21tempo.MetronomeMark(number=tempo))
            score = stream.Score()
            score.insert(0, treble)
            score.insert(0, bass)
            score.insert(0, layout.StaffGroup([treble, bass], symbol="brace", barTogether=True))
            notated = score.makeNotation(inPlace=False)
        except Exception:  # noqa: BLE001 - fall back to a single staff
            for part in parsed.parts:
                part.insert(0, instrument.Piano())
                part.insert(0, ts)
                if mm is not None:
                    part.insert(0, m21tempo.MetronomeMark(number=tempo))
            notated = parsed.makeNotation(inPlace=False)

        out = notated.write("musicxml")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    with open(out, "r", encoding="utf-8") as fh:
        xml = fh.read()
    try:
        os.unlink(out)
    except OSError:
        pass
    return xml


def renotate_from_midi_bytes(
    data: bytes,
    tempo: float | None = None,
    time_signature: str = DEFAULT_TIME_SIGNATURE,
    split_point: int = DEFAULT_SPLIT_POINT,
) -> tuple[str, TranscriptionStats]:
    """Re-run only the (fast) notation step from raw MIDI bytes.

    Lets the UI re-render with a new tempo / time signature without paying for a
    fresh basic-pitch inference pass.
    """
    midi = pretty_midi.PrettyMIDI(io.BytesIO(data))
    xml = midi_to_musicxml(midi, tempo, time_signature, split_point)
    stats = compute_stats(midi, tempo_bpm=tempo, time_signature=time_signature)
    return xml, stats
