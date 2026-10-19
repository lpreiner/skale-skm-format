# SPDX-License-Identifier: BSD-2-Clause

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_parser():
    path = ROOT / "reference" / "skmparse.py"
    spec = importlib.util.spec_from_file_location("release_skmparse", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReferenceParserSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parser = load_parser()
        cls.manifest = json.loads(
            (ROOT / "tests" / "fixtures" / "manifest.json").read_text())

    def test_every_nonmalformed_skm_is_fully_consumed(self):
        checked = 0
        for record in self.manifest["files"]:
            if not record["path"].endswith(".skm"):
                continue
            if record.get("expected_parse") == "reject":
                continue
            info = self.parser.parse_skm(ROOT / record["path"])
            self.assertTrue(info["fully_covered"], record["path"])
            checked += 1
        self.assertGreater(checked, 40)

    def parse_fixture(self, name):
        return self.parser.parse_skm(
            ROOT / "tests" / "fixtures" / "authentic" / name)

    def test_vst_effect_causal_probes(self):
        default = self.parse_fixture("vst-fx-default-076.skm")["fx_chain"]["slots"][0]
        param = self.parse_fixture("vst-fx-param-076.skm")["fx_chain"]["slots"][0]
        mixer = self.parse_fixture("vst-fx-mix-076.skm")["fx_chain"]["slots"][0]
        bypassed = self.parse_fixture("vst-fx-disabled-076.skm")["fx_chain"]["slots"][0]

        self.assertEqual(default["slot_index"], 0)
        self.assertEqual(default["bypassed"], 0)
        self.assertEqual(bypassed["bypassed"], 1)
        self.assertAlmostEqual(default["mixer_volume"], 0.8)
        self.assertAlmostEqual(mixer["mixer_volume"], 3.0)
        self.assertEqual(default["params"][:5], param["params"][:5])
        self.assertAlmostEqual(default["params"][5], 0.5)
        self.assertAlmostEqual(param["params"][5], 1.0)

    def test_vsti_causal_probes(self):
        default_info = self.parse_fixture("vsti-default-081.skm")
        note_info = self.parse_fixture("vsti-note-081.skm")
        param_info = self.parse_fixture("vsti-param-081.skm")
        default = default_info["section6"]["entries"][0]
        param = param_info["section6"]["entries"][0]

        self.assertEqual(default_info["header"]["version_raw"], 7600)
        self.assertEqual(default["slot_index"], 0)
        self.assertEqual(default["plugin_param_count"], 24)
        self.assertAlmostEqual(default["plugin_params"][1], 0.37)
        self.assertAlmostEqual(param["plugin_params"][1], 0.0)
        self.assertEqual(
            note_info["patterns"]["patterns"][0]["tracks"][0]["rows"][0],
            {"note": 48, "instrument": 1},
        )


    def test_ogg_padding_is_four_bytes(self):
        """Skale pads Ogg streams with `01 00 FF FF`, and all four must be
        excluded. Leaving `01 00` in place is enough to hang a push-mode
        Vorbis decoder (FORMAT.md, section 3)."""
        import struct

        checked = 0
        for name in ("sample-mono-ogg-081.skm", "sample-mono-ogg-081-resaved.skm"):
            path = ROOT / "tests" / "fixtures" / "authentic" / name
            raw = path.read_bytes()
            info = self.parser.parse_skm(path)
            for record in info["instruments"]["instruments"]:
                for sample in record.get("samples") or []:
                    if sample.get("format_raw") != 4:
                        continue
                    offset = sample["audio_data_offset"]
                    inner = struct.unpack_from("<I", raw, offset)[0]
                    stored = raw[offset + 4:offset + 4 + inner]
                    self.assertEqual(stored[-4:], b"\x01\x00\xff\xff", name)

                    stream = self.parser.extract_ogg_stream(raw, sample)
                    self.assertEqual(stream, stored[:-4], name)
                    self.assertEqual(stream[:4], b"OggS", name)
                    # The returned stream must not end in any of the padding.
                    self.assertNotEqual(stream[-2:], b"\xff\xff", name)
                    self.assertNotEqual(stream[-2:], b"\x01\x00", name)
                    checked += 1
        self.assertGreater(checked, 0)

    def test_ogg_padding_validation_rejects_mutated_padding(self):
        """The negative fixture keeps its container framing but breaks the
        padding, so the container parses and only the stream extraction
        rejects it."""
        import struct

        path = (ROOT / "tests" / "fixtures" / "generated"
                / "ogg-missing-ff-padding.skm")
        raw = path.read_bytes()
        info = self.parser.parse_skm(path)
        self.assertTrue(info["fully_covered"])
        rejected = 0
        for record in info["instruments"]["instruments"]:
            for sample in record.get("samples") or []:
                if sample.get("format_raw") != 4:
                    continue
                with self.assertRaises(ValueError):
                    self.parser.extract_ogg_stream(raw, sample)
                rejected += 1
        self.assertGreater(rejected, 0)


    def test_song_text_short_padding_keeps_whole_message(self):
        """The trailing NUL run before the 8-byte trailer is not a field a
        consumer may reserve. Reserving a fixed 10 bytes truncates the
        message; requiring them to be zero rejects the module outright."""
        import struct

        path = (ROOT / "tests" / "fixtures" / "generated"
                / "song-text-short-padding.skm")
        raw = path.read_bytes()
        info = self.parser.parse_skm(path)

        self.assertTrue(info["fully_covered"])
        song = info["song_text"]
        self.assertEqual(song["title"], "T")
        self.assertEqual(song["message"], "Msg")
        self.assertLess(song["padding_length"], 10)

        # The trailer is the only fixed field, and it must still cross-check.
        self.assertEqual(song["channel_count"], info["patterns"]["channel_count"])
        self.assertEqual(song["version_raw"], info["header"]["version_raw"])

        # Guard the specific regression: slicing a fixed 18 bytes off the end
        # leaves a text region too short to contain the message at all.
        for chunk in info["chunks"]:
            if chunk["tag"] != 1:
                continue
            body = raw[chunk["offset"] + 8:chunk["offset"] + 8 + chunk["length"]]
            self.assertNotIn(b"Msg", body[:-18])
            self.assertIn(b"Msg", body[:-8])
            break


    def test_song_text_minimal_is_the_lower_boundary(self):
        """Only the 8-byte trailer is fixed. A section carrying nothing but a
        title terminator and that trailer is the smallest well-formed one, and
        must parse; reserving a 10-byte footer would reject it."""
        path = (ROOT / "tests" / "fixtures" / "generated"
                / "song-text-minimal.skm")
        info = self.parser.parse_skm(path)
        self.assertTrue(info["fully_covered"])

        tag1 = [c for c in info["chunks"] if c["tag"] == 1]
        self.assertEqual(len(tag1), 1)
        self.assertEqual(tag1[0]["length"], 9)

        song = info["song_text"]
        self.assertEqual(song["title"], "")
        self.assertEqual(song["message"], "")
        # The canonical footer region does not exist at this size, and the
        # parser must say so rather than report a truncated slice.
        self.assertIsNone(song["zero_footer_raw"])
        self.assertFalse(song["canonical_layout"])
        # The one fixed field still cross-checks.
        self.assertEqual(song["channel_count"], info["patterns"]["channel_count"])
        self.assertEqual(song["version_raw"], info["header"]["version_raw"])

    def test_song_text_below_minimum_is_rejected(self):
        """Eight bytes leaves no room for a terminated title."""
        class Chunk:
            data = b"\x00" * 8
        with self.assertRaises(ValueError):
            self.parser.parse_song_text(Chunk())

    def test_sampleless_direct_layout_instruments_locate_id2_tag2_subchunks(self):
        """Pre-0.76 (529B prefix) and compact-0.76 (412B prefix) instruments
        store their 32 parameter/envelope blocks as (id=2, tag=2). When an
        instrument has zero samples, its nested sub-chunk list starts directly
        with (id=2, tag=2) and must still be located."""
        for name, version_raw, expected_prefix in (
            ("keymap-two-sample-075.skm", 7500, 529),
            ("keymap-two-sample-076.skm", 7600, 412),
        ):
            raw = (ROOT / "tests" / "fixtures" / "authentic" / name).read_bytes()
            sec3 = next(c for c in self.parser.read_chunks(raw)[0] if c.tag == 3)
            rec = self.parser.read_chunks(sec3.data)[0][0]
            _, name_end = self.parser.cstring(rec.data, 1)
            list_off = self.parser.locate_sample_list(rec.data, name_end)
            self.assertEqual(list_off - name_end, expected_prefix, name)
            sub_chunks, _ = self.parser.read_chunks(rec.data[list_off:])
            non_sample = b"".join(
                self.parser.HDR.pack(sc.id, sc.tag, len(sc.data)) + sc.data
                for sc in sub_chunks
                if not (sc.id == 1 and sc.tag == 1)
            )
            sampleless_rec = rec.data[:list_off] + non_sample
            sec3_body = (
                self.parser.HDR.pack(rec.id, rec.tag, len(sampleless_rec))
                + sampleless_rec
                + self.parser.HDR.pack(1, self.parser.TAG_EOF, 0)
            )
            parsed = self.parser.parse_instruments(
                self.parser.Chunk(0, 1, 3, len(sec3_body), sec3_body),
                version_raw=version_raw,
            )["instruments"][0]
            self.assertTrue(parsed["internals_located"], name)
            self.assertEqual(parsed["keymap_layout"], "direct-96-byte", name)
            self.assertEqual(len(parsed["samples"]), 0, name)
            self.assertEqual(
                len(parsed["envelopes"]) + parsed["other_subchunks"], 32, name
            )

    def make_instrument(self, record_version, mapped=128):
        import struct
        p = self.parser
        if record_version in (3, 4):
            keymap = bytes(range(128))
        else:
            keymap = b"".join(
                bytes((1, 1, i, 0, 127, 0)) if i < mapped else b"\0\0"
                for i in range(128))
        settings = bytearray({3: 401, 4: 284, 5: 284, 6: 288}[record_version])
        struct.pack_into("<H", settings, 0, 4321)
        settings[7:9] = b"\1\1"
        struct.pack_into("<ff", settings, 9, 1.25, -0.25)
        if record_version != 3:
            settings[253:257] = b"\1\0\1\0"
            for offset, freq in ((257, 32), (266, 2540), (275, 13500)):
                struct.pack_into("<Bff", settings, offset, 1, 0.5, freq)
        if record_version == 6:
            settings[284:288] = bytes((12, 34, 56, 0))
        data = b"\1test\0" + keymap + settings + p.HDR.pack(1, p.TAG_EOF, 0)
        body = p.HDR.pack(record_version, 1, len(data)) + data + p.HDR.pack(1, p.TAG_EOF, 0)
        return p.Chunk(0, 1, 3, len(body), body)

    def test_versioned_prefixes_and_variable_keymaps(self):
        for version, mapped, length in (
            (3, 128, 529), (4, 128, 412), (5, 127, 1048), (5, 128, 1052),
            (6, 0, 544), (6, 43, 716), (6, 60, 784), (6, 96, 928), (6, 128, 1056),
        ):
            with self.subTest(version=version, mapped=mapped):
                entry = self.parser.parse_instruments(
                    self.make_instrument(version, mapped), version_raw=7600
                )["instruments"][0]
                self.assertEqual(entry["prefix_length"], length)
                self.assertEqual(len(entry["keymap_all_slots"]), 128)
                self.assertEqual(entry["keymap"], [i if i < mapped else 0 for i in range(96)])
                self.assertEqual(entry["fadeout"], 4321)
                self.assertEqual(entry["note_death"], "note-off")
                if version == 3:
                    self.assertIsNone(entry["mixer_strip"])
                else:
                    mixer = entry["mixer_strip"]
                    self.assertEqual(mixer["volume_fader"], 1.25)
                    self.assertEqual(mixer["bal"], -0.25)
                    self.assertEqual(mixer["sub_assign"], [1, 0, 1, 0])
                    self.assertEqual([mixer[k]["freq"] for k in ("eq_l", "eq_m", "eq_h")],
                                     [32, 2540, 13500])
                    if version == 6:
                        self.assertEqual(mixer["color_bgr"], [12, 34, 56])

    def test_empty_id2_envelope_has_no_reserved_trailer(self):
        p = self.parser
        data = bytes((0, 1, 0, 0, 0, 0, 0, 0, 0))
        envelope = p.parse_instrument_envelope(p.Chunk(0, 2, 2, len(data), data))
        self.assertEqual(envelope["type"], "volume")
        self.assertEqual(envelope["points"], [])
        self.assertFalse(envelope["enabled"])

    def test_nonboolean_companion_is_preserved(self):
        p = self.parser
        chunk = self.make_instrument(5)
        body = bytearray(chunk.data)
        body[8 + 6 + 768 + 152] = 12
        entry = p.parse_instruments(p.Chunk(0, 1, 3, len(body), bytes(body)), 7600)["instruments"][0]
        self.assertEqual(entry["mixer_strip"]["toggle01_companion"], 12)

    def test_bad_known_keymap_is_rejected_without_scanning(self):
        p = self.parser
        chunk = self.make_instrument(6)
        body = bytearray(chunk.data)
        body[8 + 6] = 2  # invalid first framed entry marker
        with self.assertRaises(ValueError):
            p.parse_instruments(p.Chunk(0, 1, 3, len(body), bytes(body)), 7600)

    def test_audio_payload_boundaries_on_public_fixtures(self):
        p = self.parser
        checked = 0
        for record in self.manifest["files"]:
            if (not record["path"].endswith(".skm")
                    or record.get("classification") == "malformed"
                    or record.get("expected_parse") == "reject"):
                continue
            path = ROOT / record["path"]
            raw = path.read_bytes()
            info = p.parse_skm(path)
            for inst in info.get("instruments", {}).get("instruments", []):
                for sample in inst.get("samples", []):
                    if not sample.get("audio_located"):
                        continue
                    offset = sample["audio_data_offset"]
                    end = offset + sample["audio_payload_length"]
                    self.assertEqual(sample["audio_chunk_length"], sample["audio_payload_length"] + 5)
                    # Malformed EOF fixtures deliberately remain inspectable.
                    self.assertEqual(sample["audio_eof_valid"],
                                     raw[end:end + 8] == p.HDR.pack(1, p.TAG_EOF, 0))
                    if sample["format_raw"] in (2, 3):
                        self.assertEqual(len(p.extract_pcm_samples(raw, sample)),
                                         sample["stored_value_count"])
                    checked += 1
        self.assertGreater(checked, 10)

    def test_pattern_section_is_a_chunk_list_with_u16_rows(self):
        p = self.parser
        checked = 0
        for record in self.manifest["files"]:
            if (not record["path"].endswith(".skm")
                    or record.get("classification") == "malformed"
                    or record.get("expected_parse") == "reject"):
                continue
            patterns = p.parse_skm(ROOT / record["path"])["patterns"]
            # Pattern chunks, track mini-chunks, and the closing EOF chunk
            # account for every byte after the order list.
            self.assertTrue(patterns["walk_clean"], record["path"])
            self.assertTrue(patterns["all_tracks_clean"], record["path"])
            self.assertEqual(patterns["trailing_bytes"], 0, record["path"])
            checked += 1
        self.assertGreater(checked, 10)
        path = ROOT / "tests" / "fixtures" / "generated" / "empty-pattern-256-rows.skm"
        raw = path.read_bytes()
        info = p.parse_skm(path)
        [pattern] = info["patterns"]["patterns"]
        self.assertEqual(pattern["rows"], 256)
        section = next(c for c in p.read_chunks(raw)[0] if c.tag == 2)
        body = section.offset + p.HDR.size + pattern["offset"] + p.HDR.size
        self.assertEqual(raw[body + 1:body + 3], b"\x00\x01")

    def test_framed_keymap_distinguishes_unmapped_from_slot_zero(self):
        p = self.parser
        entry = p.parse_instruments(self.make_instrument(6, 43), 7600)["instruments"][0]
        self.assertEqual(entry["keymap_mapped"], [True] * 43 + [False] * 85)
        # Note 0 is an explicit mapping to local slot 0, unlike notes 43+.
        self.assertEqual(entry["keymap_all_slots"][0], 0)
        self.assertNotIn("keymap_nonstandard_entries", entry)
        direct = p.parse_instruments(self.make_instrument(4), 7600)["instruments"][0]
        self.assertNotIn("keymap_mapped", direct)

    def test_send_knob_records_by_record_version(self):
        import struct
        p = self.parser
        for version, first, stride in ((3, 139, 13), (5, 156, 6), (6, 156, 6)):
            with self.subTest(version=version):
                chunk = self.make_instrument(version)
                body = bytearray(chunk.data)
                keymap = 128 if version in (3, 4) else 768
                base = 8 + 6 + keymap  # record header + index/name
                struct.pack_into("<Bf", body, base + first + stride, 1, 1.5)
                entry = p.parse_instruments(
                    p.Chunk(0, 1, 3, len(body), bytes(body)), 7600)["instruments"][0]
                knobs = entry["settings"]["send_knobs"]
                self.assertEqual(len(knobs), 16)
                self.assertEqual((knobs[1]["flag"], knobs[1]["value"]), (1, 1.5))


if __name__ == "__main__":
    unittest.main()
