#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""
Generate `tests/fixtures/generated/song-text-short-padding.skm`.

A deterministic, same-size in-place rewrite of an authentic empty-text
fixture. Only the tag-1 (song text) chunk body changes; every other byte,
and the file's total size, is identical to the source.

Purpose: pin two regressions in consumers.

  1. Reserving a fixed 10-byte zero footer truncates the message of any
     file whose trailing NUL run is shorter. Both reference parsers used
     to slice a fixed 18 bytes off the end and silently lost text.
  2. Requiring those 10 bytes to be zero makes a consumer reject the whole
     module over song text alone. The experimental OpenMPT loader did, and
     two corpus files became unloadable.

The source's tag-1 body is 20 bytes: 12 NULs then the 8-byte trailer. The
rewrite spends 6 of those NULs on `T\\0Msg\\0`, leaving a 6-byte run. The
trailer is preserved byte-for-byte, so timing/channel/version cross-checks
still pass and the container still closes exactly.

This file is a consumer probe. It is NOT evidence that Skale emits a short
padding run; the run is fixed-width in Skale's own output (FORMAT.md).
"""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests" / "fixtures" / "authentic" / "empty-skale-081-first.skm"
TARGET = ROOT / "tests" / "fixtures" / "generated" / "song-text-short-padding.skm"
NEW_TEXT = b"T\x00Msg\x00"


def find_tag1(raw: bytes) -> tuple[int, int]:
    """Return (body_offset, body_length) of the top-level tag-1 chunk."""
    off = 0
    while off + 8 <= len(raw):
        _id, tag, length = struct.unpack_from("<HHI", raw, off)
        if tag == 1:
            return off + 8, length
        if tag == 0xFFFF:
            break
        off += 8 + length
    raise SystemExit("no tag-1 chunk found")


def main() -> None:
    raw = bytearray(SOURCE.read_bytes())
    body_off, body_len = find_tag1(raw)
    if body_len != 20:
        raise SystemExit(f"expected a 20-byte tag-1 body, got {body_len}")

    body = raw[body_off:body_off + body_len]
    trailer = body[-8:]
    if any(body[:-8]):
        raise SystemExit("source tag-1 text region is not all NUL; pick another source")

    new_body = NEW_TEXT + bytes(body_len - 8 - len(NEW_TEXT)) + trailer
    assert len(new_body) == body_len
    raw[body_off:body_off + body_len] = new_body

    TARGET.write_bytes(bytes(raw))
    print(f"wrote {TARGET.relative_to(ROOT)}")
    print(f"  bytes  : {len(raw)} (source: {SOURCE.stat().st_size})")
    print(f"  sha256 : {hashlib.sha256(bytes(raw)).hexdigest()}")
    run = len(new_body[:-8]) - len(bytes(new_body[:-8]).rstrip(b'\x00'))
    print(f"  NUL run before trailer: {run}")


if __name__ == "__main__":
    main()
