<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Skale Tracker SKM format

This is the player-independent public format reference. It summarizes the
current, still-evolving interpretation; detailed experimental evidence is indexed in
`PROVENANCE.md`, and declarative implementation details are in
`kaitai/skm.ksy`.

Confidence labels:

- **Verified**: directly established by controlled changes, cross-format
  evidence, or a corpus-wide invariant with an independently known anchor.
- **Probable**: strongly supported but missing a decisive independent test.
- **Unknown**: framing may be known, but semantics are not established.

All multi-byte integers and IEEE-754 floats are little-endian.

The authentic fixture set covers files authored by Skale 0.70, 0.71, 0.75,
0.76, 0.80, 0.802, and 0.81. It does not claim application testing for
0.72–0.74 or 0.77–0.79. Later application versions do not necessarily change
the serialized version stamp: 0.80, 0.802, and 0.81 fixtures still store
`version_raw == 7600` while using distinct instrument-prefix structures.

## Chunk container — Verified

SKM is a repeated chunk stream. Each chunk has:

| Field | Type | Meaning |
|---|---:|---|
| `id` | `u16` | Chunk representation/category. |
| `tag` | `u16` | Top-level section or nested-record tag. |
| `length` | `u32` | Payload length, excluding the 8-byte header. |
| `body` | `u8[length]` | Bounded chunk payload. |

Top-level tag `0xFFFE` is the header. Tags `1` through `6` are the known
sections. Tag `0xFFFF`, normally with length zero, terminates a chunk list.
Nested sections reuse the same header shape but interpret local tag values in
their own context.

## File header — Verified

The header payload is nine bytes:

| Field | Type | Meaning |
|---|---:|---|
| `magic` | `u8[5]` | ASCII `ALIM3`. |
| `version_raw` | `u32` | Version multiplied by 10,000; `7600` represents 0.76. |

## Section 1: song text and timing — Verified

The payload is front- and back-anchored:

1. NUL-terminated title.
2. A NUL separator in the canonical layout. It is not always present, and a
   consumer must test for it rather than skipping a byte unconditionally --
   doing so swallows the first character of the message.
3. Message bytes, normally NUL-padded.
4. Ten-byte zero footer.
5. Eight-byte trailer containing initial BPM, initial speed, channel count, a
   reserved zero byte, and a redundant `u32 version_raw`.

Only item 5 is a fixed-width field a consumer may reserve. The footer is
fixed-width in files Skale itself writes -- inserting one extra zero shifts
Skale's own reader by exactly one byte -- but a consumer that reserves ten
bytes truncates the message of any structurally valid file whose padding run
is shorter, and one that requires those ten bytes to be zero rejects such a
file entirely. Anchor the message on the trailer and strip trailing NULs
instead. The smallest well-formed section is nine bytes: a title terminator
plus the trailer.

Existing evidence supports ISO-8859-1 as a conservative byte-to-text mapping,
but the actual non-ASCII encoding still needs a controlled fixture.
In a controlled synthetic fixture containing `First line\rSecond line`, Skale
0.76's visible Comments field showed only `First line`. A subsequent fixture
containing `CC0 fixture message` without a terminating CR displayed an empty
Comments field. Consumers should preserve the full bounded message byte region,
but multiline presentation is not established by these UI observations. The
public conformance fixture uses `CC0 fixture message\r`; Skale 0.76 displays
`CC0 fixture message`, confirming that CR terminates a visible comment entry.

## Section 2: orders and patterns — Verified

The section begins with:

| Field | Type | Meaning |
|---|---:|---|
| `channel_count` | `u8` | Number of channel tracks in each pattern. |
| `order_list_raw` | `u8[256]` | Pattern IDs; bytes beyond `song_length` are stale state. |
| `song_length` | `u8` | Authoritative number of order entries. |
| `repeat_pattern` | `u8` | Order position used when playback restarts. |

Pattern IDs are identities, not dense array positions. Deleted patterns may
leave gaps. An order may reference a missing ID; observed Skale behavior is to
present a synthetic empty 64-row pattern for it.

### Pattern records

From offset `0x103` the section is an ordinary chunk list closed by the
standard EOF chunk. Each pattern is a chunk with `id = 1`, `tag = 1`, and a
`u32` length. Older descriptions called its header a signature `01 00 01 00`
plus a `u16` size and two zero bytes; those zero bytes are the length's high
half. The payload is:

| Field | Type | Meaning |
|---|---:|---|
| `pattern_index` | `u8` | Pattern ID. |
| `rows` | `u16` | Row count, 1..256. |
| tracks | track chunks | One per channel, then an end marker. |

`rows` is a `u16`. Skale writes a 256-row pattern as `00 01`. An earlier
reading treated it as a `u8` in which 0 meant 256, and the byte after it as a
constant. Skale refuses to expand a pattern beyond 256 rows. A stored 0 is not
produced by Skale; its behavior is untested.

Tracks use a half-width chunk header: `u8 id` (1), `u8 tag`, and a `u16`
length. Tag 1 is a track whose payload is `u8 channel_index` followed by its
events. Tag `0xFF` with length 0 ends the list. The bytes formerly described
as `(0, 1, 1)` are the row count's high byte plus the first track header.
The `01 01` separators and the `01 FF 00 00` trailer are track headers and
the end marker.

### Track and event encoding

Patterns store one length-bounded track per channel. Track records carry their
starting and ending absolute row positions. Event rows use two grammars:

- `0x80` is an empty-row marker.
- With bit 7 set, low bits indicate presence of effect command, note,
  instrument, two-byte volume, and effect parameter fields.
- With bit 7 clear, the byte is a literal effect command and is followed by
  note, instrument, two-byte volume, and parameter fields.

Trailing empty pattern rows are not encoded and must be padded by the consumer
to the declared pattern length. Note value `0x81` is Note Off. The distinct
value `0x80` remains unidentified. “Note Death: Cut / Note Off” in the extended
instrument editor is an instrument-level end-of-note policy and does not by
itself establish a pattern-row encoding for Note Cut. Do not label note value
`0x80` as Note Cut without a causal pattern save/diff.

The public synthetic compressed-mask, literal-row, and Note Off fixtures all
load in Skale 0.76 without a new-chunk warning or visible pattern corruption.
The Note Off fixture visibly displays Note Off at row 0, providing an
application-side check independent of the research parser.

## Section 3: instruments and samples — partial

The instrument chunk ID is its record version, independent of the file's
`version_raw`. Known IDs select a 128-entry keymap followed by a fixed settings
block and the nested sample/envelope list:

| Record ID | Observed writer | Keymap bytes | Settings bytes | Total prefix |
| --- | --- | ---: | ---: | ---: |
| 3 | 0.70/0.71/0.75 | 128 direct | 401 | 529 |
| 4 | 0.76 | 128 direct | 284 | 412 |
| 5 | 0.80/0.802 | 128 framed entries | 284 | 1048/1052 observed |
| 6 | 0.81 | 128 framed entries | 288 | 544/716/784/928/1056 observed |

Direct entries are one local sample-slot byte each. A framed entry is either
`00 00` (unmapped) or `01 01 <slot> 00 7F 00` (mapped). Thus a framed map
occupies `256 + 4*k` bytes for `k` mapped entries. The first 96 entries map
playable notes; the remaining 32 serialized entries must also be consumed,
without assuming their musical meaning. This explains the formerly opaque
prefix sizes without searching or selecting from the shared `7600` file stamp.
The Kaitai spec now decodes all four observed record versions declaratively.

An unmapped entry (`00 00`) is distinct on disk from an explicit mapping to
local slot 0, although both yield slot 0 in a slot list. The reference parser
reports the distinction as `keymap_mapped`. The authentic 0.80 fixture leaves
entry 127 unmapped, which accounts for its 1048-byte prefix against 0.802's
1052; IDs 5 and 6 differ only by the four settings bytes.

The entry bytes fit `u8 flag, u8 layer_count, layer[layer_count]` with 4-byte
`(slot, 00, 7F, 00)` layers. Reading the second byte as a count is a
conjecture; no file has a count other than 0 or 1. Parsers should reject an
inconsistent flag/count header but preserve unexpected layer bytes.

The reference parser preserves its 96-note `keymap` view and adds
`keymap_all_slots`, `record_version`, `prefix_length`, and `post_keymap_length`.
Unknown IDs retain an explicitly marked structural-search fallback in Python;
Kaitai preserves their remainder as raw bytes. Known malformed layouts are
rejected rather than scanned for an alternative start. The fallback alone
cannot resolve intentionally constructed ambiguous nested-list decoys.

Sample-less ID 3/4 instruments can start their nested list with `(id=2, tag=2)`
parameter/envelope chunks. ID 5/6 use `(id=3, tag=2)`. Both families are supported.

In a backward-compatibility test, Skale 0.76 loads its own controlled keymap
fixture without a warning but reports “NEW Chunks Found” for each controlled
0.80, 0.802, and 0.81 keymap fixture. This brackets the newly encountered
instrument content at or before 0.80, but the warning alone does not identify
which record inside the larger prefix triggers it. After the warning is
dismissed, the instrument and its samples are not loaded by 0.76; the message
therefore represents skipped unsupported content rather than successful
partial interpretation of the framed layout.

Skale 0.80 loads both the controlled 0.80 and 0.802 fixtures without a warning,
establishing that it accepts both the 1048-byte and 1052-byte prefixes. Loading
the 0.81 fixture in 0.80 reports “NEW Chunks Found,” placing another
compatibility boundary at the 1056-byte 0.81 structure. After dismissal, 0.80
does not load the 0.81 instrument or its samples. Skale 0.802 likewise reports
“NEW Chunks Found” for the controlled 0.81 fixture, showing that the added 0.81
content is unknown to both earlier framed-layout readers; after dismissal,
0.802 also discards the instrument and samples.

Known structures include principal envelopes, keymaps, and common settings.
Relative to the end of all 128 keymap entries, fadeout is `u16` at `+0`,
`mute_toggle` is at `+6`, `toggle01` at `+7`, Note Death at `+8`, and the
volume/BAL floats at `+9/+13`. Note Death `0` means Cut and `1` means Note Off;
controlled single-variable saves establish this for writers 0.76–0.81.
It is independent of pattern note-value encoding.

IDs 4/5 share a 284-byte settings block. SUB assignments occupy `+253..256`
and three nine-byte EQ records (enabled byte, gain float, frequency float)
start at `+257`, `+266`, and `+275`. ID 6 adds three BGR color bytes and one
pad at `+284..287`. Earlier reports of a two-band EQ were caused by reading
these fields four bytes out of alignment.

The first 130 settings bytes are shared by IDs 3–6. After the fields above,
`+25..88` is a 64-byte table that is the identity map in nearly every record,
and `+89..127` holds flags and floats. These are probably the instrument
filter (defaults 5000, 5000, 50, 0.5, 0.5, 0, 10; a 3-bit mask at `+122`), but
no UI control has been tied to them yet.

Each block ends its common part with 16 FX-send knob records. IDs 4–6 store
them at `+156` as 6 bytes each (`u8 flag, f32 value, u8 index`). ID 3 stores
them at `+139` as 13 bytes each (`u8 flag, f32 value, f32 0.0, f32 1.0`). ID 3
also has a mostly-zero 54-byte tail. Knob 0 is the mixer's first send knob;
knobs 8–15 have no visible control. The historical `toggle01_companion` at
`+152` is preserved as a raw value: it is not universally boolean. The
remaining constant bytes (`+132..147` all `0xFF`, `0x7F` at `+155`) are
unidentified.
Structural correspondence across layouts does not independently establish
UI semantics for every field; controlled evidence is distinguished in provenance.

### Sample metadata and payload — Verified

Known sample fields include volume, panning, signed finetune, signed relative
note, loop start/end/type, stored format, frame/value counts, channel count,
and audio payload length.

Sample volume and panning are stored as the hexadecimal bytes displayed by
Skale's sample editor. For volume, `0x80` is unity and the controlled `0x40`
probe is one-half linear gain; `0x00` is silence. For panning, `0x80` is center
and `0x00` is hard left. The opposite endpoint has not yet been established by
a public causal fixture, so consumers should preserve the raw byte rather than
infer an undocumented range endpoint.

The stored sample-value count is the total number of interleaved values.
Per-channel frame count is therefore total values divided by channel count.
PCM payloads may be signed 8-bit or signed little-endian 16-bit. The sample
rate is represented through XM-compatible relative-note/finetune semantics
rather than an explicit Hertz field.

After `u8 local_slot` and a NUL-terminated name, each sample slot has 14
metadata bytes (volume through loop type), followed by an inner chunk list.
An empty slot contains only EOF `(id=1, tag=0xFFFF, length=0)`. A populated
slot contains an audio chunk `(id=format, tag=1, length=N)` and then EOF.
The format IDs are 2 (PCM16), 3 (PCM8), and 4 (Ogg). Its payload begins with
`u32 stored_value_count` and `u8 channels`, followed by `N-5` audio bytes.
All boundaries must close exactly without slack.

This corrects the older 27-byte-header/three-byte-trailer interpretation.
The former unknown `u16` at metadata offset 16 is the audio chunk tag.
The apparent five-byte PCM tail and three-byte record trailer together are
the eight-byte EOF header. There is no extra PCM padding.

For Ogg, the bounded audio bytes contain a `u32 inner_length` followed by the
self-contained `OggS` stream. The inner length is self-inclusive: it counts
its own four bytes plus the stream, which ends exactly where the audio chunk
ends. Validate `inner_length == bounded_audio_length` (including the length
word), a valid following EOF header, and Ogg magic. Pass only the bytes after
the length word and before EOF to a decoder. Older documentation described
the length as overcounting into four bytes of "Ogg padding", which are
actually the EOF header. Including even two of them can stall a push-mode
decoder.

For Ogg, `stored_value_count` equals the final page's granule position times
the channel count, as it does for PCM's interleaved values. Consumers can use
this as a cross-check.

Python exposes `audio_chunk_length` and `audio_payload_length`; the latter
counts audio bytes after the five-byte count/channel prefix. The historical
`audio_data_length` remains an alias for the complete inner chunk length,
not the length of a slice starting at `audio_data_offset`. `audio_eof_valid`
reports terminal header validity. Container inspection keeps deliberately
bad EOF values visible; stream extraction rejects them. Kaitai likewise
bounds its lazy Ogg view by the enclosing chunk and leaves payload-value
validation to the consumer.

## Section 4: FX chain — Verified for the observed VST2 layout

The nested slot framing, plugin path/name strings, parameter count/array, and
principal controls are structurally decoded. A clean 0.76 mda Delay family
establishes that UI slot 01 is stored as index 0, the first float is Skale's
FX-strip mixer-volume value (`0.8` to `3.0` in the probe), and the byte after
the two floats is a bypass flag (`0` enabled, `1` disabled). A one-variable
plugin edit changed only parameter index 5 from `0.5` to `1.0`. Plugin paths
and parameter meanings remain plugin-specific and are not portable.

## Section 5: global/mixer — Verified for known layouts

Before 0.76 the observed section is four bytes. The 0.76 section is 424 bytes
and contains master volume, four subgroup records, and an FX-bus send matrix.
The principal record shapes and editable fields were established by controlled
single-variable saves. Consumers without an equivalent routing graph may
preserve or report these values without reproducing playback routing.

## Section 6: VSTi/plugin state — partial

The section is an empty nested list in most files. A clean Skale 0.81 mda JX10
family (whose common file header still says 7600) establishes that UI synth
slot 01 is stored as index 0. After the path and display-name strings, the
record begins with an explicit `u32` plugin-parameter count followed by
exactly that many `f32` plugin parameters. Changing JX10's
second parameter, OSC Tune, from `-7` to `-24` changed parameter index 1 from
approximately `0.37` to `0.0`. The remaining entry bytes contain Skale-owned
routing/send state; preserve them as bounded opaque data until their internal
layout is generalized.

As a controlled compatibility experiment, Skale 0.75 reports “New Chunks
Found” when loading the empty 0.76 fixture. Single-change derivatives establish
that the 424-byte section 5 and the empty top-level tag 6 each independently
trigger the warning. Changing both stored version stamps from 7500 to 7600 does
not. Because these fixtures contain no instruments or samples, the warning is
not evidence by itself of a later keymap layout or Ogg data.

## Validation requirements

A robust consumer should at minimum:

- bound every chunk and nested record by its declared parent payload;
- reject length arithmetic overflow and premature EOF;
- cap patterns, channels, rows, instruments, samples, and decoded audio;
- distinguish sparse IDs from dense counts;
- accept the documented missing-pattern behavior only as an explicit policy;
- validate every track consumes exactly its bounded event bytes;
- validate sample header/payload size relationships before allocating;
- handle unknown and incomplete sections without reading outside their chunk;
- report unsupported semantic features separately from malformed structure.

## Known open questions

- Non-ASCII text encoding.
- Meaning of the second byte in non-plain volume-column forms.
- Note value `0x80` and several Skale-native effects.
- The sample metadata byte at offset 4 (8 or 16; tracks bit depth only in older files).
- UI meaning of the probable filter fields, the 64-byte table, and the
  constant settings bytes.
- Whether framed keymap entries can hold more than one layer.
- How Skale loads a stored pattern row count of `0` (never written by Skale).
- Whether Skale plays anything for an unmapped framed keymap entry.
- Extended MIDI/remapping state.
- Internal layout of the Skale-owned routing/send tail in section 6.
