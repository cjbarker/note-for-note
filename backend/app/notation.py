"""Convert transcribed MIDI into rendered sheet music (MusicXML).

We take the PrettyMIDI produced by basic-pitch and hand it to music21 (which has
a mature MIDI->notation engine). The notes are:
  1. re-timed to a chosen/estimated tempo (basic-pitch bakes in 120 BPM, and
     music21 derives note *values* from tempo, so the tempo must be right for
     durations to be correct),
  2. legato-cleaned and pre-quantized to an eighth-note grid (fills inter-note
     gaps from early key releases so durations match the full inter-onset
     interval, then snaps start/end times to clean rhythmic positions),
  3. quantized by music21 to an eighth-note grid at import,
  4. split by pitch into a treble + bass grand staff, and
  5. given a time signature and metronome mark,
then serialized to MusicXML for the frontend to render with OpenSheetMusicDisplay.
"""

from __future__ import annotations

import io
import logging
import tempfile
from dataclasses import dataclass

import pretty_midi

from . import _music21
from .audio import _safe_unlink


class NotationError(RuntimeError):
    """Raised when notation conversion fails."""

logger = logging.getLogger("note_for_note")

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
    key_signature: str = ""


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
        if note_count < 2:
            tempo_bpm = 120.0
        else:
            try:
                tempo_bpm = midi.estimate_tempo()
            except ValueError:
                # estimate_tempo needs >=2 onsets; fall back to 120.
                tempo_bpm = 120.0
    key_sig = _estimate_key_signature(midi)
    return TranscriptionStats(
        note_count=note_count,
        duration_seconds=round(float(duration), 3),
        tempo_bpm=round(float(tempo_bpm), 1),
        time_signature=time_signature,
        key_signature=key_sig,
    )


def _estimate_key_signature(midi: pretty_midi.PrettyMIDI) -> str:
    """Estimate the key signature from note distribution using music21.

    Returns an empty string if estimation is not possible.
    """
    try:
        #key = _music21.key  # type: ignore[attr-defined]
        analyzer = _music21.analysis  # type: ignore[attr-defined]

        # Collect all pitches from all instruments.
        pitches = []
        for inst in midi.instruments:
            for note in inst.notes:
                pitches.append(note.pitch.midi)

        if not pitches:
            return ""

        # Build a music21 stream and run krumhansl-schmuckler key estimation.
        stream_obj = _music21.stream.Score()  # type: ignore[attr-defined]
        part = _music21.stream.Part()  # type: ignore[attr-defined]
        for m in pitches:
            n = _music21.note.Note(m)  # type: ignore[attr-defined]
            n.duration.type = "quarter"
            part.append(n)
        stream_obj.append(part)

        # Use krumhansl-schmuckler (default in music21).
        result = analyzer.analyze(stream_obj, method="krumhansl")
        if result is not None:
            return str(result.key_name)  # e.g. "C major", "G minor"
    except Exception:
        logger.warning("Key signature estimation failed", exc_info=True)
    return ""


def _retempo_midi(midi: pretty_midi.PrettyMIDI, tempo_bpm: float) -> pretty_midi.PrettyMIDI:
    """Return a copy of ``midi`` whose tempo metadata is ``tempo_bpm``.

    Note times are stored in seconds (tempo-independent); rewriting the tempo so
    that music21 maps seconds->quarterLengths at the intended BPM is what makes
    the notated durations correct.
    """
    out = pretty_midi.PrettyMIDI(initial_tempo=float(tempo_bpm))
    for inst in midi.instruments:
        new_inst = pretty_midi.Instrument(
            program=inst.program,
            is_drum=inst.is_drum,
            name=inst.name,
        )
        new_inst.notes = [
            pretty_midi.Note(velocity=n.velocity, pitch=n.pitch, start=n.start, end=n.end)
            for n in inst.notes
        ]
        out.instruments.append(new_inst)
    return out


def _split_to_grand_staff(score, split_point: int):
    """Split a parsed single-part ``score`` into a treble+bass grand staff.

    Returns a new music21 Score with two PartStaff objects joined by a
    brace StaffGroup. Raises on unexpected structure so the caller can fall back.
    """
    m21note = _music21.note  # type: ignore[attr-defined]
    clef = _music21.clef  # type: ignore[attr-defined]
    stream = _music21.stream  # type: ignore[attr-defined]

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

    # Accessing _music21.layout triggers the lazy import (via __getattr__) so
    # we don't have to import music21 at module load time.
    _music21.layout  # noqa
    return treble, bass


def _insert_pitches(part, offset, duration, pitches):
    """Insert ``pitches`` at ``offset`` as a Note or Chord (no-op if empty)."""
    m21chord = _music21.chord  # type: ignore[attr-defined]
    m21note = _music21.note  # type: ignore[attr-defined]

    if not pitches:
        return
    if len(pitches) == 1:
        el = m21note.Note(pitches[0])  # type: ignore[attr-defined]
    else:
        el = m21chord.Chord(pitches)  # type: ignore[attr-defined]
    el.duration.quarterLength = duration.quarterLength
    part.insert(offset, el)


def _setup_part(part, time_signature: str, tempo: float | None) -> None:
    """Insert the piano instrument, time signature, and (optional) tempo mark."""
    instrument = _music21.instrument  # type: ignore[attr-defined]
    meter = _music21.meter  # type: ignore[attr-defined]
    m21tempo = _music21.tempo  # type: ignore[attr-defined]

    part.insert(0, instrument.Piano())  # type: ignore[attr-defined]
    part.insert(0, meter.TimeSignature(time_signature))  # type: ignore[attr-defined]
    if tempo and tempo > 0:
        part.insert(0, m21tempo.MetronomeMark(number=tempo))  # type: ignore[attr-defined]


def _legato_quantize_midi(
    midi: pretty_midi.PrettyMIDI, tempo: float
) -> pretty_midi.PrettyMIDI:
    """Fill small inter-note gaps and snap times to an eighth-note grid.

    basic-pitch detects note-off when the sound decays below its frame
    threshold, which is often well before the next note starts — especially
    with staccato playing or quick key releases.  Those gaps become spurious
    rests and force surrounding notes into shorter, complex durations
    (e.g. eighth + rest instead of a clean quarter note).

    This two-step cleanup:
      1. **Legato fill** — extends each note's end to meet the next note's
         start when the gap is ≤ one beat *and the notes share the same pitch*,
         so note durations cover the full inter-onset interval.  Gaps between
         notes of different pitches are *not* filled because extending them
         would cause the earlier note to overlap the later one, which music21
         then misinterprets as a chord.
      2. **Grid snap** — rounds start/end times to the nearest eighth-note
         position so the MIDI ticks that music21 reads are already aligned to
         clean rhythmic values.
    """
    beat_dur = 60.0 / tempo
    grid = beat_dur / 2  # eighth-note grid (seconds)
    # Notes starting within 10 % of a beat are treated as simultaneous (chord).
    sim_thresh = beat_dur * 0.1

    out = pretty_midi.PrettyMIDI(initial_tempo=float(tempo))
    for inst in midi.instruments:
        new_inst = pretty_midi.Instrument(
            program=inst.program, is_drum=inst.is_drum, name=inst.name
        )
        notes = sorted(inst.notes, key=lambda n: n.start)

        for i, n in enumerate(notes):
            end = n.end
            # Find the next non-simultaneous note of the *same pitch* and fill
            # any small gap so consecutive same-pitch notes merge into one
            # clean duration.  Gaps between different pitches are left alone;
            # extending them would make the earlier note overlap the later one,
            # which music21 would then render as a chord.
            for j in range(i + 1, len(notes)):
                if notes[j].start - n.start > sim_thresh:
                    gap = notes[j].start - end
                    if 0 < gap <= beat_dur and notes[j].pitch == n.pitch:
                        end = notes[j].start
                    break

            # Snap to the eighth-note grid.
            start = round(n.start / grid) * grid
            end = round(end / grid) * grid
            if end <= start:
                end = start + grid

            new_inst.notes.append(
                pretty_midi.Note(
                    velocity=n.velocity, pitch=n.pitch, start=start, end=end
                )
            )
        out.instruments.append(new_inst)
    return out


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
    converter = _music21.converter  # type: ignore[attr-defined]
    stream = _music21.stream  # type: ignore[attr-defined]

    if tempo and tempo > 0:
        midi = _retempo_midi(midi, tempo)

    # Pre-quantize note times and fill inter-note gaps so music21 receives
    # clean rhythmic input (avoids spurious eighth + rest patterns).
    effective_tempo = tempo if (tempo and tempo > 0) else 120.0
    midi = _legato_quantize_midi(midi, effective_tempo)

    with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
        tmp.write(midi_bytes(midi))
        tmp_path = tmp.name

    try:
        # Quantize at MIDI-import time to an eighth-note grid. Using only the
        # (2,) divisor (no triplets) guarantees every duration is expressible
        # in standard MusicXML notation.
        parsed = converter.parse(tmp_path, quantizePost=True, quarterLengthDivisors=(2,))  # type: ignore[attr-defined]

        try:
            treble, bass = _split_to_grand_staff(parsed, split_point)
            for part in (treble, bass):
                _setup_part(part, time_signature, tempo)
            score = stream.Score()  # type: ignore[attr-defined]
            score.insert(0, treble)
            score.insert(0, bass)
            score.insert(
                0,
                _music21.layout.StaffGroup(  # type: ignore[attr-defined]
                    [treble, bass], symbol="brace", barTogether=True
                ),
            )
            notated = score.makeNotation(inPlace=False)
        except Exception:  # noqa: BLE001 - fall back to a single staff
            logger.warning("grand-staff split failed; using single staff", exc_info=True)
            for part in parsed.parts:
                _setup_part(part, time_signature, tempo)
            notated = parsed.makeNotation(inPlace=False)

        out = notated.write("musicxml")
    finally:
        _safe_unlink(tmp_path)

    with open(out, encoding="utf-8") as fh:
        xml = fh.read()
    _safe_unlink(out)
    return xml


def renotate_from_midi_bytes(
    data: bytes,
    tempo: float | None = None,
    time_signature: str = DEFAULT_TIME_SIGNATURE,
    split_point: int = DEFAULT_SPLIT_POINT,
) -> tuple[str, TranscriptionStats, bytes]:
    """Re-run only the (fast) notation step from raw MIDI bytes.

    Lets the UI re-render with a new tempo / time signature without paying for a
    fresh basic-pitch inference pass. Also returns a MIDI re-timed to ``tempo`` so
    playback/download stay in sync with the re-rendered notation.
    """
    midi = pretty_midi.PrettyMIDI(io.BytesIO(data))
    xml = midi_to_musicxml(midi, tempo, time_signature, split_point)
    stats = compute_stats(midi, tempo_bpm=tempo, time_signature=time_signature)
    out_midi = _retempo_midi(midi, tempo) if (tempo and tempo > 0) else midi
    return xml, stats, midi_bytes(out_midi)
