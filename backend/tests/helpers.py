"""Shared synthesis helpers for tests (pure functions, no model needed)."""

from __future__ import annotations

import io

import numpy as np
import soundfile as sf

SR = 22050


def sine(freq: float, seconds: float, sr: int = SR, amp: float = 0.5) -> np.ndarray:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def wav_bytes(samples: np.ndarray, sr: int = SR) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, samples, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def melody_wav() -> bytes:
    """A clear C4–E4–G4–C5 arpeggio basic-pitch can latch onto."""
    freqs = [261.63, 329.63, 392.00, 523.25]
    parts = []
    for f in freqs:
        parts.append(sine(f, 0.6))
        parts.append(np.zeros(int(SR * 0.1), dtype=np.float32))  # gap between notes
    return wav_bytes(np.concatenate(parts))
