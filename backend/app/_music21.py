"""Lazy music21 imports to avoid startup cost.

music21 is a heavy package (~10 MB). Importing it at module level would slow
app startup for every request. Instead, we import it lazily on first use and
re-export the symbols we need.
"""

from __future__ import annotations

# Module-level cache so music21 is only imported once.
_m21_cache: dict[str, object] | None = None


def _ensure():
    global _m21_cache
    if _m21_cache is None:
        from music21 import (  # noqa: F401
            chord,
            clef,
            converter,
            instrument,
            layout,
            meter,
            note,
            stream,
            tempo,
        )

        _m21_cache = {
            "chord": chord,
            "clef": clef,
            "converter": converter,
            "instrument": instrument,
            "layout": layout,
            "meter": meter,
            "note": note,
            "stream": stream,
            "tempo": tempo,
        }


def __getattr__(name: str):
    _ensure()
    return _m21_cache[name]  # type: ignore[literal-required]
