<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Evidence and provenance

This file records the evidence behind each claim in `FORMAT.md`. The fixture
list, with hashes and creation steps, is `tests/fixtures/manifest.json`.

Kinds of evidence, strongest first:

- **Controlled save**: one setting changed in Skale, saved, and diffed against
  the save before it. Public fixtures named here are of this kind unless noted.
- **Paired XM export**: Skale's XM export of the same song, read as a second
  decoding of the same data.
- **Load test**: a file opened in Skale, with what Skale displayed or did.
- **Private corpus**: a structural invariant that holds exactly across a
  private collection of third-party songs. These songs are not distributed.
  Claims that rest only on this are marked *(private)*; `EXAMPLES_NEEDED.md`
  lists the public file that would replace each one.

Synthetic, template-rewritten, and malformed fixtures test parsers. They are
not evidence of what Skale writes.

## 1. Song text and timing

Controlled empty and metadata fixtures establish the title/message layout,
initial BPM, speed, channel count, the trailing version copy, and that the
Comments field shows text only up to a CR.

`song-text-short-padding` and `song-text-minimal` (synthetic) pin the
consumer rule: only the 8-byte trailer may be reserved. Reserving the ten-byte
footer truncates or rejects valid files, and the NUL separator is not always
present.

## 2. Orders and patterns

Synthetic fixtures cover song length, leftover order bytes, restart
position, sparse and missing pattern IDs, and row counts 1, 64, 128, and 256.

The row count is a `u16`. Every 256-row pattern in the private corpus stores
`00 01` (22/22), and no other pattern has a nonzero high byte *(private)*.
The public 256-row fixture is synthetic. Pattern and track records close
exactly as chunk lists in every public fixture.

## 3. Pattern events

`pattern-compressed-field-matrix` (synthetic) covers all 31 non-empty
presence masks, and `pattern-literal-event` covers the literal grammar. Both
load in Skale 0.76 without warning or visible corruption. `pattern-note-off`
loads in 0.76 and shows Note Off at row 0, confirming `0x81`. Note value
`0x80` occurs in no public fixture and no private song.

Track `first_row` and `last_row` agree with the decoded row count in every
track *(private)*.

Effect names and parameter descriptions are transcribed from Skale's Help →
Effects pages; the screenshots are not distributed. The XM numbering of
`00`–`0F` and `0C`'s halved parameter come from paired XM exports
*(private)*. Commands `10`–`13` appear in no public or private file.

## 4. Instruments

### Record versions and keymaps

Authentic keymap fixtures from 0.75, 0.76, 0.80, 0.802, and 0.81
(`keymap-two-sample-*`, each with an XM export and a resave) establish the
direct and framed keymap shapes and the 401/284/284/288-byte settings blocks.
The reference parser and the generated Kaitai parser agree on every boundary.
The 0.80 fixture leaves entry 127 unmapped; that one entry is the whole
4-byte difference between its 1048-byte prefix and 0.802's 1052. Synthetic
tests cover every observed prefix length and malformed framed entries.

### Settings block

- Fader and BAL: `mx-vol-076`, `mx-bal-076`, plus framed-layout probes.
- `toggle01_companion` at `+252`: a re-diff of the toggle fixture pair; equals
  `1 - toggle01` in all 35 authentic public and 1,294 private ID 4–6 records.
- Send knobs: a 0.75 song and its 0.81 resave agree on all 1,392 knob flags
  and values; a controlled save puts the mixer's first send knob at knob 0
  *(private)*.
- `+127` and `+149`: controlled saves changed each alone (device 01 → 02;
  enable light off/on) *(private)*. The public 0.81 VSTi fixtures store
  `+149 = 0` while linked, which is unexplained.
- `+126`: 1 on every VSTi-linked instrument and 0 elsewhere. No save has
  changed it alone, hence Probable.
- `+25..+125`, `+152`, and the constant runs are delimited only.
- Fadeout at `+0` matches Skale's XM export for 114/114 instruments across
  paired private songs (87 ID 3, 16 with 928-byte and 11 with 1056-byte ID 6
  prefixes) *(private)*.

### Envelopes

`envelope-baseline-076` and `envelope-edited-076` (with XM export) establish
the envelope chunk layout. Every record holds 32 envelope chunks in an 8 × 4
grid; unedited chunks have five default points (29 bytes in IDs 3/4, 30 in
IDs 5/6).

### Samples

`sample-*` fixtures, authored from the WAVs in `tests/fixtures/audio/`,
establish PCM8, PCM16, mono/stereo value counts, ping-pong loops, and Ogg
framing. `sp-vol-076` shows the editor's volume `0x80 → 0x40` stored as the
same bytes; playback establishes `0x80` as unity and `0x40` as half gain.
`sp-pan-076` establishes `0x80` centre and `0x00` hard left.

For Ogg, `stored_value_count` equals final granule × channels in 1,032/1,032
private samples and in the public Ogg fixtures. Sample metadata byte 4 tracks
bit depth in older private songs; fresh 0.81 saves always store 8.

Signed finetune and relative note are supported by paired XM exports, which
store the same bytes. No save has isolated a negative value.

## 5. FX chain and synths

`vst-fx-*-076` (mda Delay) establishes the 0-based slot index, the FX-strip
fader (`0.8 → 3.0`), the bypass byte, and that a parameter edit changes only
that parameter's float. `vsti-*-081` (mda JX10) establishes the synth slot
index, the parameter count, a parameter change (OSC Tune `-7 → -24` moves
parameter 1 from about 0.37 to 0.0), and the 110-byte mixer strip. The plugin
DLLs were used for authoring only and are not distributed.

## 6. Global mixer

Controlled saves *(private)* establish the 0.76 master volume, SUB fader,
balance, knob value, and knob LED fields, and confirm that SUB2–4 share SUB1's
layout. A test that moved an FX bus's fader and balance changed section 4
rather than section 5.

## 7. Version compatibility

Authentic files cover Skale 0.70, 0.71, 0.75, 0.76, 0.80, 0.802, and 0.81.
The compatibility table in `FORMAT.md` comes from load tests of the public
empty-song and keymap fixtures in each older version.
