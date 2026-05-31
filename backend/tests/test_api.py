"""HTTP API tests via FastAPI's TestClient.

These exercise the endpoints end-to-end (routing, validation, serialization).
The module-scoped client runs the app lifespan once (warming the model, which is
then shared with the session-scoped ``melody_midi`` fixture).
"""
from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from app import notation
from app.main import app
from tests.helpers import melody_wav


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "model_loaded" in body and "ffmpeg_available" in body


def test_transcribe_happy_path(client):
    r = client.post(
        "/api/transcribe",
        files={"file": ("melody.wav", melody_wav(), "audio/wav")},
        data={"tempo": "90", "time_signature": "3/4"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stats"]["time_signature"] == "3/4"
    assert body["stats"]["tempo_bpm"] == 90.0
    assert body["stats"]["note_count"] >= 1
    assert body["midiBase64"]
    xml = body["musicXml"]
    assert "<staves>2</staves>" in xml or "<staff>2</staff>" in xml  # grand staff


def test_transcribe_empty_upload(client):
    r = client.post("/api/transcribe", files={"file": ("empty.wav", b"", "audio/wav")})
    assert r.status_code == 400


def test_transcribe_bad_time_signature(client):
    r = client.post(
        "/api/transcribe",
        files={"file": ("melody.wav", melody_wav(), "audio/wav")},
        data={"time_signature": "foo"},
    )
    assert r.status_code == 400


def test_transcribe_nonpositive_tempo(client):
    r = client.post(
        "/api/transcribe",
        files={"file": ("melody.wav", melody_wav(), "audio/wav")},
        data={"tempo": "-5"},
    )
    assert r.status_code == 400


def test_transcribe_oversized(client, monkeypatch):
    monkeypatch.setattr("app.main.MAX_UPLOAD_BYTES", 16)
    r = client.post(
        "/api/transcribe",
        files={"file": ("big.wav", b"x" * 64, "audio/wav")},
    )
    assert r.status_code == 413


def test_renotate_round_trip(client, melody_midi):
    midi_b64 = base64.b64encode(notation.midi_bytes(melody_midi)).decode("ascii")
    r = client.post(
        "/api/renotate",
        json={"midiBase64": midi_b64, "tempo": 180, "timeSignature": "4/4"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stats"]["tempo_bpm"] == 180.0
    assert body["stats"]["time_signature"] == "4/4"
    assert body["midiBase64"]  # re-timed MIDI returned for in-sync playback


def test_renotate_bad_base64(client):
    r = client.post(
        "/api/renotate",
        json={"midiBase64": "!!!not-base64!!!", "tempo": 120, "timeSignature": "4/4"},
    )
    assert r.status_code == 400


def test_renotate_bad_split_point(client):
    r = client.post(
        "/api/renotate",
        json={"midiBase64": "AAA=", "tempo": 120, "timeSignature": "4/4", "splitPoint": 999},
    )
    assert r.status_code == 422  # pydantic bounds (ge=0, le=127)


def test_renotate_bad_time_signature(client):
    r = client.post(
        "/api/renotate",
        json={"midiBase64": "AAA=", "tempo": 120, "timeSignature": "nope"},
    )
    assert r.status_code == 422  # pydantic pattern on RenotateRequest
