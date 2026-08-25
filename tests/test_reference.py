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


if __name__ == "__main__":
    unittest.main()
