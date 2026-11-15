<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# skale-skm-format

A description of the `.skm` module format written by Skale Tracker, with a
reference parser in Python, a Kaitai Struct schema, and a small test corpus
that is safe to redistribute.

Canonical repository: <https://github.com/lpreiner/skale-skm-format>

## How the format was worked out

Everything here comes from the files Skale writes. Most claims rest on
controlled saves: change one setting in Skale, save, and diff against the
previous file. Comparing the SKM file with Skale's XM export of the same song
helps identify fields shared by both formats. The Skale executables were run
as applications only. They were not disassembled, decompiled, or debugged, and
they are not distributed here.

A private collection of third-party songs was used to check that layouts hold
across real-world files. Those songs are not distributed. Where a claim rests
only on them, `PROVENANCE.md` says so.

## Status

| Part | Status |
|---|---|
| Chunk container, file header | Verified |
| Section 1: title, message, initial BPM/speed/channels | Verified; non-ASCII encoding open |
| Section 2: order list, patterns, event encoding | Layout verified; stored parameters for effects `10`–`13` and volume-column values other than plain volume or no volume remain unconfirmed |
| Section 3: instruments, keymaps, envelopes, samples (PCM8/PCM16/Ogg) | Layout verified for all observed record versions; some settings fields unnamed |
| Section 4: VST effect chain | Layout verified; plugin parameters are plugin-specific |
| Section 5: master volume, sub-buses, FX-bus sends | Verified for the 0.76 layout |
| Section 6: VSTi synths | Layout verified; plugin parameters are plugin-specific |

The parser's interfaces are not yet stable. A file that parses cleanly may
still contain fields whose meaning is unknown.

Tested Skale versions: 0.70, 0.71, 0.75, 0.76, 0.80, 0.802, and 0.81.
The observed file-header values are
7000, 7100, 7500, or 7600; 0.80, 0.802, and 0.81 all write 7600 even though
their instrument records differ. Read the instrument record's own chunk ID to
tell them apart, not the header.

## Help wanted: example files

Several open questions can be settled with a single small file saved from
Skale. [`EXAMPLES_NEEDED.md`](EXAMPLES_NEEDED.md) lists each one with the
exact steps to produce it. If you have a working copy of Skale, that list is
the most useful place to start.

## Repository contents

- `FORMAT.md`: the format, in on-disk order.
- `PROVENANCE.md`: the evidence behind each claim.
- `EXAMPLES_NEEDED.md`: open questions and the example files that would close
  them.
- `kaitai/skm.ksy`: Kaitai Struct schema.
- `reference/skmparse.py`: reference parser and verifier (Python 3, standard
  library only).
- `tests/fixtures/`: test files, each with recorded origin and license.
- `corpus/third-party-manifest.json`: hashes of the Skale executables used to
  author the fixtures.
- `docs/CHANGELOG.md`: history of corrections to the format description.

## Test files

No third-party songs are included. Every fixture was made for this project
from generated audio, and `tests/fixtures/manifest.json` records who made it,
how, from what inputs, and under what license. Fixtures fall into four
classes:

- **authentic**: saved by Skale;
- **synthetic**: built by a script from the documented format;
- **template-rewritten**: a script's edit of an authentic file;
- **malformed**: deliberately broken, for testing error handling.

Authentic saves show what Skale writes. Synthetic or modified files show
what Skale accepts only when a load test is recorded. They also test parsers.

The format description does not depend on OpenMPT or any other player.
Player-specific loaders belong in their own projects.

## Quick start

```sh
python3 reference/skmparse.py --json tests/fixtures/authentic/empty-skale-076-first.skm
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 tools/validate_public_tree.py .
```

To check the Kaitai schema against the reference parser:

```sh
kaitai-struct-compiler -t python --outdir /tmp/skm-generated kaitai/skm.ksy
python tools/check_instrument_layouts.py tests/fixtures/authentic --generated-dir /tmp/skm-generated
```

This needs the `kaitaistruct` 0.11 Python runtime. The checker also accepts
extra files or directories, so you can run it over your own songs.

## Licensing

Code is BSD-2-Clause. Documentation is CC-BY-4.0. The Kaitai schema,
fixtures, generated audio, and metadata are CC0-1.0. See `LICENSE_POLICY.md`
for details. Nothing here grants rights to Skale itself or to any third-party
song.
