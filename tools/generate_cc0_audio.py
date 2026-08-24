#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Generate deterministic CC0 audio inputs for the public SKM corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import wave
from dataclasses import dataclass
from pathlib import Path


SAMPLE_RATE = 44_100
LONG_FRAMES = 44_100
SHORT_FRAMES = 4_096


@dataclass(frozen=True)
class Profile:
    channels: int
    frames: int
    purpose: str


PROFILES = {
    "mono-pcm8": Profile(1, LONG_FRAMES, "PCM8-exact import source"),
    "mono-pcm16": Profile(1, LONG_FRAMES, "PCM16 low-byte-detail import source"),
    "stereo-pcm8": Profile(2, SHORT_FRAMES, "distinguishable PCM8-exact stereo source"),
    "stereo-pcm16": Profile(2, SHORT_FRAMES, "distinguishable stereo interleaving source"),
    "keymap-low": Profile(1, SHORT_FRAMES, "lower keyboard range source"),
    "keymap-high": Profile(1, SHORT_FRAMES, "upper keyboard range source"),
}


def triangle(frame: int, period: int, amplitude: int) -> int:
    phase = frame % period
    half = period // 2
    if phase < half:
        return -amplitude + (2 * amplitude * phase) // half
    return amplitude - (2 * amplitude * (phase - half)) // half


def sample(profile: str, frame: int, channel: int) -> int:
    if profile == "mono-pcm8":
        # Byte-exact with the original public-test generator.
        return triangle(frame, 128, 8_192)
    if profile == "mono-pcm16":
        phase = frame % 128
        return triangle(frame, 128, 8_192) + ((phase * 73) % 255) - 127
    if profile == "stereo-pcm8":
        # Keep every value exactly representable as signed PCM8 while making
        # channel swaps, duplication, and interleaving errors visible.
        if channel == 0:
            return 256 * triangle(frame, 128, 70)
        return -256 * triangle(frame, 96, 45)
    if profile == "stereo-pcm16":
        if channel == 0:
            return triangle(frame, 128, 7_000) + ((frame * 29) % 97) - 48
        # A different period, polarity, amplitude, and low-byte sequence makes
        # channel swaps/duplication/interleaving mistakes obvious.
        return -triangle(frame, 96, 11_000) + ((frame * 61) % 193) - 96
    if profile == "keymap-low":
        return triangle(frame, 128, 6_000) + ((frame * 17) % 127) - 63
    if profile == "keymap-high":
        return triangle(frame, 80, 10_000) + ((frame * 47) % 251) - 125
    raise ValueError(f"unknown profile: {profile}")


def generate(profile_name: str, output: Path) -> dict[str, object]:
    profile = PROFILES[profile_name]
    output.parent.mkdir(parents=True, exist_ok=True)
    pcm = bytearray()
    for frame in range(profile.frames):
        for channel in range(profile.channels):
            pcm.extend(struct.pack("<h", sample(profile_name, frame, channel)))
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(profile.channels)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
    raw = output.read_bytes()
    return {
        "profile": profile_name,
        "filename": output.name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "sample_rate": SAMPLE_RATE,
        "channels": profile.channels,
        "sample_width_bits": 16,
        "frames": profile.frames,
        "purpose": profile.purpose,
        "license": "CC0-1.0",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        help="write generated metadata to this JSON file",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        action="append",
        help="generate only this profile; repeatable (default: all)",
    )
    args = parser.parse_args()

    selected = args.profile or list(PROFILES)
    records = []
    for name in selected:
        record = generate(name, args.output_dir / f"cc0-{name}.wav")
        records.append(record)
        print(f"{record['sha256']}  {args.output_dir / record['filename']}")
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps({"schema_version": 1, "assets": records}, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
