<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Changelog

Changes to the format description, newest first. Corrections say what the
earlier reading was.

## Unreleased — initial public repository

### Format

- Added the effect-command table (`00`–`13`) from Skale's Help, with a status
  for each command. `10`–`13` scaling and the `0F` threshold are open.
- Documented the two volume-column bytes: second byte `00` is a plain volume,
  `80` is no volume, other values are unknown.
- Section 6: a synth record ends in a fixed 110-byte mixer strip after its
  plugin parameters.
- Section 3: the 32 envelope chunks per instrument form one 8 × 4 grid with a
  single layout.
- **Correction:** `toggle01_companion` is at settings `+252`, not `+152`.
  `+127` and `+149` are the VSTi device index and enable flag. `+126` is
  named by correlation only.
- **Correction:** note value `0x80` does not occur. Earlier counts came from a
  parser that predated the two-mode row grammar. Only `0x81` (Note Off) is a
  special note value.
- **Correction:** pattern `rows` is a `u16`; Skale writes 256 as `00 01`. It was
  read as a `u8` with 0 meaning 256. Pattern and track records are chunk lists;
  the bytes once described as a reserved word, separators, and a trailer are
  their headers and end markers. The synthetic 256-row fixture was regenerated.
- **Correction:** the instrument chunk ID is the record version (3–6) and
  selects the keymap and settings layout. Earlier versions of this document
  located the sample list by searching.
- Framed keymap entries are read as flag, layer count, and layers. Unmapped
  entries are reported separately from slot-0 mappings.
- Mapped the settings blocks, including the 16 send knobs in every record
  version.
- **Correction:** the older EQ offsets were four bytes out of alignment, which
  made some files look like they had two EQ bands. All files have three.
- **Correction:** a sample is 14 metadata bytes followed by an inner chunk list
  and EOF. The earlier 27-byte header and 3-byte trailer were this framing
  misread.
- **Correction:** the Ogg `inner_length` counts itself. The four bytes once
  called "Ogg padding" (first read as two) are the following EOF header.
  Passing them to a Vorbis decoder can stall it.
- **Correction:** loop points are stored as the hex values Skale's editor
  displays.
- **Correction:** song text is read from both ends. The ten-byte footer is not
  reserved, and the separator after the title is optional; both earlier
  assumptions truncated or rejected valid files.
- Note Death (Cut / Note Off) is an instrument setting, not a pattern
  encoding.
- Added fixtures from Skale 0.70, 0.71, 0.75, 0.76, 0.80, 0.802, and 0.81,
  covering PCM8, PCM16, stereo, Ogg, loops, envelopes, Note Off, Note Death,
  sample volume and panning, mixer fader and BAL, VST2 effects, and VSTi
  synths.

### Tooling

- The Kaitai schema decodes all four instrument record versions and rejects
  a synth mixer strip of the wrong length.
- The Kaitai schema's Ogg view is lazy, so a bad inner length fails
  validation instead of container parsing.
- `tests/fixtures/README.md` explains `expected_parse`.
- `validate_public_tree.py` no longer writes `__pycache__`.
