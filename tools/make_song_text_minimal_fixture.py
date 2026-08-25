#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""
Generate `tests/fixtures/generated/song-text-minimal.skm`.

Pins the lower boundary of the tag-1 song-text section. Only the 8-byte
timing/version trailer is a fixed field; a well-formed section additionally
needs the title's NUL terminator, so the minimum is 9 bytes. This fixture
shrinks an authentic empty-text section to exactly that.

Unlike the other generated fixtures this is not a same-size rewrite: the
tag-1 chunk's declared length is reduced from 20 to 9 and the 11 surplus
body bytes are removed, so the file shrinks by 11. Every other chunk is
copied verbatim and the container still closes exactly, which is the
property that matters.

The trailer is preserved byte-for-byte, so the channel-count and version
cross-checks against sections 2 and the header still hold.

A consumer that reserves a fixed 10-byte footer (the pre-2026-08-25 model)
rejects this file outright; one anchored on the trailer reads it as an
empty title and empty message.
"""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests" / "fixtures" / "authentic" / "empty-skale-081-first.skm"
TARGET = ROOT / "tests" / "fixtures" / "generated" / "song-text-minimal.skm"


def main() -> None:
    raw = SOURCE.read_bytes()
    out = bytearray()
    off = 0
    rebuilt = False
    while off + 8 <= len(raw):
        cid, tag, length = struct.unpack_from("<HHI", raw, off)
        body = raw[off + 8:off + 8 + length]
        off += 8 + length          # advance by the ORIGINAL declared length
        if tag == 1:
            if length != 20 or any(body[:-8]):
                raise SystemExit("unexpected source tag-1 shape")
            body = b"\x00" + body[-8:]          # title terminator + trailer
            rebuilt = True
        out += struct.pack("<HHI", cid, tag, len(body)) + body
        if tag == 0xFFFF:
            break
    if not rebuilt:
        raise SystemExit("no tag-1 chunk rewritten")
    TARGET.write_bytes(bytes(out))
    print(f"wrote {TARGET.relative_to(ROOT)}")
    print(f"  bytes  : {len(out)} (source {len(raw)}, delta {len(out) - len(raw)})")
    print(f"  sha256 : {hashlib.sha256(bytes(out)).hexdigest()}")


if __name__ == "__main__":
    main()
