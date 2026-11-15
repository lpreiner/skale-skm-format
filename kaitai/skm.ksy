meta:
  id: skm
  title: Skale Tracker SKM module
  file-extension: skm
  endian: le
  license: CC0-1.0
doc: |
  Skale Tracker `.skm` module format. Field names and confidence levels
  match the reference parser `reference/skmparse.py`; the format is
  described in `FORMAT.md` and the evidence in `PROVENANCE.md`.
  https://github.com/lpreiner/skale-skm-format

  Covers every section: the chunk container, file header, song text,
  orders and patterns (including the row-token grammar), instruments for
  record versions 3-6, the VST2 FX chain, the global mixer, and VSTi synth
  records.

  Not covered here, but done by the reference parser: placing track rows at
  their absolute positions (`tokens` are in stored order starting at
  `reserved`), and cross-record checks such as order-list references.

  Source generation is tested for Python, C++ STL, C#, and JavaScript.
seq:
  - id: chunks
    type: chunk
    repeat: until
    repeat-until: _.tag == 0xffff or _io.eof
instances:
  version_raw:
    value: chunks[0].body.as<header_section>.version_raw
    doc: >
      Header version stamp. Skale 0.76, 0.80, 0.802, and 0.81 all write 7600,
      so it cannot select the instrument layout; the instrument chunk ID does.

types:
  chunk:
    doc: |
      The file, and every nested list in it, is a sequence of chunks with
      this 8-byte header. At the top level, `tag` is 0xfffe for the file
      header, 1-6 for a section, or 0xffff (length 0) for the end of the list.
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
      Top-level tag 0xfffe. Observed stamps are 7000, 7100, 7500, and 7600.
    seq:
      - id: magic
        contents: "ALIM3"
      - id: version_raw
        type: u4
        doc: Version × 10000; 7100 is Skale 0.71.
    instances:
      version:
        value: version_raw / 10000.0

  song_text_section:
    doc: |
      Top-level tag 1: the title, an optional NUL separator, the message,
      then a fixed 8-byte trailer. The message has no length field; it is
      whatever lies between the title and the trailer.

      Skale itself also writes a ten-byte zero footer before the trailer.
      It is not a field here, because some valid files have a shorter NUL
      run and reserving ten bytes would truncate their message.
    seq:
      - id: title
        type: strz
        encoding: ISO-8859-1
      - id: text_region
        size: _io.size - _io.pos - 8
        doc: >
          Raw bytes between the title and the trailer: optional separator,
          message, and NUL padding.
      - id: trailer
        type: trailer_t
    instances:
      separator_ok:
        value: text_region.size > 0 and text_region[0] == 0
        doc: True when a NUL separator follows the title.
      message:
        pos: '_io.size - 8 - text_region.size + (separator_ok ? 1 : 0)'
        size: 'text_region.size - (separator_ok ? 1 : 0)'
        type: str
        encoding: ISO-8859-1
        doc: >
          The message, with the separator skipped only if present. Still
          NUL-padded; strip trailing NULs.

  trailer_t:
    doc: Last 8 bytes of section 1.
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
        doc: Copy of the header version.

  patterns_section:
    doc: Top-level tag 2. The order list followed by pattern chunks.
    seq:
      - id: channel_count
        type: u1
      - id: order_list_raw
        size: 256
        doc: >
          Pattern IDs. Only the first `song_length` entries are used; the rest
          is leftover data and may be nonzero.
      - id: song_length
        type: u1
        doc: Number of order entries in use (Skale's SONG LENGTH).
      - id: repeat_pattern
        type: u1
        doc: Order position playback restarts from (Skale's REPEAT PATT.).
      - id: patterns
        type: pattern_chunk(channel_count)
        repeat: until
        repeat-until: _.tag == 0xffff or _io.eof
        doc: Chunk list from offset 0x103, closed by the standard EOF chunk.

  pattern_chunk:
    doc: One pattern, as an ordinary chunk with id 1, tag 1.
    params:
      - id: channel_count
        type: u1
    seq:
      - id: id
        type: u2
      - id: tag
        type: u2
      - id: len
        type: u4
      - id: body
        size: len
        type:
          switch-on: tag
          cases:
            1: pattern_body(channel_count)

  pattern_body:
    params:
      - id: channel_count
        type: u1
    seq:
      - id: pattern_index
        type: u1
      - id: rows
        type: u2
        doc: Row count, 1-256. Skale writes 256 as 00 01.
      - id: tracks
        type: track_chunk
        repeat: until
        repeat-until: _.tag == 0xff or _io.eof
        doc: One track per channel, then an end marker (01 FF 00 00).

  track_chunk:
    doc: Chunk with a 4-byte header (u8 id, u8 tag, u16 length).
    seq:
      - id: id
        type: u1
        valid: 1
      - id: tag
        type: u1
        valid:
          any-of: [1, 0xff]
      - id: len_track
        type: u2
      - id: track
        size: len_track
        type: track
        if: tag == 1

  track:
    seq:
      - id: channel_index
        type: u1
        doc: 0 to channel_count - 1, in order.
      - id: events
        size-eos: true
        type: events_body

  events_body:
    doc: |
      `reserved` is the track's first stored row and `last_row` its last,
      both absolute. `tokens` are in stored order; the consumer places them
      starting at row `reserved` and pads the rest of the pattern.
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
      One row. The marker byte selects the form:

        * `0x80`: empty row.
        * bit 7 set (not 0x80): compressed row. Bits 0-4 flag effect
          command (1 byte), note (1), instrument (1), volume (2), and effect
          parameter (1). Flagged fields follow in that order.
        * bit 7 clear: literal row. The marker is the effect command, and
          note, instrument, volume (2 bytes), and effect parameter always
          follow.

      The `*_effective` instances give one value per field for either form;
      absent fields read as -1.
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
        doc: Plain volume 0-128 when compressed_volume1 is 0 (halve for XM's 0-64).
      - id: compressed_volume1
        type: u1
        if: is_compressed and has_volume
        doc: 0 = plain volume, 0x80 = no volume; other values unknown.
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
          0-95 = C-0 to B-7; 0x81 = Note Off. No other value has been
          observed.
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
        doc: Both volume bytes as one little-endian integer.
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
        doc: Plain volume; halve volume0_effective for XM's 0-64.
      volume_is_absent:
        value: volume1_effective == 128
        doc: No volume; ignore the first byte.
      effect_param_effective:
        value: >
          is_literal ? literal_effect_param.as<s4> :
          (is_compressed and has_effect_param) ? compressed_effect_param.as<s4> : -1

  fx_chain_section:
    doc: |
      Top-level tag 4. A chunk list with one record per FX slot. Tags in
      this list have their own meaning (1 = FX slot), so it has its own
      chunk type.
    seq:
      - id: slots
        type: fx_slot_chunk
        repeat: until
        repeat-until: _.tag == 0xffff or _io.eof

  fx_slot_chunk:
    seq:
      - id: id
        type: u2
        doc: 2 for every populated slot observed.
      - id: tag
        type: u2
        doc: 1 for a slot; 0xffff (length 0) ends the list.
      - id: length
        type: u4
      - id: body
        size: length
        type: fx_slot_record
        if: tag != 0xffff

  fx_slot_record:
    doc: |
      One FX plugin. `slot_index` is the rack slot, not the position in this
      list; empty slots are omitted.
    seq:
      - id: slot_index
        type: u1
        doc: 0-based; UI slot 01 is 0.
      - id: path
        type: strz
        encoding: ISO-8859-1
        doc: >
          Plugin DLL path. Full only when the plugin was loaded from disk in
          that session; after a reload and resave Skale writes the display
          name here instead.
      - id: display_name
        type: strz
        encoding: ISO-8859-1
        doc: The plugin's own name.
      - id: loaded
        type: u1
        doc: 1 in every observed file. Unknown.
      - id: mixer_volume
        type: f4
        doc: FX strip fader.
      - id: wet_or_pan
        type: f4
        doc: Usually 0.5. Probably the FX strip balance.
      - id: bypassed
        type: u1
        doc: 0 enabled, 1 disabled.
      - id: param_count
        type: u4
      - id: params
        type: f4
        repeat: expr
        repeat-expr: param_count
        doc: Plugin parameters, in plugin order.

  vsti_section:
    doc: |
      Top-level tag 6. A chunk list with one record per loaded synth. Empty
      in most files.
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
        doc: 0-based; UI slot 01 is 0.
      - id: path
        type: strz
        encoding: ISO-8859-1
        doc: Same behavior as the FX slot path.
      - id: display_name
        type: strz
        encoding: ISO-8859-1
      - id: plugin_param_count
        type: u4
      - id: plugin_params
        type: f4
        repeat: expr
        repeat-expr: plugin_param_count
      - id: skale_state
        size: 110
        type: vsti_skale_state
        doc: Skale's mixer strip for this synth.
      - id: trailing_bytes
        size-eos: true
        valid:
          expr: _.size == 0
        doc: Must be empty; the mixer strip ends the record.

  vsti_skale_state:
    doc: Skale's 110-byte mixer strip for one synth.
    seq:
      - id: unknown_0
        type: u1
        doc: Always 0.
      - id: send_knobs
        type: vsti_send_knob
        repeat: expr
        repeat-expr: 16
        doc: 16 send knobs. Knob 0 is the strip's first send knob.
      - id: bal
        type: f4
        doc: -0.5 to +0.5, default 0.0.
      - id: volume_fader
        type: f4
        doc: Default 1.0.
      - id: sub_assign
        type: u1
        repeat: expr
        repeat-expr: 4
        doc: SUB1-SUB4 assignment, 0 or 1.
      - id: mute_or_toggle
        type: u1
        doc: The strip's 01 toggle, 0 or 1.

  vsti_send_knob:
    seq:
      - id: flag
        type: u1
      - id: value
        type: f4
      - id: pad
        type: u1

  global_section:
    doc: |
      Top-level tag 5. Two sizes: 4 bytes when the header stamp is below
      7600 (master volume only), 424 bytes when it is 7600 (adds SUB1-4 and
      the FX-bus send matrix at offsets 4-135 and 136-423).
    seq:
      - id: master_volume
        type: f4
        doc: Song master fader. Probable for the 4-byte form.
      - id: mixer
        type: global_mixer_ext
        if: _io.size == 424

  global_mixer_ext:
    seq:
      - id: sub_buses
        type: sub_bus_record
        repeat: expr
        repeat-expr: 4
        doc: SUB1-4, in order.
      - id: fx_bus_matrix
        type: fx_bus_send(_index)
        repeat: expr
        repeat-expr: 32
        doc: 8 source buses × 4 sends.

  sub_bus_record:
    doc: 33 bytes. SUB1-4 share this layout.
    seq:
      - id: flag0
        type: u1
        doc: Usually 0. Unknown; possibly a toggle like knobs[].pad.
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
        doc: Send knobs 01-04, in order.

  sub_bus_knob:
    doc: 6 bytes.
    seq:
      - id: pad
        type: u1
        doc: 1 when the knob's LED is clicked, otherwise 0.
      - id: value
        type: f4
        doc: Default 1.0.
      - id: index
        type: u1
        doc: 0-3, always in order.

  fx_bus_send:
    doc: >
      9 bytes. An FX bus's own fader and balance are in section 4, not here.
    params:
      - id: idx
        type: s4
    seq:
      - id: enabled_flag
        type: u1
        doc: >
          Usually 0, sometimes 1. Unknown; changing the send level alone
          leaves it 0.
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
        doc: -1 means no target.

  instruments_section:
    doc: |
      Top-level tag 3. A chunk list with one record per instrument. The
      chunk ID is the record version.
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
        type: instrument_record(version_raw, id)
        if: tag != 0xffff

  instrument_record:
    doc: |
      Record versions 3/4 have 128 one-byte keymap entries; 5/6 have 128
      framed entries. The settings block is 401, 284, 284, or 288 bytes for
      versions 3-6. The first 96 keymap entries are the playable notes.
      Other versions are kept as raw bytes.
    params:
      - id: version_raw
        type: u4
      - id: record_version
        type: u2
    seq:
      - id: index
        type: u1
      - id: name
        type: strz
        encoding: ISO-8859-1
      - id: direct_keymap
        type: u1
        repeat: expr
        repeat-expr: 128
        if: record_version == 3 or record_version == 4
      - id: framed_keymap
        type: keymap_entry
        repeat: expr
        repeat-expr: 128
        if: record_version == 5 or record_version == 6
      - id: settings
        type: instrument_settings(record_version)
        size: 'record_version == 3 ? 401 : (record_version == 6 ? 288 : 284)'
        if: record_version >= 3 and record_version <= 6
      - id: nested
        type: instrument_nested_list
        if: record_version >= 3 and record_version <= 6
      - id: remainder_raw
        size-eos: true
        if: record_version < 3 or record_version > 6

  keymap_entry:
    doc: |
      Always `00 00` (unmapped) or `01 01 <slot> 00 7F 00` in observed
      files. Read as flag, layer count, and 4-byte layers. The count reading
      is Probable, so layer bytes after the slot are kept raw.
    seq:
      - id: flag
        type: u1
        valid:
          any-of: [0, 1]
      - id: num_layers
        type: u1
        valid:
          expr: (_ > 0) == (flag == 1)
      - id: layers
        type: keymap_layer
        repeat: expr
        repeat-expr: num_layers
    instances:
      mapped:
        value: flag == 1
      local_slot:
        value: 'num_layers > 0 ? layers[0].local_slot : 0'

  keymap_layer:
    seq:
      - id: local_slot
        type: u1
      - id: layer_raw
        size: 3
        doc: Always 00 7F 00.

  instrument_settings:
    doc: Offsets in field names are from the start of the settings block.
    params:
      - id: record_version
        type: u2
    seq:
      - id: fadeout
        type: u2
      - id: unknown_2
        size: 4
      - id: mute_toggle
        type: u1
      - id: toggle01
        type: u1
      - id: note_death
        type: u1
        doc: 0 = Cut, 1 = Note Off.
      - id: volume_fader
        type: f4
      - id: bal
        type: f4
      - id: unknown_17
        size: 8
        doc: Always zero.
      - id: table_25
        size: 64
        doc: >
          Almost always the identity map (entry i == i). The only exceptions
          seen remap entry 7 to 16 or 17. Unknown.
      - id: u8_89
        type: u1
        doc: >
          Start of offsets 89-125, which are probably the instrument filter.
          Defaults are 5000, 5000, 50, 0.5, 0.5, 0, and 10; u8_122 is a bit
          mask. Unknown.
      - id: f32_90
        type: f4
      - id: f32_94
        type: f4
      - id: u8_98
        type: u1
      - id: unknown_99
        size: 3
      - id: f32_102
        type: f4
      - id: f32_106
        type: f4
      - id: f32_110
        type: f4
      - id: f32_114
        type: f4
      - id: f32_118
        type: f4
      - id: u8_122
        type: u1
      - id: unknown_123
        size: 3
      - id: ext_synth_mode
        type: u1
        doc: >
          1 on every VSTi-linked instrument, 0 otherwise. Probable; no save has
          changed it on its own.
      - id: vsti_device
        type: u1
        doc: 0-based section 6 synth slot (Device 01 is 0).
      - id: unknown_128
        size: 2
      # ID 3 (0.70-0.75) tail: 1 + 7 + 1 + 16 x 13 + 54 = 271 bytes.
      - id: legacy_byte_130
        type: u1
        if: record_version == 3
        doc: Always 0xFF.
      - id: legacy_unknown_131
        size: 7
        if: record_version == 3
      - id: legacy_byte_138
        type: u1
        if: record_version == 3
        doc: Always 0x7F.
      - id: legacy_send_knobs
        type: legacy_send_knob
        repeat: expr
        repeat-expr: 16
        if: record_version == 3
      - id: legacy_tail_raw
        size: 54
        if: record_version == 3
        doc: Zero except for u32 value 1 at block offsets 364 and 368.
      # IDs 4-6.
      - id: unknown_130
        size: 2
        if: record_version != 3
      - id: unknown_132
        size: 16
        if: record_version != 3
        doc: Always 0xFF.
      - id: unknown_148
        type: u1
        if: record_version != 3
      - id: vsti_device_enabled
        type: u1
        if: record_version != 3
        doc: The extended editor's device enable light, 0 or 1.
      - id: unknown_150
        size: 2
        if: record_version != 3
      - id: byte_152
        type: u1
        if: record_version != 3
        doc: Almost always 0. Unknown.
      - id: unknown_153
        size: 2
        if: record_version != 3
      - id: byte_155
        type: u1
        if: record_version != 3
        doc: Almost always 0x7F. Unknown.
      - id: send_knobs
        type: send_knob
        repeat: expr
        repeat-expr: 16
        if: record_version != 3
        doc: Knob 0 is the mixer's first send knob; knobs 8-15 have no visible control.
      - id: toggle01_companion
        type: u1
        if: record_version != 3
        doc: Always 1 - toggle01.
      - id: sub_assign
        type: u1
        repeat: expr
        repeat-expr: 4
        if: record_version != 3
      - id: eq
        type: instrument_eq_band
        repeat: expr
        repeat-expr: 3
        if: record_version != 3
      - id: color_bgr
        size: 3
        if: record_version == 6
      - id: color_pad
        type: u1
        if: record_version == 6
    instances:
      u8_126:
        value: ext_synth_mode
      u8_127:
        value: vsti_device

  send_knob:
    seq:
      - id: flag
        type: u1
      - id: value
        type: f4
      - id: index
        type: u1

  legacy_send_knob:
    doc: >
      Record version 3 send knob. flag and value match the same song resaved
      as version 6. aux_a and aux_b are always 0.0 and 1.0.
    seq:
      - id: flag
        type: u1
      - id: value
        type: f4
      - id: aux_a
        type: f4
      - id: aux_b
        type: f4

  instrument_eq_band:
    seq:
      - id: enabled_flag
        type: u1
      - id: gain
        type: f4
      - id: freq
        type: f4

  instrument_nested_list:
    doc: |
      Sample slots (id 1, tag 1) and 32 envelope chunks (tag 2; id 2 in
      record versions 3/4, id 3 in 5/6), closed by EOF.
    seq:
      - id: entries
        type: generic_chunk
        repeat: until
        repeat-until: _.tag == 0xffff or _io.eof

  generic_chunk:
    doc: tag 1 is a sample slot, tag 2 an envelope, tag 0xffff EOF.
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
            1: sample_subchunk
            2: instrument_envelope_subchunk(id)

  instrument_envelope_subchunk:
    doc: |
      One cell of the instrument's 8 × 4 envelope grid. `row` 0-7 is step
      A-H (0 is the active step A). `col` 1-4 is volume, panning, and two
      unidentified envelopes. Length is `9 + 4 * num_points` for chunk id 2
      and `10 + 4 * num_points` for chunk id 3.
    params:
      - id: chunk_id
        type: u2
    seq:
      - id: row
        type: u1
      - id: col
        type: u1
      - id: enabled
        type: u1
      - id: num_points
        type: u1
      - id: points
        type: envelope_point
        repeat: expr
        repeat-expr: num_points
      - id: sustain_enabled
        type: u1
      - id: sustain_point
        type: u1
      - id: loop_enabled
        type: u1
      - id: loop_start
        type: u1
      - id: loop_end
        type: u1
      - id: reserved
        type: u1
        if: chunk_id == 3

  envelope_point:
    seq:
      - id: x
        type: u2
      - id: y
        type: u2

  sample_subchunk:
    doc: Slot number, name, 14 metadata bytes, then an audio chunk list.
    seq:
      - id: local_slot
        type: u1
      - id: name
        type: strz
        encoding: ISO-8859-1
      - id: metadata
        type: sample_metadata
      - id: audio_chunks
        type: sample_audio_chunk
        repeat: until
        repeat-until: _.length == 0 or _io.eof

  sample_audio_chunk:
    doc: |
      A populated slot has one tag 1 audio chunk, then EOF. An empty slot has
      only EOF. EOF header values are kept as read so a validator can check
      them.
    seq:
      - id: format
        type: u2
      - id: tag
        type: u2
      - id: length
        type: u4
      - id: body
        size: length
        type: sample_audio_body
        if: length != 0

  sample_audio_body:
    seq:
      - id: stored_value_count
        type: u4
        doc: Total interleaved values; divide by channels for frames.
      - id: channels
        type: u1
      - id: payload
        size-eos: true
        doc: PCM data, or a u32 Ogg inner length followed by the Ogg stream.
    instances:
      ogg:
        pos: 5
        size: _io.size - 5
        type: ogg_payload
        if: _parent.format == 4

  ogg_payload:
    doc: |
      `inner_length` counts its own four bytes plus the stream, and the
      stream ends at the end of the audio chunk. A validator should require
      inner_length == stream.size + 4, `OggS` magic, and a valid EOF after
      the chunk. This view is lazy, so a bad payload does not stop the rest
      of the file from parsing.
    seq:
      - id: inner_length
        type: u4
      - id: stream
        size-eos: true

  sample_metadata:
    doc: The 14 bytes after a sample's name.
    seq:
      - id: volume
        type: u1
        doc: Shown in hex by Skale. 0x80 is unity, 0x40 half linear gain, 0x00 silent.
      - id: panning
        type: u1
        doc: Shown in hex by Skale. 0x80 is centre, 0x00 hard left; right endpoint untested.
      - id: finetune
        type: s1
      - id: relative_note
        type: s1
      - id: unknown_a
        type: u1
        doc: 8 or 16. Unknown.
      - id: loop_start
        type: u4
        doc: Absolute sample frame.
      - id: loop_end
        type: u4
        doc: Absolute sample frame, not a length.
      - id: loop_type
        type: u1
        enum: sample_loop_type

enums:
  sample_loop_type:
    0: off
    1: forward
    2: ping_pong
  sample_format:
    2: pcm16
    3: pcm8
    4: ogg_vorbis
