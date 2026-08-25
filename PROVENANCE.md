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
64, 128, and 256 (`rows_raw == 0`).

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

Controlled probes establish fader and BAL values in both the framed layout and
the 412-byte direct-keymap layout. The direct layout places these two floats
four bytes later. Other direct-layout mixer fields are not shifted by
inference.

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
