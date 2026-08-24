meta:
  id: skm
  title: Skale Tracker SKM module
  file-extension: skm
  endian: le
  license: CC0-1.0
doc: |
  Skale Tracker `.SKM` module format, reverse-engineered by observation only
  (no Skale binary was disassembled, decompiled, or debugged -- see
  `PROVENANCE.md`). Ported from the independent reference parser
  `skmparse.py`; field names and confidence levels below mirror it exactly,
  status as of 2026-08-22. Canonical project:
  https://github.com/lpreiner/skale-skm-format

  Covers: the flat/recursive chunk container, the file header, song text
  (title/message/timing trailer), section 2 (order list, pattern records,
  per-channel tracks, and the confirmed two-mode per-row event grammar),
  section 4 (FX chain), section 5 (global/mixer, both the 4-byte pre-0.76
  and 424-byte shape observed in 0.76), section 3's verified instrument
  variants, and section 6's counted VSTi parameter prefix plus bounded
  Skale-owned routing tail.

  KNOWN GAPS, not yet done (see PROVENANCE.md Sec 6 item 15 for the full
  list with reasoning): a general declarative discriminator for every 0.76
  instrument-prefix variant; the internal structure of section 6's
  Skale-owned routing/send tail; reserved/last_row absolute-row
  padding (tokens here are still track-local, unlike skmparse.py's
  parse_tracks); and skmparse.py's cross-record consistency checks
  (order_list_in_range and friends), which this spec doesn't re-assert.
  Source generation is validated for Python, C++ STL, C#, and JavaScript.
  Generated sources are release artifacts rather than committed files.
seq:
  - id: chunks
    type: chunk
    repeat: until
    repeat-until: _.tag == 0xffff or _io.eof
instances:
  version_raw:
    value: chunks[0].body.as<header_section>.version_raw
    doc: >
      The serialized version stamp. It distinguishes older framing but cannot
      select among all layouts stamped 7600: Skale 0.76, 0.80, 0.802, and
      0.81 produced distinct instrument prefixes under that value.

types:
  chunk:
    doc: |
      The whole file, and every nested list within it (instrument
      sub-chunks, FX-chain slots, ...), is this same 8-byte-header chunk
      repeated. `id` distinguishes binary (1) vs. record/text (3) chunks;
      `tag` is 0xfffe for the one-off file header, 1..6 for a top-level
      section index, or 0xffff for the list's own terminator (length
      always 0).
    seq:
      - id: id
        type: u2
      - id: tag
        type: u2
      - id: length
        type: u4
      - id: body
        size: length
        type:
          switch-on: tag
          cases:
            0xfffe: header_section
            1: song_text_section
            2: patterns_section
            3: instruments_section(_root.version_raw)
            4: fx_chain_section
            5: global_section
            6: vsti_section
    instances:
      section_name:
        value: >
          tag == 0xfffe ? "header" :
          tag == 1 ? "song_text" :
          tag == 2 ? "patterns" :
          tag == 3 ? "instruments" :
          tag == 4 ? "fx_chain" :
          tag == 5 ? "global" :
          tag == 6 ? "section6" :
          tag == 0xffff ? "eof" : "unknown"

  header_section:
    doc: |
      Top-level tag 0xfffe. Verified for files authored with Skale 0.70,
      0.71, 0.75, 0.76, 0.80, 0.802, and 0.81. Observed serialized stamps
      range from 7000 through 7600.
    seq:
      - id: magic
        contents: "ALIM3"
      - id: version_raw
        type: u4
        doc: version * 10000, e.g. 7100 -> Skale 0.71
    instances:
      version:
        value: version_raw / 10000.0

  song_text_section:
    doc: |
      Top-level tag 1. Verified corpus-wide. Layout is front-anchored
      (title, then an optional NUL separator, then a free-text message)
      and back-anchored (a fixed 10-byte zero footer, then an 8-byte
      timing/version trailer) -- `message`'s length is whatever's left
      between them, computed from the chunk's own total size rather than
      a stored length field.
    seq:
      - id: title
        type: strz
        encoding: ISO-8859-1
      - id: separator
        type: u1
        doc: Expected 0 in the canonical layout; see `separator_ok`.
      - id: message
        size: _io.size - _io.pos - 18
        type: str
        encoding: ISO-8859-1
        doc: >
          Raw remaining bytes, NUL-padded to fill the gap before the
          footer -- callers should rstrip trailing \x00 themselves
          (skmparse.py's `canonical_layout` flags files where that padding
          isn't clean, e.g. an embedded NUL mid-message).
      - id: zero_footer
        size: 10
        doc: Fixed 10 zero bytes in the canonical layout (not contents-matched here since a handful of files deviate; see `canonical_layout`).
      - id: trailer
        type: trailer_t
    instances:
      separator_ok:
        value: separator == 0

  trailer_t:
    doc: The 8-byte tail of section 1 -- initial playback timing plus a second, redundant version stamp.
    seq:
      - id: initial_bpm
        type: u1
      - id: initial_speed
        type: u1
      - id: channel_count
        type: u1
      - id: reserved
        type: u1
      - id: version_raw
        type: u4

  patterns_section:
    doc: |
      Top-level tag 2: the order list followed by pattern data. Verified
      byte-exact across the supported corpus (skmparse.py's
      `parse_patterns`/`parse_tracks`/`decode_events`).
    seq:
      - id: channel_count
        type: u1
      - id: order_list_raw
        size: 256
        doc: >
          Pattern indices; only the first `song_length` bytes are real,
          the rest is leftover/uninitialized editor state (not
          necessarily zero -- do not use trailing-zero-stripping to find
          the real length, use `song_length`).
      - id: song_length
        type: u1
        doc: >
          Skale's own "SONG LENGTH" field (confirmed against the live
          GUI, not inferred) -- the authoritative order-list length.
      - id: repeat_pattern
        type: u1
        doc: >
          Skale's "REPEAT PATT." field: the order position to restart at
          after reaching the end of the song.
      - id: pattern_data
        size: _io.size - _io.pos - 8
        type: pattern_data_t(channel_count)
        doc: Everything from offset 0x103 up to the fixed 8-byte section tail.
      - id: tail
        size: 8

  pattern_data_t:
    params:
      - id: channel_count
        type: u1
    seq:
      - id: records
        type: pattern_record(channel_count)
        repeat: eos

  pattern_record:
    doc: |
      One pattern. `next_record = (offset of packed_size) + packed_size + 4`;
      expressed here as a self-sized substream (`tracks_raw`) plus the
      fixed 4-byte trailer, so no manual offset arithmetic is needed.
    params:
      - id: channel_count
        type: u1
    seq:
      - id: signature
        contents: [0x01, 0x00, 0x01, 0x00]
      - id: packed_size
        type: u2
        doc: Counted from this field's own offset.
      - id: reserved1
        type: u2
        doc: Always 0 so far.
      - id: pattern_index
        type: u1
      - id: rows_raw
        type: u1
        doc: On-disk row count; 0 means 256 (u8 overflow -- see `rows`).
      - id: reserved2
        type: u1
        doc: Always 0 so far.
      - id: reserved3
        type: u1
        doc: Always 1 so far.
      - id: reserved4
        type: u1
        doc: Always 1 so far.
      - id: tracks_raw
        size: packed_size - 9
        type: tracks_t(channel_count)
      - id: trailer
        size: 4
        doc: Observed constant 01 ff 00 00; not contents-matched to stay tolerant of an unseen corpus file.
    instances:
      rows:
        value: "rows_raw == 0 ? 256 : rows_raw"
        doc: >
          Confirmed real via a paired .xm export (n_rows=256) with intact,
          decodable content past row 255; Skale's own UI refused to grow a
          maxed-out pattern further, so 256 is a hard ceiling, never a
          larger multiple.

  tracks_t:
    doc: |
      Channel-major, not a flat cell stream: one track per channel, each
      internally self-delimited by its own `length`, with a literal
      `01 01` separator between tracks (absent after the last one).
    params:
      - id: channel_count
        type: u1
    seq:
      - id: entries
        type: track_entry(_index, channel_count)
        repeat: expr
        repeat-expr: channel_count

  track_entry:
    params:
      - id: idx
        type: s4
      - id: total
        type: s4
    seq:
      - id: track
        type: track
      - id: separator
        size: 2
        if: idx < (total - 1)
        doc: Literal 01 01, present between tracks only (not after the last).

  track:
    seq:
      - id: len
        type: u2
      - id: channel_index
        type: u1
        doc: Sequential 0..channel_count-1.
      - id: events
        size: len - 1
        type: events_body

  events_body:
    doc: |
      `decode_events` in skmparse.py. `reserved` is this track's absolute
      starting row and `last_row` its absolute ending row (Verified, 100%
      corpus-wide) -- not consumed here as an offset; `tokens` remains in
      on-the-wire/track-local order and consumers must apply the padding.
    seq:
      - id: last_row
        type: u1
      - id: reserved
        type: u1
      - id: tokens
        type: row_token
        repeat: eos

  row_token:
    doc: |
      One row. Confirmed 2026-08-08 by a live cross-check against a paired
      .xm export -- see PROVENANCE.md §6. Two grammars selected by
      bit7 of `marker`:

        * `marker == 0x80`: empty row, 1 byte, no payload.
        * bit7 set (and marker != 0x80): COMPRESSED row. Low 5 bits of
          `marker` select which fields follow, in ascending bit order:
          bit0=effect_cmd(1B), bit1=note(1B), bit2=instrument(1B),
          bit3=volume(2B), bit4=effect_param(1B). Every set bit's bytes
          are always present (no bit0-dependency on bit4, unlike an
          earlier, disproven model -- see skmparse.py's decode_events
          docstring).
        * bit7 clear: LITERAL row. `marker` itself IS the effect command
          (not a bitmask), unconditionally followed by note(1B),
          instrument(1B), volume(2B), effect_param(1B) -- mirroring XM's
          own packed-cell convention.

      The `*_effective` instances below collapse both grammars into one
      logical field each; unset fields read back as -1.
    seq:
      - id: marker
        type: u1
      - id: compressed_effect_cmd
        type: u1
        if: is_compressed and has_effect_cmd
      - id: compressed_note
        type: u1
        if: is_compressed and has_note
      - id: compressed_instrument
        type: u1
        if: is_compressed and has_instrument
      - id: compressed_volume0
        type: u1
        if: is_compressed and has_volume
        doc: Plain-volume value when compressed_volume1 is 0; range 0..128 maps to tracker volume 0..64.
      - id: compressed_volume1
        type: u1
        if: is_compressed and has_volume
        doc: 0 selects the verified plain-volume family; 0x80 is the verified absent-volume sentinel.
      - id: compressed_effect_param
        type: u1
        if: is_compressed and has_effect_param
      - id: literal_note
        type: u1
        if: is_literal
      - id: literal_instrument
        type: u1
        if: is_literal
      - id: literal_volume0
        type: u1
        if: is_literal
      - id: literal_volume1
        type: u1
        if: is_literal
      - id: literal_effect_param
        type: u1
        if: is_literal
    instances:
      is_empty:
        value: marker == 0x80
      is_compressed:
        value: (marker & 0x80) != 0 and marker != 0x80
      is_literal:
        value: (marker & 0x80) == 0
      has_effect_cmd:
        value: (marker & 0x01) != 0
      has_note:
        value: (marker & 0x02) != 0
      has_instrument:
        value: (marker & 0x04) != 0
      has_volume:
        value: (marker & 0x08) != 0
      has_effect_param:
        value: (marker & 0x10) != 0
      effect_cmd_effective:
        value: >
          is_literal ? marker.as<s4> :
          (is_compressed and has_effect_cmd) ? compressed_effect_cmd.as<s4> : -1
      note_effective:
        doc: >
          Raw on-disk value. 0x81=Note Off (Verified). 0x80 as a *note*
          value remains unidentified and is distinct from `marker`'s own
          0x80, which means "empty row" at the row-token level. The extended
          instrument editor's Note Death Cut/Note Off policy is not evidence
          that this pattern value means Note Cut.
        value: >
          is_literal ? literal_note.as<s4> :
          (is_compressed and has_note) ? compressed_note.as<s4> : -1
      instrument_effective:
        value: >
          is_literal ? literal_instrument.as<s4> :
          (is_compressed and has_instrument) ? compressed_instrument.as<s4> : -1
      volume_effective:
        value: >
          is_literal ? literal_volume0.as<s4> + (literal_volume1.as<s4> << 8) :
          (is_compressed and has_volume) ? compressed_volume0.as<s4> + (compressed_volume1.as<s4> << 8) : -1
        doc: Compatibility view of the two raw bytes as a little-endian integer.
      volume0_effective:
        value: >
          is_literal ? literal_volume0.as<s4> :
          (is_compressed and has_volume) ? compressed_volume0.as<s4> : -1
      volume1_effective:
        value: >
          is_literal ? literal_volume1.as<s4> :
          (is_compressed and has_volume) ? compressed_volume1.as<s4> : -1
      has_plain_volume:
        value: volume1_effective == 0 and volume0_effective >= 0 and volume0_effective <= 128
        doc: Verified ordinary volume family; divide volume0_effective by 2 for a 0..64 tracker volume.
      volume_is_absent:
        value: volume1_effective == 128
        doc: Verified absent-volume sentinel; the varying first byte has no volume-column playback semantics.
      effect_param_effective:
        value: >
          is_literal ? literal_effect_param.as<s4> :
          (is_compressed and has_effect_param) ? compressed_effect_param.as<s4> : -1

  fx_chain_section:
    doc: |
      Top-level tag 4. Verified byte-exact (zero slack) on all FX slots
      corpus-wide -- see PROVENANCE.md §4. Structurally just another
      generic chunk list (the same id/tag/length shape as the top-level
      file), but with its own tag namespace -- a nested tag of 1 here
      means "FX slot record", not "song_text" the way it would at the top
      level, so this uses its own wrapper type (`fx_slot_chunk`) rather
      than reusing the root `chunk` type.
    seq:
      - id: slots
        type: fx_slot_chunk
        repeat: until
        repeat-until: _.tag == 0xffff or _io.eof

  fx_slot_chunk:
    seq:
      - id: id
        type: u2
        doc: Observed 0x0002 for every populated slot.
      - id: tag
        type: u2
        doc: Observed 0x0001 for every populated slot; 0xffff terminates the list (length 0).
      - id: length
        type: u4
      - id: body
        size: length
        type: fx_slot_record
        if: tag != 0xffff

  fx_slot_record:
    doc: |
      One loaded FX-rack plugin. `slot_index` is the plugin's FX-rack
      slot number -- sparse, not "position in this list" (empty slots
      are omitted entirely; non-sequential slot records are observed).
      `param_count` is an explicit on-disk field (unlike section 2's
      pattern records, no offset arithmetic is needed here at all --
      `params`'s length is simply `param_count`).
    seq:
      - id: slot_index
        type: u1
      - id: path
        type: strz
        encoding: ISO-8859-1
        doc: >
          Full path or bare filename to the plugin DLL as seen by the
          authoring install. Per PROVENANCE.md §3, only reliable
          immediately after a fresh browse-load -- Skale itself collapses
          this to `display_name` on the next save, so a format consumer
          can't depend on it surviving a reload.
      - id: display_name
        type: strz
        encoding: ISO-8859-1
        doc: The plugin's own self-reported name (effGetEffectName/effGetProductString).
      - id: loaded
        type: u1
        doc: 0x01 in every instance seen so far; precise semantics remain unstressed.
      - id: mixer_volume
        type: f4
        doc: Skale FX-strip fader. A 0.76 causal probe changed only this field from 0.8 to 3.0.
      - id: wet_or_pan
        type: f4
        doc: Commonly 0.5; observed to vary independently of mixer_volume.
      - id: bypassed
        type: u1
        doc: 0 when enabled and 1 after disabling the effect in the 0.76 causal probe.
      - id: param_count
        type: u4
      - id: params
        type: f4
        repeat: expr
        repeat-expr: param_count
        doc: One float per automatable plugin parameter, in plugin parameter order.

  vsti_section:
    doc: |
      Top-level tag 6. A clean Skale 0.81 mdaJX10 causal family verifies
      one nested record per loaded synth slot. UI slot 01 is stored as
      slot_index 0. Plugin parameters have an explicit count; bytes after
      them are Skale-owned synth routing/send state and remain raw pending
      further causal isolation.
    seq:
      - id: entries
        type: vsti_chunk
        repeat: until
        repeat-until: _.tag == 0xffff or _io.eof

  vsti_chunk:
    seq:
      - id: id
        type: u2
      - id: tag
        type: u2
      - id: length
        type: u4
      - id: body
        size: length
        type: vsti_record
        if: tag != 0xffff

  vsti_record:
    seq:
      - id: slot_index
        type: u1
      - id: path
        type: strz
        encoding: ISO-8859-1
      - id: display_name
        type: strz
        encoding: ISO-8859-1
      - id: plugin_param_count
        type: u4
      - id: plugin_params
        type: f4
        repeat: expr
        repeat-expr: plugin_param_count
      - id: skale_state_raw
        size-eos: true
        doc: Skale-owned per-synth routing/send state; internal structure not yet generalized.

  global_section:
    doc: |
      Top-level tag 5 (global/mixer). Fully Verified by causal Wine-GUI
      drag/save/diff tests -- see PROVENANCE.md §5. Two on-disk
      shapes, distinguished purely by the chunk's own length (already
      known from the enclosing `chunk.length`, so no extra discriminant
      field is needed): 4 bytes on 0.70-0.75 (just `master_volume`), 424
      bytes in observed 0.76 files (adds the 4 SUB1-4 bus records and the FX-bus
      cross-send matrix). `mixer` reads immediately following
      `master_volume` in the same stream, so its own internal offsets
      (SUB buses at 4-135, FX matrix at 136-423) fall out naturally with
      no manual arithmetic.
    seq:
      - id: master_volume
        type: f4
        doc: The overall song master fader (Verified) -- not to be confused with a same-named but unrelated per-plugin VSTi parameter found elsewhere (section 6).
      - id: mixer
        type: global_mixer_ext
        if: _io.size == 424

  global_mixer_ext:
    seq:
      - id: sub_buses
        type: sub_bus_record
        repeat: expr
        repeat-expr: 4
        doc: SUB1-4, in fixed order.
      - id: fx_bus_matrix
        type: fx_bus_send(_index)
        repeat: expr
        repeat-expr: 32
        doc: 8 source buses x 4 send slots each, see fx_bus_send.source_bus/slot.

  sub_bus_record:
    doc: 33 bytes. Every field independently confirmed by an isolated causal drag/click test (PROVENANCE.md §5); SUB2-4 confirmed to share SUB1's exact layout, not just assumed by symmetry.
    seq:
      - id: flag0
        type: u1
        doc: >
          0 normally; its exact semantic role is inferred from `knobs[].pad`'s
          confirmed behavior (same shape, same kind of toggle) rather than
          independently drag-tested -- Probable, not Verified.
      - id: fader
        type: f4
        doc: Default 1.0.
      - id: balance
        type: f4
        doc: Default 0.5.
      - id: knobs
        type: sub_bus_knob
        repeat: expr
        repeat-expr: 4
        doc: One per the mixer's fixed "01".."04" send knobs, label N == 0-based index N-1.

  sub_bus_knob:
    doc: 6 bytes.
    seq:
      - id: pad
        type: u1
        doc: 0 normally, 1 when the knob's own small LED/dot is clicked (Verified).
      - id: value
        type: f4
        doc: Default 1.0.
      - id: index
        type: u1
        doc: 0,1,2,3 -- always in fixed order corpus-wide (unlike the FX matrix's re-routable target_bus).

  fx_bus_send:
    doc: >
      9 bytes. An FX bus's own fader/balance are NOT stored here -- a
      causal test dragging both, once a plugin was loaded into the slot,
      touched section 4's mixer_volume/wet_or_pan fields instead (see
      fx_slot_record), leaving this matrix untouched.
    params:
      - id: idx
        type: s4
    seq:
      - id: enabled_flag
        type: u1
        doc: >
          Named on a corpus-wide hunch, not a causal test (Probable): 0 in
          every untouched corpus slot, but also 0 in this session's own
          causal test after editing send_level, so editing the knob alone
          doesn't set it. Does turn up 1 on real-world songs.
      - id: target_bus_raw
        type: u4
      - id: send_level
        type: f4
    instances:
      source_bus:
        value: idx / 4
      slot:
        value: idx % 4
      target_bus:
        value: "target_bus_raw == 0xffffffff ? -1 : target_bus_raw.as<s4>"
        doc: -1 (from the on-disk 0xffffffff sentinel) means unset.

  instruments_section:
    doc: |
      Top-level tag 3. Per-instrument nested chunk list, same shape as
      `fx_chain_section` -- but, again, `tag`'s meaning here (1 = a real
      instrument record, 0xffff = terminator) is local to this list, so
      it gets its own wrapper type rather than reusing the root `chunk`.
    params:
      - id: version_raw
        type: u4
    seq:
      - id: instruments
        type: instrument_chunk(version_raw)
        repeat: until
        repeat-until: _.tag == 0xffff or _io.eof

  instrument_chunk:
    params:
      - id: version_raw
        type: u4
    seq:
      - id: id
        type: u2
      - id: tag
        type: u2
      - id: length
        type: u4
      - id: body
        size: length
        type: instrument_record(version_raw)
        if: tag != 0xffff

  instrument_record:
    doc: |
      One instrument. Only `index`/`name` (the outer shell) plus, for
      pre-0.76 files, the fixed-size envelope/keymap gap and the nested
      sample-chunk list are decoded here -- see PROVENANCE.md §7.
      0.76 files leave everything past the name as `remainder_raw`: the
      gap there is genuinely one of 8 distinct sizes with no known
      discriminant field yet (not a simple version check, and not a
      smooth per-record continuum either). Rights-safe controlled fixtures
      prove that a 412-byte 0.76 prefix starts with the same direct 96-byte
      keymap used before 0.76, while a 1056-byte 0.76 prefix starts with 96
      framed six-byte entries. Because both carry version_raw 7600, nothing
      past this point can be honestly typed from the version alone; this
      declarative spec keeps it opaque pending a safe layout discriminator.
    params:
      - id: version_raw
        type: u4
    seq:
      - id: index
        type: u1
      - id: name
        type: strz
        encoding: ISO-8859-1
        doc: First/primary sample's name, or the instrument's own name for a sample-less (e.g. VSTi) instrument.
      - id: pre76_keymap
        type: u1
        repeat: expr
        repeat-expr: 96
        if: version_raw != 7600
        doc: >
          Verified direct 96-note note-to-local-sample-slot map used by
          pre-0.76 instruments. Values index the nested sample slots;
          references to empty or absent slots intentionally remain silent.
      - id: pre76_envelope_keymap_remainder_raw
        size: 433
        if: version_raw != 7600
        doc: >
          Remaining undecoded envelope/settings bytes. Together with the
          96-byte keymap this forms the verified fixed 529-byte pre-0.76
          region; the nested chunk list begins immediately afterward.
      - id: nested_pre76
        type: instrument_nested_list
        if: version_raw != 7600
        doc: Sample sub-chunks (id=1/tag=1) plus undecoded param/envelope entries (id=3/tag=2), terminated by the standard EOF chunk.
      - id: remainder_raw
        size-eos: true
        if: version_raw == 7600
        doc: Everything past the name, undecoded. Known 0.76 keymap layouts are documented in this type's docstring but intentionally not guessed here.

  instrument_nested_list:
    doc: The generic id/tag/length chunk-list shape, one more time. Populated sample sub-chunks are decoded; short empty placeholders remain explicit raw tails.
    seq:
      - id: entries
        type: generic_chunk
        repeat: until
        repeat-until: _.tag == 0xffff or _io.eof

  generic_chunk:
    doc: A nested instrument chunk. id=1/tag=1 is a sample slot; other parameter/envelope record families remain raw.
    seq:
      - id: id
        type: u2
      - id: tag
        type: u2
      - id: length
        type: u4
      - id: body
        size: length
        type:
          switch-on: id == 1 and tag == 1
          cases:
            true: sample_subchunk

  sample_subchunk:
    doc: |
      One instrument-local sample slot. Populated records have a verified
      27-byte metadata header, a length-delimited audio payload, and a fixed
      3-byte trailer. Empty placeholders end after a shorter 22-byte tail and
      are deliberately retained rather than forced through the populated form.
    seq:
      - id: local_slot
        type: u1
      - id: name
        type: strz
        encoding: ISO-8859-1
      - id: body
        size-eos: true
        type:
          switch-on: _io.size - _io.pos
          cases:
            22: sample_placeholder
            _: populated_sample_body

  sample_placeholder:
    doc: Undecoded short empty-slot metadata; 22 bytes in every observed instance.
    seq:
      - id: raw
        size-eos: true

  populated_sample_body:
    seq:
      - id: metadata
        type: sample_metadata
      - id: audio_data
        size: metadata.audio_data_length
        doc: Raw PCM data plus its fixed 5-byte inner tail, or the self-contained Ogg length/stream/padding payload.
      - id: trailer
        size: 3
        doc: Fixed record trailer, observed as 00 00 00.

  sample_metadata:
    doc: Verified fixed header immediately following a populated sample name.
    seq:
      - id: volume
        type: u1
        doc: Stored byte is displayed directly in hexadecimal by Skale; 0x80 is unity, 0x40 is one-half linear gain, and 0x00 is silence (Verified).
      - id: panning
        type: u1
        doc: Stored byte is displayed directly in hexadecimal by Skale; 0x80 is center and 0x00 is hard left (Verified). The opposite endpoint is not yet established by a public causal fixture.
      - id: finetune
        type: s1
      - id: relative_note
        type: s1
      - id: unknown_a
        type: u1
      - id: loop_start
        type: u4
        doc: Absolute sample-frame position; full width causally verified with values above 0xffff and below 0x100.
      - id: loop_end
        type: u4
        doc: Absolute sample-frame position, not a loop length.
      - id: loop_type
        type: u1
        enum: sample_loop_type
      - id: format
        type: u2
        enum: sample_format
      - id: unknown_b
        type: u2
        doc: Observed as 1.
      - id: audio_data_length
        type: u4
      - id: stored_value_count
        type: u4
        doc: Total interleaved sample values; divide by channels to obtain the per-channel frame count.
      - id: channels
        type: u1
        doc: Verified values are 1 and 2.

enums:
  sample_loop_type:
    0: off
    1: forward
    2: ping_pong
  sample_format:
    2: pcm16
    3: pcm8
    4: ogg_vorbis
