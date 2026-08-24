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
2. Canonical NUL separator.
3. Message bytes, normally NUL-padded.
4. Ten-byte zero footer.
5. Eight-byte trailer containing initial BPM, initial speed, channel count, a
   reserved zero byte, and a redundant `u32 version_raw`.

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

### Pattern record

Each record begins with signature `01 00 01 00`, followed by a `u16` packed
size counted from the size field itself, two unknown zero bytes, pattern ID,
row-count byte, the observed bytes `(0, 1, 1)`, packed track data, and trailer
`01 FF 00 00`.

The row count is a `u8`; stored zero represents 256 rows. Skale refuses to
expand a pattern beyond 256.

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

The outer nested chunk list and explicit instrument record IDs are Verified.
Pre-0.76 instrument internals have stable version-dependent framing. Version
0.76 has several observed envelope/keymap-to-sample-list gap sizes without a
known discriminant; bounded structural validation is required before treating
a candidate location as a sample list.

A deliberately constructed prefix can wrap the genuine nested list in an
additional structurally valid chunk, making two candidate starts satisfy all
currently verified invariants. Such a file cannot yet be disambiguated safely;
doing so requires decoding enough of the remaining instrument-prefix records to
validate their identities and sizes. Malformed sample-bearing decoys are
rejected using the verified sample-size invariant.

Keymap selection is not determined by the file version alone. Controlled CC0
fixtures establish these layouts:

| File/application case | Prefix before nested sample list | Keymap |
| --- | ---: | --- |
| Format 0.75 | 529 bytes | 96 direct local-slot bytes |
| Format 0.76 written by Skale 0.76 | 412 bytes | 96 direct local-slot bytes |
| Format 0.76 written by Skale 0.80 | 1048 bytes | 96 entries of 6 bytes each |
| Format 0.76 written by Skale 0.802 | 1052 bytes | 96 entries of 6 bytes each |
| Format 0.76 written by Skale 0.81 | 1056 bytes | 96 entries of 6 bytes each |

In the framed layout each verified entry is `01 01 <slot> 00 7F 00`. The two
principal layouts have the same header version and identical logical maps,
and the framed form is established by application version 0.80. This proves
that consumers must use validated instrument framing rather than
`version_raw` alone. The Kaitai specification deliberately leaves 0.76
instrument remainders opaque until a declarative discriminator for the known
prefix variants is established. Controlled 0.80, 0.802, and 0.81 fixtures
further show a four-byte prefix increase at each release (1048, 1052, and
1056 bytes respectively) while retaining byte-identical nested sample lists.

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

Known structures include principal volume and panning envelopes, fadeout in
the canonical 0.76 layout, keymaps, mixer-strip fields, and nested sample
records. Some optional instrument-editor and filter/MIDI fields remain unknown.

For the verified 1056-byte Skale 0.81 prefix, the instrument-level Note Death
field is one byte at keymap end + 200 (`name_end + 776`): `0` means Cut and `1`
means Note Off. Controlled saves differing only in that UI choice change
exactly this byte. This field controls instrument behavior and is independent
of the pattern note-value encoding. Its position is not generalized to the
1048- or 1052-byte prefixes.

The compact 412-byte Skale 0.76 prefix stores the same `0`/`1` field at direct
keymap end + 40 (`name_end + 136`), or 276 bytes before its sample list.
Controlled Cut/Note Off saves again differ by exactly that byte. The differing
positions reinforce that the field must be selected by verified structure,
not by the shared `7600` header.

Native single-variable pairs complete the framed-layout mapping:

| Writer/prefix | Note Death field position |
| --- | ---: |
| Skale 0.80 / 1048 bytes | `name_end + 772` = sample list − 276 |
| Skale 0.802 / 1052 bytes | `name_end + 776` = sample list − 276 |
| Skale 0.81 / 1056 bytes | `name_end + 776` = sample list − 280 |

Every Cut base stores `0`; every Note Off save stores `1` and differs from its
base by that byte alone. The 0.81 four-byte addition is after Note Death but
before the nested sample list, explaining why 0.802 and 0.81 share the absolute
field position while their tail-relative positions differ.

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

Embedded Ogg Vorbis is stored as a self-contained stream. All observed streams
have two `FF` padding bytes after Ogg EOS within the stored inner length; a
consumer should validate framing and exclude non-Ogg padding from the decoder.

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
- Two small pattern-record fields and the eight-byte section-2 tail.
- General discriminant for all 0.76 instrument prefix/gap shapes.
- Several sample-header/trailer fields.
- Instrument filter and extended MIDI/remapping state.
- Internal layout of the Skale-owned routing/send tail in section 6.
