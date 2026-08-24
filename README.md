<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# skale-skm-format

This project documents the `.skm` module format written by Skale Tracker and
provides an independent reference parser, a Kaitai Struct description, and a
small redistribution-safe test corpus.

Canonical repository: <https://github.com/lpreiner/skale-skm-format>

The format was reverse-engineered by observing files, comparing controlled
single-variable saves, using Skale's documented behavior and paired exports,
and validating structural invariants across a private research corpus. The
Skale executable was not disassembled, decompiled, or debugged.

## Project status

The container, song metadata, order list, pattern framing, channel-major event
encoding, common instrument/sample records, PCM and embedded Ogg payloads,
keymaps, principal envelopes, and the 0.76 global mixer section are documented.
Some 0.76 instrument prefixes remain difficult to locate declaratively. VST2
FX records and the counted VSTi parameter prefix are covered by rights-safe
fixtures; plugin-specific meanings and Skale's VSTi routing tail remain
intentionally incomplete.

This project's specification is partial and its parser interfaces are not yet
declared stable. A successful structural parse does not imply that every
optional or plugin-specific field is understood.

Authentic application evidence currently covers Skale 0.70, 0.71, 0.75,
0.76, 0.80, 0.802, and 0.81. Versions 0.72–0.74 and 0.77–0.79 were not
available and are not claimed as tested. The observed serialized header
values are 7000, 7100, 7500, and 7600; applications 0.80, 0.802, and 0.81
continue to stamp 7600 despite structural changes.

## Method and evidence

Format claims come from controlled Skale saves, single-variable comparisons,
paired XM exports, deterministic CC0 sample inputs, and structural invariants.
The fixture manifest is the public evidence index. Skale executables were used
only as applications and are neither analyzed nor redistributed.

Private third-party songs contributed to early exploration but are not needed
by the public tests and are not distributed. Conclusions supported only by
private observations remain explicitly qualified in `FORMAT.md` until public
causal evidence replaces them. In particular, consumers must distinguish the
serialized version stamp from the authoring application and total interleaved
sample values from per-channel audio frames.

## Repository contents

- `FORMAT.md`: current format description organized in on-disk order.
- `PROVENANCE.md`: evidence and confidence record.
- `kaitai/skm.ksy`: declarative Kaitai Struct parser.
- `reference/skmparse.py`: independent parser and semantic verifier.
- `tests/fixtures/`: compact fixtures with explicit redistribution rights.
- `corpus/third-party-manifest.json`: factual hashes identifying the Skale
  executables used for authoring; no executable or third-party module is
  redistributed.

## Corpus policy

Copyrighted scene music is not included. Public fixtures must be wholly
authored for this project and contain only deterministic generated audio under
an explicit redistribution-safe license. Each fixture records its creator,
inputs, creation method, SHA-256, license, authenticity classification, and
coverage purpose.

Fixtures are classified as:

- **authentic**: saved by Skale from rights-safe inputs;
- **synthetic**: constructed from the documented format;
- **template-rewritten**: derived automatically from an authentic safe seed;
- **malformed**: deliberately invalid input for boundary testing.

Synthetic fixtures test consumers; only authentic Skale saves are used as
evidence for what Skale itself emits or accepts.

## Independence from players

The specification describes stored SKM values directly and has no dependency
on OpenMPT or another playback engine. Player-specific mappings and loaders
belong in separate projects.

## Licensing

The public license split is CC0-1.0 for the Kaitai spec, generated audio,
approved fixtures, expected results, and corpus metadata; BSD-2-Clause for
code; and CC-BY-4.0 for documentation. See `LICENSE_POLICY.md`. Hash-only
metadata does not grant rights to third-party modules, and no such module is
distributed here.

## Quick start

```sh
python3 reference/skmparse.py --json tests/fixtures/authentic/empty-skale-076-first.skm
python3 tools/validate_public_tree.py .
python3 -m unittest discover -s tests -p 'test_*.py'
```
