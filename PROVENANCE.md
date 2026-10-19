<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Public evidence and provenance record

This is the publication-safe evidence index for the SKM format conclusions.
The complete machine-readable record is `tests/fixtures/manifest.json`; its
covered files are identified by the repository-level `CC0-AFFIRMATION.md`.

Sections are numbered for this standalone public document. They summarize the
evidence represented by the public fixture manifest without inheriting the
numbering of the private chronological research journal.

## 1. Song text and timing

Controlled empty and metadata fixtures establish the front/back-anchored song
text layout, initial BPM, speed, channel count, redundant version stamp, and
the visible-comment requirement for a terminating carriage return.

`song-text-short-padding` and `song-text-minimal` establish the consumer-facing
boundary: only the 8-byte trailer is a field a reader may reserve. Reserving the
ten-byte footer truncates messages and rejects structurally valid files, and the
NUL separator is not always present.

## 2. Orders and pattern sizes

Generated fixtures establish authoritative song length, stale unused order
bytes, restart position, sparse/missing pattern identifiers, and row counts 1,
64, 128, and 256.

**Correction (2026-10-19).** The row count is a `u16`, not a `u8` in which 0
means 256. Every 256-row pattern Skale wrote in the private research corpus
stores `00 01` (22/22), and no other pattern has a nonzero high byte. The
synthetic 256-row fixture had been generated as `00 00` under the old reading.
It was regenerated as `00 01`, since it is a template rewrite rather than a
Skale save. Pattern records and their tracks are chunk lists (a full chunk
header per pattern, a half-width `u8 id, u8 tag, u16 length` header per
track, and an EOF/end marker for each list). Every public fixture is consumed
exactly under this reading. The former reserved word, `(0, 1, 1)` bytes,
separators, and trailer are all framing.

## 3. Instruments and samples

Authentic CC0 fixtures establish direct and framed keymaps, empty sample
placeholders, primary envelopes, fadeout, Note Death policy, signed PCM8 and
PCM16, mono/stereo value counts, loop modes, and Ogg framing. Multiple prefix
lengths exist under serialized version 7600; structure must not be selected
from the version stamp alone.

### 3.1 Sample framing

The fixed populated-sample metadata header and payload-size invariant are
cross-checked against deterministic WAV inputs. Stored sample count means total
interleaved values; divide by channel count for frames per channel.

The sample editor displays volume and panning as the stored hexadecimal bytes.
The public volume probe establishes UI/stored `0x80 -> 0x40`; prior playback
evidence establishes `0x80` as unity and `0x40` as one-half linear gain. The
panning probe establishes `0x80` as center and `0x00` as hard left.

### 3.2 Tuning and rate

Paired XM exports support signed relative-note and finetune interpretation.
Raw PCM has no explicit Hertz field in its sample record.

### 3.3 Per-instrument mixer strip

Controlled probes establish fader and BAL values in direct and framed layouts.
A structural recheck on 2026-10-19 explains the apparent four-byte shift:
IDs 4/5 share a 284-byte settings block; ID 6 adds four trailing color/pad bytes.
All three EQ bands are present in ID 5. Universal settings offsets are measured
from the end of 128 serialized keymap entries, rather than 96 playable notes.

### 3.4 Structural consolidation (2026-10-19)

Verified by an independent boundary walk and reference/generated-parser
comparison: IDs 3/4 use 128 direct bytes; IDs 5/6 use 128 variable-length
framed entries. Fixed settings lengths are 401/284/284/288 bytes respectively.
Authentic public keymap fixtures for 0.75, 0.76, 0.80, 0.802, and 0.81 support
these shapes. Synthetic tests cover every observed prefix length and malformed
framed entries; these tests establish consumer behavior rather than new claims
about application output. Broader private corpus correspondence supports the
same model but supplies no new public causal evidence for unknown UI fields.

The sample's 14 metadata bytes precede an audio chunk list. Empty slots hold
EOF alone; populated slots hold one tag=1 audio chunk and EOF. The formerly
unknown tag and apparent audio tails are ordinary chunk framing. Ogg's stored
inner length is self-inclusive (its own four bytes plus the stream); extraction
uses the bounded stream. Existing malformed Ogg fixtures remain structurally inspectable
and fail payload validation. The unknown byte at metadata offset 4 remains raw.

The historical companion field at settings offset 152 is not universally a
boolean (a private record contains 12); it is preserved without assigning new
semantics or rejecting an otherwise valid mixer strip.

### 3.5 Settings skeleton and keymap entries (2026-10-19)

Every byte of the settings blocks is now assigned to a field or a constant
run. The 16 send-knob records are 13 bytes in ID 3 and 6 bytes in IDs 4–6.
A private 0.75 song and its 0.81 resave agree on all 1392 knob flags and
values, and a private causal save places the mixer's first send knob at
knob 0. The probable filter fields and the 64-byte table at `+25` are
described structurally only; no public or private causal save has tied them
to a control. Sample byte `+4` is 8 or 16. In older private files it tracks
bit depth, but freshly authored 0.81 saves always store 8.

Framed keymap entries are read as flag, layer count, and 4-byte layers. The
count interpretation is a conjecture, so unexpected layer bytes are preserved
rather than rejected. Unmapped entries are reported separately from explicit
slot-0 mappings. The authentic 0.80 fixture's single unmapped entry (127) is
the whole difference between its 1048-byte prefix and 0.802's 1052 bytes.
For Ogg, `stored_value_count` equals final granule position × channels in all
private Ogg samples (1032/1032) and in the public Ogg fixtures.

Fadeout at keymap end `+0` matches the instrument fadeout of Skale's own XM
export for every paired private file: 16/16 instruments with 928-byte prefixes
and 11/11 with 1056-byte prefixes. No paired export exists for record IDs 3–5,
so for those versions the field rests on the common settings prefix being
byte-identical across a private 0.75 song and its 0.81 resave.

## 4. FX chain and VSTi state

Rights-safe 0.76 mda Delay and 0.81 mda JX10 causal families now cover FX
parameter, mixer-volume, bypass, synth linkage, pattern-note, and VSTi
parameter changes. They establish zero-based stored slot indices for the
one-based UI slots, an explicit VSTi plugin-parameter count, and the boundary
at which the still-opaque Skale-owned synth routing/send tail begins. The
plugin DLLs were authoring tools only and are not distributed.

## 5. Global mixer

Controlled changes establish the 424-byte 0.76 layout's master volume,
subgroup fader/balance/send records, and FX routing matrix. Earlier files use
the observed four-byte form.

## 6. Pattern events

The public compressed-field matrix covers all 31 non-empty presence masks. A
literal event fixture establishes the second grammar, and an authentic
application-side check confirms note value `0x81` as Note Off. Value `0x80`
remains unidentified.

## 7. Version and prefix compatibility

Authentic application evidence covers Skale 0.70, 0.71, 0.75, 0.76, 0.80,
0.802, and 0.81; the intervening unavailable versions are not claimed as
tested.

Application versions 0.80, 0.802, and 0.81 still serialize version 7600 but
use distinct instrument-prefix lengths. Compatibility probes show that older
applications may warn and discard instruments when encountering later
structures.

## 8. Remaining questions

The open-question list in `FORMAT.md` is authoritative. In particular, text
encoding, pattern note `0x80`, some volume/effect forms, several instrument
regions, and general plugin-owned data remain incomplete.
