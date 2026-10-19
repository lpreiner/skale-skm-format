<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Interpretation history

## Unreleased — initial public repository

- Read section 2 as chunk lists: pattern chunks, half-width track chunks, and
  their end markers account for every former unknown/separator/trailer byte.
  The pattern row count is a `u16` (Skale writes 256 as `00 01`); the
  synthetic 256-row fixture was regenerated to match.
- Framed keymap entries are parsed as flag + layer count + layers. Unexpected
  layer bytes are preserved rather than failing the file, and `keymap_mapped`
  separates unmapped entries from explicit slot-0 mappings.
- Decoded the 16 send-knob records for every instrument record version, and
  mapped the rest of the settings blocks structurally.
- Described the Ogg inner length as self-inclusive (no change to validation).
- Resolved instrument chunk IDs as record versions; decode 128 direct or
  variable-length keymap entries and versioned settings blocks in Python and
  Kaitai. Added sample-less instrument support and regression coverage for all
  observed prefix lengths; known malformed keymaps no longer trigger scanning.
- Corrected sample framing to 14 metadata bytes plus an inner audio chunk list
  and EOF. The former Ogg padding is part of EOF; stream extraction stays inside
  its audio chunk while validating the historical inner-length overcount.
- Corrected older mixer EQ offsets using the 284/288-byte settings lengths and
  retained the nonboolean companion field as a raw value.
- Established redistribution-safe fixtures for application versions 0.70,
  0.71, 0.75, 0.76, 0.80, 0.802, and 0.81.
- Distinguished direct and framed instrument keymap/prefix layouts despite
  shared serialized version values.
- Verified PCM8, PCM16, stereo interleaving, Ogg framing, loop types, primary
  envelopes, Note Off, Note Death policy, sample volume/pan, and direct-layout
  mixer fader/BAL fields.
- Added rights-safe VST2 effect and VSTi fixture families, verified zero-based
  stored slot indices, FX mixer-volume and bypass fields, counted VSTi plugin
  parameters, and deterministic reload/resave behavior.
- Kept pattern note value `0x80` unidentified; instrument Note Death policy is
  not evidence that it represents pattern Note Cut.
- Corrected loop-point interpretation after confirming that Skale's editor
  displays those values in hexadecimal.
- Corrected embedded-Ogg padding from two bytes to four. Every observed stream
  ends `01 00 FF FF` inside the stored inner length (1032/1032 corpus samples,
  3/3 public fixtures); the earlier reading recognised only the trailing
  `FF FF`. Excluding just two bytes leaves `01 00` after the real Ogg EOS,
  which is enough to make a push-mode Vorbis decoder consume nothing while
  reporting "need more data" — hanging a length-driven read loop after the
  audio has already been fully decoded. Excluding all four is lossless;
  decoded sample counts are identical.
- Anchored the song-text message on the 8-byte trailer instead of reserving a
  fixed ten-byte footer. The footer is fixed-width in Skale's own output, but
  reserving it truncated the message of any structurally valid file whose
  trailing NUL run is shorter, and requiring it to be zero rejected such files
  outright. Added `song-text-short-padding.skm` and lowered the minimum section
  size from 18 bytes to 9 (a title terminator plus the trailer), pinned by
  `song-text-minimal.skm`. `zero_footer_raw` now reports `null` when the
  canonical footer region does not exist, rather than a truncated slice.
- Made the song-text separator conditional. It is absent in some structurally
  valid files, and consuming it unconditionally swallowed the first character
  of the message; the Kaitai schema did this and disagreed with the reference
  parser on every such file. Both now agree across the whole test corpus.
- Kept the Kaitai schema's Ogg framing decode out of container parsing. Sizing
  a field from the untrusted inner length made a declared-bad length fail at
  the container layer, contradicting the documented split where framing damage
  is the container's to reject and payload damage belongs to validation. The
  framing is now a lazy `ogg` instance; evaluating it is the validation step.
- Documented what `expected_parse` means in the fixture manifest: whether the
  container framing survives the mutation, not whether the payload is
  meaningful.
- Stopped `validate_public_tree.py` writing `__pycache__` while loading the
  reference parser. It did so after its own tree walk, so it passed on the run
  that created the cache and failed on the next one against an unchanged tree.
