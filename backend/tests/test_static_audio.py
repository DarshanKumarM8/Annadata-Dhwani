"""Exotel checks a prompt URL with HEAD before playing it: the audio route must answer HEAD like GET."""
import wave

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)                     # no lifespan: these routes need no database


def test_head_on_the_fallback_beep_is_200_with_wav_headers():
    r = client.head("/audio/mix/sample.wav")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/")
    assert int(r.headers["content-length"]) > 0
    assert r.content == b""                  # HEAD never has a body


def test_head_on_a_mixed_prompt_and_get_agree(tmp_path):
    mix = settings.audio_dir / "mix"
    mix.mkdir(parents=True, exist_ok=True)
    f = mix / "unit-test-prompt.wav"
    with wave.open(str(f), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 8000)
    try:
        h, g = client.head("/audio/mix/unit-test-prompt.wav"), client.get("/audio/mix/unit-test-prompt.wav")
        assert h.status_code == g.status_code == 200
        assert h.headers["content-length"] == g.headers["content-length"] == str(len(g.content))
        assert h.headers["content-type"].startswith("audio/")
        part = client.get("/audio/mix/unit-test-prompt.wav", headers={"Range": "bytes=0-99"})
        assert part.status_code == 206 and len(part.content) == 100     # players may ask for ranges
    finally:
        f.unlink(missing_ok=True)


def test_media_route_answers_head_and_path_tricks_fall_back_safely():
    assert client.head("/media/v/anything.jpg").status_code == 200
    r = client.get("/audio/mix/..%2f..%2f.env")
    assert r.status_code in (200, 404) and b"JWT_SECRET" not in r.content
