from __future__ import annotations

import hashlib
import wave

from scripts.make_test_files import generate_test_files


def test_fixture_generator_is_deterministic_and_creates_all_required_types(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    manifest_a = generate_test_files(first, seed=77)
    manifest_b = generate_test_files(second, seed=77)

    expected = {"small.txt", "medium.txt", "large.txt", "image.png", "audio.wav"}
    assert set(manifest_a) == expected
    assert manifest_a == manifest_b
    for name in expected:
        assert (first / name).read_bytes() == (second / name).read_bytes()
        assert hashlib.sha256((first / name).read_bytes()).hexdigest() == manifest_a[name]["sha256"]

    assert (first / "image.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with wave.open(str(first / "audio.wav"), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getframerate() == 8000
        assert audio.getnframes() == 8000
