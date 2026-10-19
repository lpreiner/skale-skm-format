#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Independently check versioned instrument boundaries and optional Kaitai output.

Usage: python tools/check_instrument_layouts.py PATH... [--generated-dir DIR]
Generate skm.py with Kaitai 0.11 and install kaitaistruct to enable comparison.
All supplied files must have valid container framing; exclude deliberate
container-truncation fixtures. Invalid terminal audio header values are counted
separately, allowing payload-negative fixtures to remain inspectable.
"""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
from pathlib import Path
import struct
import sys


def check_file(path, parser, generated, counts):
    raw = path.read_bytes()
    ref = parser.parse_skm(path)
    chunks, consumed = parser.read_chunks(raw)
    assert consumed == len(raw), "outer container slack"
    sec = next((c for c in chunks if c.tag == 3), None)
    counts["files"] += 1
    if sec is None:
        return
    records = [r for r in parser.read_chunks(sec.data)[0] if r.tag != 65535]
    refs = ref["instruments"]["instruments"]
    assert len(records) == len(refs)
    ks_records = None
    if generated:
        ks = generated.from_bytes(raw)
        ks_section = next(c.body for c in ks.chunks if c.tag == 3)
        ks_records = [c.body for c in ks_section.instruments if c.tag != 65535]
        assert len(ks_records) == len(records)
    for idx, (rec, entry) in enumerate(zip(records, refs)):
        _, name_end = parser.cstring(rec.data, 1)
        pos = name_end
        slots = []
        if rec.id in (3, 4):
            slots = list(rec.data[pos:pos + 128])
            assert len(slots) == 128
            pos += 128
        else:
            assert rec.id in (5, 6), f"unsupported record ID {rec.id}"
            for _ in range(128):
                marker = rec.data[pos:pos + 2]
                if marker == b"\0\0":
                    slots.append(0)
                    pos += 2
                else:
                    assert marker == b"\1\1"
                    assert rec.data[pos + 3:pos + 6] == b"\0\x7f\0"
                    slots.append(rec.data[pos + 2])
                    pos += 6
        start = pos + {3: 401, 4: 284, 5: 284, 6: 288}[rec.id]
        # The older scanning algorithm provides a separate boundary cross-check.
        assert parser.locate_sample_list(rec.data, name_end, len(rec.data)) == start
        assert entry["internals_located"] and entry["prefix_source"] == "record-version"
        assert entry["keymap_all_slots"] == slots
        assert entry["prefix_length"] == start - name_end
        assert entry["fadeout"] == struct.unpack_from("<H", rec.data, pos)[0]
        sub, used = parser.read_chunks(rec.data[start:])
        assert used == len(rec.data) - start and sub[-1].tag == 65535
        counts["instruments"] += 1
        counts[f"record_{rec.id}_prefix_{start - name_end}"] += 1
        ks_inst = ks_records[idx] if ks_records is not None else None
        if ks_inst:
            ks_slots = (list(ks_inst.direct_keymap) if rec.id in (3, 4) else
                        [e.local_slot if e.mapped else 0 for e in ks_inst.framed_keymap])
            assert ks_slots == slots
            assert ks_inst.settings.fadeout == entry["fadeout"]
            assert ks_inst.settings.note_death == entry["note_death_raw"]
            assert ks_inst._io.is_eof() and ks_inst.settings._io.is_eof()
            if entry.get("mixer_strip"):
                strip = entry["mixer_strip"]
                assert ks_inst.settings.volume_fader == strip["volume_fader"]
                assert ks_inst.settings.bal == strip["bal"]
                assert list(ks_inst.settings.sub_assign) == strip["sub_assign"]
                for band, name in zip(ks_inst.settings.eq, ("eq_l", "eq_m", "eq_h")):
                    assert (band.enabled_flag, band.gain, band.freq) == tuple(
                        strip[name][key] for key in ("enabled_flag", "gain", "freq"))
        samples = [s for s in sub if s.id == 1 and s.tag == 1]
        assert len(samples) == len(entry["samples"])
        ks_samples = ([s.body for s in ks_inst.nested.entries if s.id == 1 and s.tag == 1]
                      if ks_inst else [None] * len(samples))
        assert len(ks_samples) == len(samples)
        for sample, parsed, ks_sample in zip(samples, entry["samples"], ks_samples):
            _, n = parser.cstring(sample.data, 1)
            at = n + 14
            cid, tag, length = parser.HDR.unpack_from(sample.data, at)
            counts["sample_slots"] += 1
            if length == 0:
                assert (cid, tag) == (1, 65535) and at + 8 == len(sample.data)
                assert parsed["empty_slot"] and not parsed["audio_located"]
                if ks_sample:
                    assert len(ks_sample.audio_chunks) == 1 and ks_sample._io.is_eof()
                continue
            assert cid in (2, 3, 4) and tag == 1 and length >= 5
            end = at + 8 + length
            assert end + 8 == len(sample.data), "audio chunk slack/overrun"
            eof_valid = sample.data[end:] == parser.HDR.pack(1, 65535, 0)
            counts["invalid_audio_eof"] += not eof_valid
            values, channels = struct.unpack_from("<IB", sample.data, at + 8)
            payload = sample.data[at + 13:end]
            assert parsed["audio_eof_valid"] == eof_valid
            assert parsed["audio_payload_length"] == len(payload)
            assert parsed["audio_chunk_length"] == length
            absolute = parsed["audio_data_offset"]
            assert raw[absolute:absolute + len(payload)] == payload
            if cid in (2, 3):
                assert len(payload) == values * {2: 2, 3: 1}[cid]
                pcm = parser.extract_pcm_samples(raw, parsed)
                if sys.byteorder == "big" and cid == 2:
                    pcm.byteswap()
                assert pcm.tobytes() == payload
            else:
                valid_ogg = (eof_valid and len(payload) >= 4
                             and struct.unpack_from("<I", payload)[0] == len(payload)
                             and payload[4:8] == b"OggS")
                counts["invalid_ogg_payload"] += not valid_ogg
                if valid_ogg:
                    assert parser.extract_ogg_stream(raw, parsed) == payload[4:]
                else:
                    try:
                        parser.extract_ogg_stream(raw, parsed)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("invalid Ogg payload accepted")
            if ks_sample:
                meta = ks_sample.metadata
                for key in ("volume", "panning", "finetune", "relative_note", "unknown_a",
                            "loop_start", "loop_end"):
                    assert getattr(meta, key) == parsed[key]
                assert ks_sample._io.is_eof() and len(ks_sample.audio_chunks) == 2
                audio, terminal = ks_sample.audio_chunks
                assert (audio.format, audio.tag, audio.length) == (cid, tag, length)
                assert (audio.body.stored_value_count, audio.body.channels) == (values, channels)
                assert audio.body.payload == payload and terminal.length == 0
                if cid == 4:
                    assert audio.body.ogg.stream == payload[4:]
            counts["populated_samples"] += 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--generated-dir", type=Path)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    parser_path = root / "skmparse.py"
    if not parser_path.is_file():
        parser_path = root / "reference/skmparse.py"
    spec = importlib.util.spec_from_file_location("layout_reference", parser_path)
    parser = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = parser
    spec.loader.exec_module(parser)
    generated = None
    if args.generated_dir:
        sys.path.insert(0, str(args.generated_dir.resolve()))
        from skm import Skm
        generated = Skm
    files = sorted({f for path in args.paths for f in
                    (path.rglob("*.skm") if path.is_dir() else [path])})
    counts = Counter()
    failures = []
    for path in files:
        current = Counter()
        try:
            check_file(path, parser, generated, current)
            counts.update(current)
        except Exception as exc:
            failures.append((path, str(exc) or type(exc).__name__))
    for name, value in sorted(counts.items()):
        print(f"{name}: {value}")
    for path, error in failures:
        print(f"FAIL {path}: {error}")
    print(f"failed_files: {len(failures)}")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
