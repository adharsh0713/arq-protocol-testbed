"""Generate the project's deterministic text, PNG and WAV transfer fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import struct
import wave
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "test_files"


def _write_text(path: Path, size: int, seed: int) -> None:
    rng = random.Random(seed)
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ,.;:-_()[]\n"
    with path.open("wb") as output:
        remaining = size
        while remaining:
            block_size = min(8192, remaining)
            block = "".join(rng.choice(alphabet) for _ in range(block_size)).encode("ascii")
            output.write(block)
            remaining -= len(block)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack("!I", len(payload))
        + kind
        + payload
        + struct.pack("!I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _write_png(path: Path, width: int = 128, height: int = 96) -> None:
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # PNG filter type: None.
        for x in range(width):
            rows.extend(((x * 3 + y) % 256, (y * 5 + x) % 256, (x ^ y) % 256))
    header = struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0)
    content = b"\x89PNG\r\n\x1a\n"
    content += _png_chunk(b"IHDR", header)
    content += _png_chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
    content += _png_chunk(b"IEND", b"")
    path.write_bytes(content)


def _write_wav(path: Path, duration: float = 1.0, sample_rate: int = 8000) -> None:
    frame_count = int(duration * sample_rate)
    frames = bytearray()
    for index in range(frame_count):
        sample = int(12_000 * math.sin(2 * math.pi * 440 * index / sample_rate))
        frames.extend(struct.pack("<h", sample))
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(bytes(frames))


def generate_test_files(output_dir: str | Path = DEFAULT_OUTPUT, seed: int = 20261113) -> dict[str, dict[str, int | str]]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    _write_text(destination / "small.txt", 8 * 1024, seed)
    _write_text(destination / "medium.txt", 256 * 1024, seed + 1)
    _write_text(destination / "large.txt", 1024 * 1024, seed + 2)
    _write_png(destination / "image.png")
    _write_wav(destination / "audio.wav")

    manifest: dict[str, dict[str, int | str]] = {}
    for path in sorted(destination.iterdir()):
        if path.is_file() and path.name in {
            "small.txt", "medium.txt", "large.txt", "image.png", "audio.wav"
        }:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest[path.name] = {"size_bytes": path.stat().st_size, "sha256": digest}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=20261113)
    args = parser.parse_args()
    manifest = generate_test_files(args.output_dir, args.seed)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
