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


if __name__ == "__main__":
    unittest.main()
