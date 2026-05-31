"""Make the ``app`` package importable and host shared fixtures.

The basic-pitch model load + inference is slow, so the transcribed MIDI is
produced once here (session-scoped) and reused across the test modules.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from app import audio, transcription  # noqa: E402
from tests.helpers import melody_wav  # noqa: E402


@pytest.fixture(scope="session")
def melody_midi():
    """Transcribe the arpeggio once; reused across notation tests."""
    path = audio.write_normalized_wav(melody_wav(), "melody.wav")
    return transcription.transcribe_wav(path)
