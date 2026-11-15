<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Skale Tracker SKM format

This document describes the SKM format in on-disk order. The evidence for each
claim is in `PROVENANCE.md`, and `kaitai/skm.ksy` is the machine-readable
version. Open questions are collected in `EXAMPLES_NEEDED.md`.

Confidence labels:

- **Verified**: established by a controlled save, a paired XM export, or an
  invariant that holds exactly across every file examined.
- **Probable**: consistent with all evidence, but no single test isolates it.
- **Unknown**: the bytes are delimited, but their meaning is not known.

All multi-byte integers and IEEE-754 floats are little-endian.

## Chunk container — Verified

An SKM file is a sequence of chunks:

| Field | Type | Meaning |
|---|---:|---|
| `id` | `u16` | Chunk category. |
| `tag` | `u16` | Section number, or a record type inside a nested list. |
| `length` | `u32` | Payload length, excluding the 8-byte header. |
| `body` | `u8[length]` | Payload. |

At the top level, tag `0xFFFE` is the file header, tags `1`–`6` are the six
sections, and tag `0xFFFF` with length 0 ends the list. Nested lists inside a
section use the same header, but their tag values have meanings local to that
section.

## File header — Verified

Nine bytes:

| Field | Type | Meaning |
|---|---:|---|
| `magic` | `u8[5]` | ASCII `ALIM3`. |
| `version_raw` | `u32` | Version × 10,000; `7600` means 0.76. |

Skale 0.80, 0.802, and 0.81 all write `7600`. Use the instrument record's
chunk ID (section 3) to distinguish them.

## Section 1: song text and timing — Verified

In order:

1. NUL-terminated title.
2. Usually a NUL separator. It is sometimes absent; test for it rather than
   skipping a byte, or the first character of the message is lost.
3. Message bytes, NUL-padded.
4. In Skale's own output, a ten-byte zero footer.
5. An eight-byte trailer: initial BPM, initial speed, channel count, a zero
   byte, and a `u32` copy of `version_raw`.

Read the trailer from the end of the section, then take everything between
the title and the trailer as the message and strip trailing NULs. Do not
reserve the footer: some valid files have a shorter NUL run, and reserving
ten bytes truncates their message. The smallest valid section is nine bytes,
a title terminator plus the trailer.

Skale's Comments field shows text up to the first CR. A message
`CC0 fixture message\r` displays as `CC0 fixture message`; a message without a
CR displays as empty, and `First line\rSecond line` displays only
`First line`. Preserve the whole message region regardless.

Text encoding beyond ASCII has not been tested. ISO-8859-1 is a safe default.

## Section 2: orders and patterns — Verified

| Field | Type | Meaning |
|---|---:|---|
| `channel_count` | `u8` | Tracks per pattern. |
| `order_list_raw` | `u8[256]` | Pattern IDs. Entries past `song_length` are leftover data. |
| `song_length` | `u8` | Number of order entries in use. |
| `repeat_pattern` | `u8` | Order position playback restarts from. |

Pattern IDs are identifiers, not array positions; deleting patterns leaves
gaps. An order entry may name a pattern that does not exist. Skale plays an
empty 64-row pattern in its place.

### Pattern records

From offset `0x103`, the section is a chunk list ending in the standard EOF
chunk. Each pattern is a chunk with `id = 1`, `tag = 1`:

| Field | Type | Meaning |
|---|---:|---|
| `pattern_index` | `u8` | Pattern ID. |
| `rows` | `u16` | Row count, 1–256. |
| tracks | track chunks | One per channel, then an end marker. |

Skale will not expand a pattern past 256 rows, and writes 256 as `00 01`.
Skale never writes `rows = 0`.

Track chunks use a 4-byte header: `u8 id` (1), `u8 tag`, `u16 length`. Tag 1
is a track: `u8 channel_index` followed by its events. Tag `0xFF`, length 0,
ends the list.

### Events

A track's events begin with `u8 last_row` and `u8 first_row`, both absolute
row numbers, followed by one row token per row from `first_row` to
`last_row`. Rows outside that range are empty; pad to `rows`. Each row token
begins with a marker byte:

- `0x80`: empty row.
- Bit 7 set (other than `0x80`): compressed row. Bits 0–4 flag the presence of
  effect command, note, instrument, volume (2 bytes), and effect parameter.
  Present fields follow in that bit order.
- Bit 7 clear: literal row. The marker is the effect command, followed by note,
  instrument, volume (2 bytes), and effect parameter, all always present.

Notes `0`–`95` are C-0 to B-7. `0x81` is Note Off. No other note value has
been observed.

The two volume bytes:

| Second byte | Meaning | Status |
|---|---|---|
| `00` | Plain volume. The first byte is `0`–`128`; halve it for XM's `0`–`64`. | Verified |
| `80` | No volume. Ignore the first byte. | Verified |
| other | Unknown. | Unknown |

The instrument editor's Note Death setting (Cut or Note Off) is an instrument
property and does not imply a pattern encoding for Note Cut.

### Effect commands

Names and parameter descriptions come from Skale's Help → Effects pages.
Where the Help names two parameters, they are the high and low nibbles of the
parameter byte. Command numbers are hex.

| Cmd | Skale name | Parameter | Status |
| --- | --- | --- | --- |
| `00` | Arpeggio | hi: first halftone (tick 2); lo: second halftone (tick 3) | Verified = XM `0` |
| `01` | Portamento Up | halftones per tick | Verified = XM `1` |
| `02` | Portamento Down | halftones per tick | Verified = XM `2` |
| `03` | Porta to Note | halftones per tick | Verified = XM `3` |
| `04`–`07` | (not in Help) | as XM | Verified = XM `4`–`7` |
| `08` | Pan | `00` left – `FF` right | Verified = XM `8` |
| `09` | Sample Offset | offset ÷ 256 | Verified = XM `9` |
| `0A` | Volume Slide | hi: up speed; lo: down speed; ignored unless one is 0 | Verified = XM `A` |
| `0B` | Jump to Song Position | order position; playback starts at row 0 | Verified = XM `B` |
| `0C` | Volume | `00`–`80`; larger values clamp to `80` | Verified = XM `C`, parameter ÷ 2 |
| `0D` | Jump to Next pattern line | row in the next pattern | Verified = XM `D` |
| `0E` | Extended | sub-command in hi nibble (below) | Verified = XM `E` |
| `0F` | BPM / Speed | value | Verified = XM `F`; see note |
| `10` | FX On/Off | hi: MultiFX effect `1`–`8`, `A`, `B`; lo: `0` off, `1` on | Unknown; Skale-only |
| `11` | Instrument filter On/Off | hi: unused; lo: `0` off, `1` on | Unknown; Skale-only |
| `12` | Note Cutoff | filter cutoff `00`–`FF` | Unknown; Skale-only |
| `13` | Note Q | filter resonance `00`–`FF` | Unknown; Skale-only |

`0E` sub-commands in the Help: `1`/`2` fine portamento up/down, `3` glissando
control, `4` vibrato control, `5` fine tune, `6` pattern loop, `7` tremolo
control, `9` retrigger note, `A`/`B` fine volume slide up/down, `C` note cut,
`D` note delay, `E` pattern delay.

- `00`–`0F` export to XM unchanged except `0C`, whose parameter is halved.
  `0C`'s `00`–`80` range is the same scale as the plain volume byte. The Help
  omits `04`–`07`; Skale's release notes list them.
- `0F`: the Help says values above 31 set speed and lower values set tempo,
  the reverse of XM. Until tested, treat this as a Help error and follow XM.
- `11` acts on the instrument in the instrument column, or on the instrument
  the channel is already playing.
- `10`–`13` have not been seen in any file, so their stored parameter values
  are unconfirmed. Skale gives cutoff and resonance a `00`–`FF` range.

## Section 3: instruments and samples — Verified layout, some fields Unknown

Section 3 is a chunk list with one chunk per instrument. The chunk ID is the
instrument record version. It selects the keymap format and the size of the
settings block that follows. The prefix consists of the keymap and settings
block, before the nested envelope and sample chunks:

| Record ID | Written by | Keymap | Settings bytes | Total prefix |
| --- | --- | --- | ---: | ---: |
| 3 | 0.70, 0.71, 0.75 | 128 direct entries | 401 | 529 |
| 4 | 0.76 | 128 direct entries | 284 | 412 |
| 5 | 0.80, 0.802 | 128 framed entries | 284 | 1048 or 1052 observed |
| 6 | 0.81 | 128 framed entries | 288 | 544, 716, 784, 928, 1056 observed |

### Keymap

A direct entry is one byte: the local sample slot. A framed entry is either
`00 00` (unmapped) or `01 01 <slot> 00 7F 00` (mapped), so a framed keymap is
`256 + 4k` bytes for `k` mapped entries. The first 96 entries are the playable
notes; the other 32 must be read but have no known musical meaning.

An unmapped entry and a mapping to slot 0 are different on disk. The reference
parser reports the difference as `keymap_mapped`.

A framed entry appears to be `u8 flag, u8 layer_count, layer[layer_count]`,
with each layer `(slot, 00, 7F, 00)`. The count reading is Probable: no file
has a count other than 0 or 1. Reject an entry whose flag and count disagree,
but keep any unexpected layer bytes.

### Settings block

Offsets are from the end of the 128th keymap entry.

| Offset | Field | Status |
|---|---|---|
| `+0` | `u16` fadeout | Verified |
| `+6` | `mute_toggle` | Verified |
| `+7` | `toggle01` | Verified |
| `+8` | Note Death: `0` Cut, `1` Note Off | Verified (0.76–0.81) |
| `+9` | `f32` volume fader | Verified |
| `+13` | `f32` balance (labelled BAL in Skale) | Verified |
| `+25..+88` | 64-byte table, almost always mapping each index to itself | Unknown |
| `+89..+125` | flags and floats, probably the instrument filter | Unknown |
| `+126` | `ext_synth_mode`: 1 on VSTi-linked instruments | Probable |
| `+127` | `vsti_device`: 0-based section 6 synth slot | Verified |
| `+132..+147` | always `FF` | Unknown |
| `+149` | `vsti_device_enabled` (IDs 4–6) | Verified |
| `+152` | `byte_152` | Unknown |
| `+155` | always `7F` | Unknown |

The first 130 bytes are laid out the same in IDs 3–6. After that, the layouts
differ:

- **IDs 4–6:** 16 send-knob records of 6 bytes
  (`u8 flag, f32 value, u8 index`) at `+156`. `toggle01_companion` at `+252`
  always equals `1 - toggle01`. SUB1–4 assignments at `+253..+256`. Three
  9-byte EQ bands (`u8 enabled, f32 gain, f32 frequency`) at `+257`, `+266`,
  and `+275`. ID 6 adds three BGR colour bytes and a pad at `+284..+287`.
- **ID 3:** 16 send-knob records of 13 bytes
  (`u8 flag, f32 value, f32 0.0, f32 1.0`) at `+139`, then a 54-byte tail
  that is mostly zero.

Knob 0 is the mixer's first send knob. Knobs 8–15 have no visible control.

### Envelopes

After the settings block comes a nested chunk list holding the instrument's
envelopes and samples. Every instrument has 32 envelope chunks (`tag = 2`;
`id = 2` in IDs 3/4, `id = 3` in IDs 5/6), forming an 8 × 4 grid: rows `0`–`7`
are steps A–H, and columns `1`–`4` are volume, panning, and two unidentified
envelopes. Each chunk is:

```
u8  row
u8  col
u8  enabled
u8  num_points
(u16 x, u16 y)[num_points]
u8  sustain_enabled
u8  sustain_point
u8  loop_enabled
u8  loop_start
u8  loop_end
u8  0              (id 3 only)
```

An instrument with no samples may begin its nested list with envelope chunks.

### Samples — Verified

Each sample slot is `u8 local_slot`, a NUL-terminated name, 14 metadata bytes,
and an inner chunk list. An empty slot's list is just EOF. A populated slot's
list is one audio chunk (`id` = format, `tag = 1`) followed by EOF. Format 2
is PCM16, 3 is PCM8, 4 is Ogg Vorbis. Each chunk's declared payload length
must match the number of payload bytes.

The metadata holds volume, panning, signed finetune, signed relative note, loop
start, loop end, and loop type. Volume and panning are the hex values Skale's
sample editor shows. Volume `0x80` is unity, `0x40` is half linear gain, and
`0x00` is silent. Panning `0x80` is centre and `0x00` is hard left; the right
endpoint is untested, so keep the raw byte. Metadata byte 4 is 8 or 16 and is
Unknown.

There is no sample-rate field. Relative note and finetune use XM's scheme,
with XM's 8363 Hz reference.

The audio chunk payload is `u32 stored_value_count`, `u8 channels`, then the
audio. `stored_value_count` counts interleaved values, so frames per channel is
`stored_value_count / channels`. PCM is signed: 8-bit, or 16-bit
little-endian. There is no padding after PCM data.

For Ogg, the audio is `u32 inner_length` followed by an `OggS` stream that
runs to the end of the chunk. `inner_length` includes its own four bytes.
Check that it equals the audio length, that the stream starts with `OggS`, and
that a valid EOF header follows the chunk. Give the decoder only the stream
bytes: passing any of the following EOF header can stall a push-mode Vorbis
decoder. `stored_value_count` equals the last page's granule position times
the channel count.

## Section 4: FX chain — Verified for VST2

A chunk list with one record per FX slot:

| Field | Type | Meaning | Status |
|---|---|---|---|
| `slot_index` | `u8` | 0-based; UI slot 01 is 0. | Verified |
| `path` | NUL-terminated | Plugin DLL path. | Verified |
| `display_name` | NUL-terminated | Plugin's own name. | Verified |
| `loaded` | `u8` | Always 1 in observed files. | Unknown |
| `mixer_volume` | `f32` | FX strip fader. | Verified |
| `wet_or_pan` | `f32` | Usually 0.5; probably the FX strip balance. | Probable |
| `bypassed` | `u8` | 0 enabled, 1 disabled. | Verified |
| `param_count` | `u32` | Number of plugin parameters. | Verified |
| `params` | `f32[param_count]` | Plugin parameters, in plugin order. | Verified |

Parameter meanings belong to each plugin. `path` holds the full path only when
the plugin was loaded from disk in that session; after the song is reloaded
and saved again, Skale writes the short display name instead. Do not rely on
`path` to locate a plugin.

## Section 5: global mixer — Verified for 0.76

Files with `version_raw` below 7600 store four bytes: one `f32`, probably the
master volume. Files stamped 7600 store 424 bytes:

| Offset | Size | Field |
|---|---:|---|
| 0 | 4 | `f32` master volume |
| 4 | 132 | SUB1–4, 33 bytes each |
| 136 | 288 | FX-bus send matrix, 32 records of 9 bytes |

SUB1–4 are the four mixer sub-buses. A SUB record is `u8 flag0`, `f32 fader`
(default 1.0), `f32 balance` (default 0.5), then four 6-byte send knobs
(`u8 pad, f32 value, u8 index`). `pad` is set when the knob's LED is
clicked. `flag0` is Unknown.

The send matrix is 8 source buses × 4 sends. Each record is
`u8 enabled_flag`, `u32 target_bus` (`0xFFFFFFFF` = none), `f32 send_level`.
`enabled_flag` is Unknown. An FX bus's own fader and balance are stored in
section 4, not here.

## Section 6: VSTi synths — Verified for the observed layout

Empty in most files. Otherwise, a chunk list with one record per loaded synth:

1. `u8 slot_index`, 0-based (UI slot 01 is 0).
2. NUL-terminated path and display name (the path behaves as in section 4).
3. `u32 param_count`, then `f32 params[param_count]`.
4. A 110-byte per-synth mixer strip:

| Offset | Field |
|---|---|
| `+0` | `u8` zero |
| `+1..+96` | 16 send knobs, 6 bytes each (`u8 flag, f32 value, u8 pad`) |
| `+97` | `f32` balance (BAL; default 0.0) |
| `+101` | `f32` fader (default 1.0) |
| `+105` | `u8 sub_assign[4]` |
| `+109` | `u8 mute_or_toggle` (Unknown) |

The strip must end exactly at the end of the record.

## Version compatibility

Older Skale versions warn "NEW Chunks Found" when they meet data they do not
know, then skip it:

| Reader | File | Result |
|---|---|---|
| 0.75 | empty 0.76 song | Warning. The 424-byte section 5 and the empty section 6 each trigger it on their own; the header version does not. |
| 0.76 | 0.80, 0.802, 0.81 instrument | Warning; instrument and samples not loaded. |
| 0.80 | 0.802 instrument | Loads without warning. |
| 0.80, 0.802 | 0.81 instrument | Warning; instrument and samples not loaded. |

## Validation

A consumer should:

- bound every chunk and nested record by its parent's length;
- reject length overflow and early EOF;
- cap pattern, channel, row, instrument, sample, and decoded-audio counts;
- treat pattern and instrument IDs as sparse;
- handle missing patterns by an explicit policy;
- check that each track consumes exactly its event bytes;
- check sample lengths before allocating;
- skip unknown sections without reading past their chunk;
- report unsupported features separately from malformed structure.

If a sample payload is corrupt but its chunk boundaries are intact, skip
that sample and continue reading the file.
