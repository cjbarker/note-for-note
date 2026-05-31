"""Audio decoding utilities.

Hybrid decode strategy:
- WAV is decoded dependency-free via ``soundfile`` (the fast path).
- Any other format (mp3/m4a/webm/ogg/flac...) is decoded via ``librosa``, which
  uses ``audioread``/ffmpeg under the hood. ffmpeg is a system dependency.

Everything is normalized to mono float32 at a target sample rate (22050 Hz,
which is what basic-pitch expects) and written to a temporary WAV that the
transcription step can hand directly to basic-pitch.
"""

from __future__ import annotations

import io
import os
import tempfile

import numpy as np
import soundfile as sf

# basic-pitch resamples to 22050 Hz internally; matching it here avoids a
# second resample and keeps the pipeline predictable.
TARGET_SR = 22050

WAV_EXTENSIONS = {".wav", ".wave"}


class AudioDecodeError(RuntimeError):
    """Raised when the input audio cannot be decoded."""


class InputError(ValueError):
    """Raised when decoded audio violates an input constraint (e.g. too long)."""


def _safe_unlink(path: str) -> None:
    """Best-effort delete of a temp file; ignore if already gone."""
    try:
        os.unlink(path)
    except OSError:
        pass


def _to_mono(samples: np.ndarray) -> np.ndarray:
    """Downmix an (n,) or (n, channels) array to mono float32."""
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim == 2:
        samples = samples.mean(axis=1)
    return samples


def _decode_wav(data: bytes) -> tuple[np.ndarray, int]:
    """Decode WAV audio via soundfile (dependency-free fast path)."""
    try:
        samples, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
        return _to_mono(samples), int(sr)
    except Exception as exc:  # noqa: BLE001 - surface a clean error
        raise AudioDecodeError(f"Failed to read WAV: {exc}") from exc


def _decode_soundfile(data: bytes) -> tuple[np.ndarray, int]:
    """Decode FLAC/OGG via soundfile (works without ffmpeg for these formats)."""
    try:
        samples, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
        return _to_mono(samples), int(sr)
    except Exception:
        return None  # type: ignore[return-value]


def _decode_librosa(data: bytes, ext: str) -> tuple[np.ndarray, int]:
    """Decode compressed audio via librosa -> audioread -> ffmpeg."""
    try:
        import librosa  # imported lazily; heavy import
    except Exception as exc:  # noqa: BLE001
        raise AudioDecodeError(
            "librosa is required to decode non-WAV audio but is unavailable"
        ) from exc

    # librosa needs a file path for the audioread/ffmpeg backend, so spill to a temp file.
    with tempfile.NamedTemporaryFile(suffix=ext or ".bin", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        samples, sr = librosa.load(tmp_path, sr=None, mono=True)
        return np.asarray(samples, dtype=np.float32), int(sr)
    except Exception as exc:  # noqa: BLE001
        raise AudioDecodeError(
            "Could not decode audio. For non-WAV formats, ffmpeg must be installed "
            f"on the server. Underlying error: {exc}"
        ) from exc
    finally:
        _safe_unlink(tmp_path)


def load_audio(data: bytes, filename: str | None = None) -> tuple[np.ndarray, int]:
    """Decode raw audio ``bytes`` to (mono float32 samples, sample_rate).

    Tries the dependency-free WAV path first, then falls back to librosa/ffmpeg
    for compressed formats. Raises :class:`AudioDecodeError` on failure.
    """
    ext = os.path.splitext(filename or "")[1].lower()

    # Fast path: WAV via soundfile (no ffmpeg required).
    if ext in WAV_EXTENSIONS:
        return _decode_wav(data)

    # soundfile can also handle FLAC/OGG without ffmpeg; try it opportunistically.
    if (result := _decode_soundfile(data)) is not None:
        return result

    # Fallback: librosa -> audioread -> ffmpeg for everything else (mp3, m4a, webm...).
    return _decode_librosa(data, ext)


def _normalize(data: bytes, filename: str | None) -> tuple[np.ndarray, int]:
    """Decode to mono and resample to ``TARGET_SR``; raise if empty."""
    samples, sr = load_audio(data, filename)

    if sr != TARGET_SR:
        try:
            import librosa

            samples = librosa.resample(samples, orig_sr=sr, target_sr=TARGET_SR)
        except Exception as exc:  # noqa: BLE001
            raise AudioDecodeError(f"Failed to resample audio: {exc}") from exc
        sr = TARGET_SR

    if samples.size == 0:
        raise AudioDecodeError("Decoded audio is empty.")
    return samples, sr


def _write_wav(samples: np.ndarray, sr: int) -> str:
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(path, samples, sr, subtype="PCM_16")
    return path


def write_normalized_wav(data: bytes, filename: str | None = None) -> str:
    """Decode ``data`` and write a mono ``TARGET_SR`` WAV to a temp file.

    Returns the path to the temporary WAV. Caller is responsible for deleting it.
    """
    samples, sr = _normalize(data, filename)
    return _write_wav(samples, sr)


def decode_and_wav(data: bytes, filename: str | None = None) -> tuple[str, np.ndarray, int]:
    """Like :func:`write_normalized_wav` but also returns the decoded samples.

    Lets callers reuse the samples (e.g. for tempo estimation) without decoding
    the input twice. Caller is responsible for deleting the returned WAV path.
    """
    samples, sr = _normalize(data, filename)
    return _write_wav(samples, sr), samples, sr


def estimate_tempo(samples: np.ndarray, sr: int) -> float:
    """Estimate tempo (BPM) from a mono signal via librosa beat tracking.

    Returns a sensible default (120) if estimation is not possible (e.g. too few
    onsets in a short clip).
    """
    try:
        import librosa

        tempo, _beats = librosa.beat.beat_track(y=samples, sr=sr)
        bpm = float(np.atleast_1d(tempo)[0])
        if not np.isfinite(bpm) or bpm <= 0:
            return 120.0
        return round(bpm, 1)
    except Exception:  # noqa: BLE001 - tempo is a best-effort hint
        return 120.0


def duration_seconds(samples: np.ndarray, sr: int) -> float:
    return float(len(samples)) / float(sr) if sr else 0.0
