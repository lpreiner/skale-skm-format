#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""
skmparse.py -- reference parser for Skale Tracker .skm modules.

Tested against files written by Skale 0.70, 0.71, 0.75, 0.76, 0.80, 0.802,
and 0.81. The header version is not enough to select a layout: 0.80, 0.802,
and 0.81 all write 7600. See FORMAT.md for the format and PROVENANCE.md for
the evidence.

A file is a sequence of chunks, each with an 8-byte header:

    u16  id
    u16  tag     0xFFFE = file header, 1..6 = section, 0xFFFF = end of list
    u32  length
    u8   payload[length]

Sections, by tag:

    0xFFFE  "ALIM3" + u32 version (version x 10000)
    1       title, message, and initial BPM/speed/channels
    2       order list and patterns
    3       instruments and samples
    4       VST FX chain
    5       master volume, SUB1-4 buses, FX-bus sends
    6       VSTi synths
    0xFFFF  end

Not decoded: non-plain volume-column bytes, the stored scaling of effects
0x10-0x13, sample metadata byte 4, and several instrument settings fields
(see EXAMPLES_NEEDED.md). Raw PCM has no sample-rate field; export derives
one from relative note and finetune unless the caller supplies a rate.
"""

import argparse
import array
import json
import math
import struct
import sys
from pathlib import Path

def _json_default(obj):
    """json.dump hook: write raw bytes as a hex string."""
    if isinstance(obj, (bytes, bytearray)):
        return obj.hex()
    raise TypeError(f"not JSON serializable: {type(obj).__name__}")


HDR = struct.Struct("<HHI")
MAGIC = b"ALIM3"

TAG_HEADER = 0xFFFE
TAG_EOF = 0xFFFF

SECTION_NAMES = {
    TAG_HEADER: "header",
    1: "song_text",
    2: "patterns",
    3: "instruments",
    4: "fx_chain",
    5: "global",
    6: "section6",
    TAG_EOF: "eof",
}


class Chunk:
    __slots__ = ("offset", "id", "tag", "length", "data")

    def __init__(self, offset, cid, tag, length, data):
        self.offset = offset
        self.id = cid
        self.tag = tag
        self.length = length
        self.data = data

    @property
    def name(self):
        return SECTION_NAMES.get(self.tag, f"tag_{self.tag}")

    def __repr__(self):
        return (f"<Chunk @0x{self.offset:X} id=0x{self.id:04X} "
                f"tag=0x{self.tag:04X} len={self.length} ({self.name})>")


def read_chunks(buf, base=0):
    """Walk a buffer as a flat chunk sequence. Stops at EOF tag or exhaustion."""
    chunks = []
    off = 0
    while off + HDR.size <= len(buf):
        cid, tag, length = HDR.unpack_from(buf, off)
        body = off + HDR.size
        if body + length > len(buf):
            raise ValueError(
                f"chunk at 0x{base+off:X} declares length {length} "
                f"which overruns the buffer ({len(buf) - body} available)"
            )
        chunks.append(Chunk(base + off, cid, tag, length, buf[body:body + length]))
        off = body + length
        if tag == TAG_EOF:
            break
    return chunks, off


def cstring(buf, offset=0):
    """Read a NUL-terminated latin-1 string; returns (text, next_offset)."""
    end = buf.find(b"\x00", offset)
    if end < 0:
        end = len(buf)
    return buf[offset:end].decode("latin-1", "replace"), end + 1


def parse_header(chunk):
    if not chunk.data.startswith(MAGIC):
        raise ValueError(f"bad magic {chunk.data[:5]!r}, expected {MAGIC!r}")
    (raw,) = struct.unpack_from("<I", chunk.data, len(MAGIC))
    return {"magic": MAGIC.decode(), "version_raw": raw,
            "version": f"{raw / 10000:.2f}".rstrip("0").rstrip(".")}


def parse_song_text(chunk):
    """
    Parse section 1 (song text).

    Only the last 8 bytes (the timing/version trailer) are a fixed field.
    Before them are the title, an optional NUL separator, the message, and
    NUL padding.

    Skale writes a ten-byte zero footer before the trailer, but some valid
    files have a shorter NUL run, so the message is taken up to the
    trailer and NUL-stripped rather than reserving the footer.
    `zero_footer_raw` reports the ten bytes before the trailer when they
    exist.
    """
    # Minimum: the title's NUL terminator plus the 8-byte trailer.
    if len(chunk.data) < 9:
        raise ValueError(
            "song text chunk is too short for a terminated title and its "
            f"8-byte trailer (got {len(chunk.data)} bytes, need at least 9)")
    text, trailer = chunk.data[:-8], chunk.data[-8:]
    # Reported only when the canonical footer region actually exists.
    zero_footer = chunk.data[-18:-8] if len(chunk.data) >= 18 else None
    initial_bpm, initial_speed, channel_count, reserved, version_raw = \
        struct.unpack("<BBBBI", trailer)
    title, nxt = cstring(text)
    separator_ok = nxt < len(text) and text[nxt] == 0
    message_raw = text[nxt + 1:] if separator_ok else text[nxt:]
    message = message_raw.rstrip(b"\x00").decode("latin-1", "replace")
    padding_length = len(message_raw) - len(message_raw.rstrip(b"\x00"))
    return {
        "title": title.strip(),
        "message": message,
        "initial_bpm": initial_bpm,
        "initial_speed": initial_speed,
        "channel_count": channel_count,
        "reserved": reserved,
        "version_raw": version_raw,
        "zero_footer_raw": zero_footer.hex() if zero_footer is not None else None,
        "padding_length": padding_length,
        "canonical_layout": (
            separator_ok
            and zero_footer == b"\x00" * 10
            and b"\x00" not in message_raw.rstrip(b"\x00")
        ),
        "trailer_raw": trailer.hex(),
    }


# Section 2 pattern records are ordinary (id=1, tag=1, u32 length) chunks
# in a chunk list closed by EOF. PATTERN_SIG is that header's id/tag half.
PATTERN_SIG = b"\x01\x00\x01\x00"
# Tracks inside a pattern use a half-width chunk header:
# u8 id (=1), u8 tag (1 = track, 0xFF = end), u16 length.
TRACK_HDR = struct.Struct("<BBH")
TRACK_TAG = 1
TRACK_TAG_END = 0xFF
TRACK_SEP = b"\x01\x01"  # a track header's id/tag half

# Special note values. 0x81 is Note Off (XM key-off in the paired export).
# NOTE_CUT is kept for API compatibility only: 0x80 does not occur as a note
# under the current row grammar, and nothing shows it means Note Cut.
NOTE_OFF = 0x81
NOTE_CUT = 0x80  # unidentified; do not expose as verified Note Cut semantics


# Compressed row token: marker bit -> field width in bytes. Fields follow
# in ascending bit order.
ROW_FIELD_WIDTH = {0: 1, 1: 1, 2: 1, 3: 2, 4: 1}
ROW_FIELD_NAME = {
    0: "effect_cmd",    # 1 byte
    1: "note",          # 1 byte, XM note number minus 1
    2: "instrument",    # 1 byte
    3: "volume",        # 2 bytes; second byte 00 = plain, 80 = none
    4: "effect_param",  # 1 byte
}


def decode_events(data, offset, length):
    """
    Decode one track's events into per-row values.

        u8   last_row   absolute last stored row
        u8   reserved   absolute first stored row
        row_token[]     one per row from `reserved` to `last_row`

    Each row token starts with a marker byte:

    - 0x80: empty row.
    - bit 7 set: compressed row. Bits 0-4 flag which fields follow, in
      ascending bit order (ROW_FIELD_WIDTH / ROW_FIELD_NAME).
    - bit 7 clear: literal row. The marker is the effect command, and note,
      instrument, volume (2 bytes), and effect param always follow.

    Returns (rows, clean, last_row, reserved). `rows` has one entry per
    stored row (None if empty, else a dict of raw field values), starting
    at `reserved`; `parse_tracks` shifts them to absolute positions.
    `clean` is True when exactly `length` bytes were consumed.
    """
    if length < 2:
        return [], False, None, None
    last_row = data[offset]
    reserved = data[offset + 1]
    pos = offset + 2
    end = offset + length
    rows = []
    while pos < end:
        b = data[pos]
        pos += 1
        if b == 0x80:
            rows.append(None)
            continue
        if b & 0x80:
            cell = {}
            for bit, width in ROW_FIELD_WIDTH.items():
                if not (b & (1 << bit)):
                    continue
                if pos + width > end:
                    return rows, False, last_row, reserved
                val = data[pos] if width == 1 else data[pos:pos + width]
                cell[ROW_FIELD_NAME[bit]] = val
                pos += width
            rows.append(cell)
        else:
            if pos + 5 > end:
                return rows, False, last_row, reserved
            rows.append({
                "effect_cmd": b,
                "note": data[pos],
                "instrument": data[pos + 1],
                "volume": data[pos + 2:pos + 4],
                "effect_param": data[pos + 4],
            })
            pos += 5
    return rows, pos == end, last_row, reserved


def parse_tracks(data, start, end):
    """
    Parse a pattern's tracks: one per channel, as a chunk list with a
    4-byte header.

        u8   id                 always 1
        u8   tag                1 = track, 0xFF = end of list
        u16  length             0 for the end marker
        u8   channel_index      0..channel_count-1, in order
        u8   events[length-1]

    `start` is the first track header; `end` is the end of the pattern
    chunk. Each track's `rows` is padded at the front by `reserved`, so
    `rows[i]` is pattern row `i`. `row_offset_consistent` reports whether
    `reserved + decoded_rows - 1 == last_row`.
    """
    off = start
    tracks = []
    while off + TRACK_HDR.size <= end:
        tid, ttag, ln = TRACK_HDR.unpack_from(data, off)
        off += TRACK_HDR.size
        if tid != 1:
            return tracks, False
        if ttag == TRACK_TAG_END:
            return tracks, ln == 0 and off == end
        if ttag != TRACK_TAG or ln < 1 or off + ln > end:
            return tracks, False
        events_offset = off + 1
        events_length = ln - 1
        decoded, events_clean, last_row, reserved = decode_events(
            data, events_offset, events_length)
        rows = [None] * reserved + decoded if reserved else decoded
        tracks.append({
            "channel": data[off],
            "length": ln,
            "events_offset": events_offset,
            "events_length": events_length,
            "rows": rows,
            "events_clean": events_clean,
            "last_row": last_row,
            "reserved": reserved,
            "row_offset_consistent": (
                reserved is not None and last_row is not None
                and reserved + (len(decoded) - 1) == last_row),
        })
        off += ln
    return tracks, False


def parse_patterns(chunk):
    """
    Parse section 2.

        u8    channel_count
        u8    order_list[256]   pattern IDs; entries past song_length are
                                leftover data and may be nonzero
        u8    song_length       Skale's SONG LENGTH
        u8    repeat_pattern    Skale's REPEAT PATT. order position
        chunk pattern[]         from offset 0x103, closed by EOF

    Each pattern chunk (id 1, tag 1):

        u8    pattern_index
        u16   rows              1-256; Skale writes 256 as 00 01
        track_chunk[]           see parse_tracks
    """
    d = chunk.data
    channels = d[0]
    order_region = d[1:257]
    # Use song_length, not the count of trailing zeros: the last real entry
    # can be pattern 0, and Skale can leave nonzero bytes past the end.
    song_length = d[257] if len(d) >= 259 else 0
    repeat_pattern = d[258] if len(d) >= 259 else 0
    used = min(song_length, len(order_region))
    order = list(order_region[:used])

    records = []
    off = 0x103
    try:
        pattern_chunks, used_bytes = read_chunks(d[off:], base=off)
    except ValueError:
        pattern_chunks, used_bytes = [], 0
    clean = bool(pattern_chunks) and pattern_chunks[-1].tag == TAG_EOF \
        and pattern_chunks[-1].id == 1 and pattern_chunks[-1].length == 0
    for pc in pattern_chunks:
        if pc.tag == TAG_EOF:
            break
        if pc.id != 1 or pc.tag != 1 or pc.length < 3:
            clean = False
            break
        body = pc.offset + HDR.size  # offset within section 2's payload
        data_end = body + pc.length
        tracks, tracks_clean = parse_tracks(d, body + 3, data_end)
        # u16 row count. Skale never writes 0; it is reported as-is.
        rows_raw = struct.unpack_from("<H", d, body + 1)[0]
        rows = rows_raw
        # Trailing empty rows are not stored; pad each track to `rows`.
        for tr in tracks:
            if len(tr["rows"]) < rows:
                tr["rows"] = tr["rows"] + [None] * (rows - len(tr["rows"]))
        records.append({
            "offset": pc.offset,
            "index": d[body],
            "rows": rows,
            "rows_raw": rows_raw,
            "length": pc.length,
            "packed_size": pc.length,  # alias of length, kept for compatibility
            "data_offset": body + 3,   # first track-chunk header
            "track_count": len(tracks),
            "tracks_clean": tracks_clean and len(tracks) == channels,
            "tracks": tracks,
        })
    off += used_bytes
    clean = clean and off == len(d)

    return {
        "channel_count": channels,
        "song_length": song_length,
        "repeat_pattern": repeat_pattern,
        "order_list_used": used,
        "order_list": order,
        "unique_patterns": sorted(set(order)),
        "pattern_count": len(records),
        "rows_seen": sorted({r["rows"] for r in records}),
        "indices_sequential": [r["index"] for r in records] == list(range(len(records))),
        "walk_clean": clean,
        "all_tracks_clean": all(r["tracks_clean"] for r in records) if records else None,
        # Pattern IDs can have gaps, so check against the set of IDs present
        # rather than the record count. Skale can save an order entry that
        # names a missing pattern.
        "order_list_in_range": all(idx in {r["index"] for r in records} for idx in order),
        "trailing_bytes": len(d) - off,
        "patterns": records,
    }


# Default window for locate_sample_list, in bytes past `start`.
# parse_instruments passes the whole record instead.
SAMPLE_LIST_SEARCH_WINDOW = 4096


LOOP_TYPES = {0: "off", 1: "forward", 2: "ping-pong"}

# Audio chunk id -> format. For PCM, the audio chunk length is
# value_count * BYTES_PER_SAMPLE + 5 (the u32 count and u8 channels).
# Ogg holds a u32 inner length and an OggS stream instead.
SAMPLE_FORMATS = {2: "pcm16", 3: "pcm8", 4: "ogg"}
BYTES_PER_SAMPLE = {2: 2, 3: 1}



def _sample_subchunk_size_exact(sd):
    """Check bounded inner audio chunks and EOF framing, including empty slots.

    EOF values are validated separately so malformed payload fixtures remain
    inspectable; lengths must account for every byte.
    """
    _, n = cstring(sd, 1)
    at = n + 14
    if at + HDR.size > len(sd):
        return False
    while at + HDR.size <= len(sd):
        cid, tag, length = HDR.unpack_from(sd, at)
        at += HDR.size
        if at == len(sd) and length == 0:
            return True
        if tag != 1 or cid not in SAMPLE_FORMATS or length < 5:
            return False
        at += length
    return False


def locate_sample_list(data, start, window=SAMPLE_LIST_SEARCH_WINDOW):
    """
    Fallback for unknown record versions: scan for the start of the
    instrument's nested chunk list.

    A candidate must start with a sample, envelope, or EOF header, read
    exactly to the end of the record, and end in EOF. Mostly-zero keymap
    bytes can also parse as a short valid list, so every sample in the
    candidate must also pass the audio-chunk size check. Returns None if no
    candidate qualifies.
    """
    limit = min(start + window, len(data) - HDR.size + 1)
    for off in range(start, limit):
        cid, tag, length = HDR.unpack_from(data, off)
        if (cid, tag) not in ((1, 1), (2, 2), (3, 2), (1, TAG_EOF)):
            continue
        if off + HDR.size + length > len(data):
            continue
        try:
            sub, consumed = read_chunks(data[off:])
        except Exception:
            continue
        if not (consumed == len(data) - off and sub and sub[-1].tag == TAG_EOF):
            continue
        if any(_sample_subchunk_size_exact(s.data) is False
               for s in sub if s.id == 1 and s.tag == 1):
            continue
        return off
    return None


def parse_sample_subchunk(rec):
    """
    Parse one sample slot (nested chunk id 1, tag 1): slot number, name,
    14 metadata bytes, then an audio chunk and EOF. Metadata byte +4 is
    unknown.
    """
    d = rec.data
    name, n2 = cstring(d, 1)
    if n2 + 13 >= len(d):
        return {"name": name, "record_len": rec.length,
                "error": "too short for the known fixed fields"}
    loop_type_raw = d[n2 + 13]
    out = {
        "local_slot": d[0],
        "name": name,
        "volume": d[n2],
        "volume_raw": d[n2],
        # Shown in hex by Skale. 0x80 is unity, 0x40 half gain.
        "volume_gain": d[n2] / 128.0,
        "panning": d[n2 + 1],
        "panning_raw": d[n2 + 1],
        # Signed, as in XM; Skale's XM export copies these bytes unchanged.
        "finetune": struct.unpack_from("<b", d, n2 + 2)[0],
        "relative_note": struct.unpack_from("<b", d, n2 + 3)[0],
        "unknown_a": d[n2 + 4],
        # Absolute sample frames, full u32.
        "loop_start": struct.unpack_from("<I", d, n2 + 5)[0],
        "loop_end": struct.unpack_from("<I", d, n2 + 9)[0],
        "loop_type": LOOP_TYPES.get(loop_type_raw, loop_type_raw),
        "record_len": rec.length,
    }
    out["size_exact"] = _sample_subchunk_size_exact(d) is True
    audio_header = n2 + 14
    if audio_header + HDR.size > len(d):
        out["audio_located"] = False
        return out
    format_raw, tag, audio_chunk_length = HDR.unpack_from(d, audio_header)
    if tag == TAG_EOF and audio_chunk_length == 0:
        out.update(audio_located=False, empty_slot=True)
        return out
    if tag != 1 or format_raw not in SAMPLE_FORMATS or audio_chunk_length < 5:
        out["audio_located"] = False
        return out
    body = audio_header + HDR.size
    audio_end = body + audio_chunk_length
    if audio_end + HDR.size != len(d):
        out["audio_located"] = False
        return out
    stored_value_count, channels = struct.unpack_from("<IB", d, body)
    out.update({
        "format": SAMPLE_FORMATS.get(format_raw, format_raw),
        "format_raw": format_raw,
        "audio_chunk_tag": tag,
        "audio_chunk_length": audio_chunk_length,
        "stored_value_count": stored_value_count,
        "frame_count_per_channel": (
            stored_value_count // channels
            if channels and stored_value_count % channels == 0 else None
        ),
        "frames": stored_value_count,  # compatibility alias
        "channels": channels,
        # Compatibility alias; includes the 5-byte count/channels prefix.
        "audio_data_length": audio_chunk_length,
        "audio_payload_length": audio_chunk_length - 5,
        "audio_data_offset": rec.offset + HDR.size + body + 5,
        "audio_eof_valid": d[audio_end:] == HDR.pack(1, TAG_EOF, 0),
        "audio_located": True,
    })
    return out


ENVELOPE_STEPS = ("A", "B", "C", "D", "E", "F", "G", "H")
ENVELOPE_TYPES = {
    1: "volume",
    2: "panning",
    3: "col3",
    4: "col4",
}


def parse_envelope_subchunk(rec):
    """Decode one envelope chunk (tag 2, id 2 or 3).

    Each instrument has 32, forming an 8 x 4 grid: row 0-7 is step A-H,
    col 1-4 is volume, panning, and two unidentified envelopes. Length is
    `9 + 4*num_points` for id 2 and `10 + 4*num_points` for id 3.
    Returns None if the chunk is malformed.
    """
    d = rec.data
    if rec.tag != 2 or rec.id not in (2, 3) or len(d) < 9:
        return None
    row, col, enabled, count = d[0], d[1], d[2], d[3]
    expected_len = (9 if rec.id == 2 else 10) + 4 * count
    if (row not in range(8) or col not in (1, 2, 3, 4)
            or enabled not in (0, 1) or count > 12
            or len(d) != expected_len):
        return None
    points = [struct.unpack_from("<HH", d, 4 + 4 * i) for i in range(count)]
    if (any(y > 64 for _, y in points)
            or any(points[i][0] > points[i + 1][0]
                   for i in range(len(points) - 1))):
        return None
    tail = 4 + 4 * count
    sustain_enabled, sustain_point, loop_enabled, loop_start, loop_end = d[tail:tail + 5]
    reserved = d[tail + 5] if rec.id == 3 else 0
    if (sustain_enabled not in (0, 1) or loop_enabled not in (0, 1)
            or reserved != 0
            or (sustain_enabled and sustain_point >= count)
            or (loop_enabled and (loop_start >= count or loop_end >= count
                                  or loop_start > loop_end))):
        return None
    return {
        "row": row,
        "step": ENVELOPE_STEPS[row],
        "col": col,
        "type": ENVELOPE_TYPES[col],
        "enabled": bool(enabled),
        "points": points,
        "sustain_enabled": bool(sustain_enabled),
        "sustain_point": sustain_point,
        "loop_enabled": bool(loop_enabled),
        "loop_start": loop_start,
        "loop_end": loop_end,
        "reserved": reserved,
    }


def parse_instrument_envelope(rec):
    """Decode a main (step A) volume/panning envelope parameter record.

    Main envelopes are row 0, type 1 (volume) or 2 (panning), and have a
    self-describing variable point count. Returns None for other records or
    for malformed envelope state.
    """
    d = rec.data
    if len(d) < 9 or d[0] != 0 or d[1] not in (1, 2) or d[2] not in (0, 1):
        return None
    count = d[3]
    core_length = 9 + 4 * count
    if count > 12 or len(d) not in (core_length, core_length + 1):
        return None
    points = [struct.unpack_from("<HH", d, 4 + 4 * i) for i in range(count)]
    if (any(y > 64 for _, y in points)
            or any(points[i][0] > points[i + 1][0]
                   for i in range(len(points) - 1))):
        return None
    tail = 4 + 4 * count
    sustain_enabled, sustain_point, loop_enabled, loop_start, loop_end = d[tail:tail + 5]
    reserved = d[tail + 5] if len(d) == core_length + 1 else 0
    if (sustain_enabled not in (0, 1) or loop_enabled not in (0, 1)
            or reserved != 0
            or (sustain_enabled and sustain_point >= count)
            or (loop_enabled and (loop_start >= count or loop_end >= count
                                  or loop_start > loop_end))):
        return None
    return {
        "type": "volume" if d[1] == 1 else "panning",
        "enabled": bool(d[2]),
        "points": points,
        "sustain_enabled": bool(sustain_enabled),
        "sustain_point": sustain_point,
        "loop_enabled": bool(loop_enabled),
        "loop_start": loop_start,
        "loop_end": loop_end,
    }


def extract_pcm_samples(raw, sample):
    """
    Read a PCM sample (format 2 or 3) into an array.array of signed
    values: 16-bit little-endian, or 8-bit. `raw` is the whole file;
    `sample` comes from parse_sample_subchunk. Values are interleaved
    for stereo.

    Raises ValueError if `sample` is not a located PCM sample or the data
    is shorter than its stored value count.
    """
    fmt = sample.get("format_raw")
    if fmt not in BYTES_PER_SAMPLE:
        raise ValueError(f"not a raw-PCM sample (format={sample.get('format')!r})")
    bps = BYTES_PER_SAMPLE[fmt]
    n_bytes = sample["frames"] * bps
    if n_bytes != sample["audio_payload_length"]:
        raise ValueError("PCM value count does not match bounded audio payload")
    off = sample["audio_data_offset"]
    data = raw[off:off + n_bytes]
    if len(data) != n_bytes:
        raise ValueError(
            f"truncated PCM data: wanted {n_bytes} bytes at offset {off}, "
            f"got {len(data)}")
    arr = array.array("h" if fmt == 2 else "b")
    arr.frombytes(data)
    if fmt == 2 and sys.byteorder == "big":
        arr.byteswap()
    return arr


def extract_ogg_stream(raw, sample):
    """Return the Ogg stream from an Ogg sample's audio chunk.

    The inner u32 length counts its own four bytes plus the stream.
    Raises ValueError if the length, EOF header, or OggS magic is wrong.
    """
    if sample.get("format_raw") != 4:
        raise ValueError(f"not an Ogg sample (format={sample.get('format')!r})")
    off = sample["audio_data_offset"]
    length = sample["audio_payload_length"]
    payload = raw[off:off + length]
    if len(payload) != length or length < 4:
        raise ValueError("truncated Ogg payload")
    inner_len = struct.unpack_from("<I", payload)[0]
    if inner_len != length:
        raise ValueError("self-inclusive inner Ogg length does not match the bounded payload")
    if not sample.get("audio_eof_valid"):
        raise ValueError("invalid audio EOF header (formerly Ogg padding)")
    stream = payload[4:]
    if stream[:4] != b"OggS":
        raise ValueError(f"expected OggS magic, got {stream[:4]!r}")
    return stream


XM_C4_REFERENCE_HZ = 8363.0  # XM's reference rate

def native_sample_rate(sample):
    """
    Sample rate in Hz from relative note and finetune, using XM's formula:
    `8363 * 2**((relative_note + finetune/128) / 12)`. Skale's XM export
    copies both bytes unchanged, so XM's reference applies. For known
    44100 and 22050 Hz sources the result is within 0.02%.
    """
    exponent = (sample["relative_note"] + sample["finetune"] / 128) / 12
    return XM_C4_REFERENCE_HZ * (2 ** exponent)


def export_sample(raw, sample, out_path, sample_rate=None):
    """
    Write a sample to `out_path`: the Ogg stream as-is for format 4, or a
    WAV file for PCM. `sample_rate` defaults to native_sample_rate(sample).
    """
    if sample.get("format_raw") == 4:
        Path(out_path).write_bytes(extract_ogg_stream(raw, sample))
        return
    if sample_rate is None:
        sample_rate = round(native_sample_rate(sample))
    import wave
    arr = extract_pcm_samples(raw, sample)
    bps = BYTES_PER_SAMPLE[sample["format_raw"]]
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(sample.get("channels") or 1)
        w.setsampwidth(bps)
        w.setframerate(sample_rate)
        # WAV PCM8 is unsigned while SKM PCM8 is signed. Python's wave module
        # writes bytes verbatim, so restore the WAV bias during export.
        frames = arr.tobytes() if bps == 2 else bytes((v + 128) & 0xFF for v in arr)
        w.writeframes(frames)


def parse_mixer_strip(data, sample_list_start, prefix_len, record_version=None):
    """Decode an instrument's mixer strip from its settings block.

    Record versions 4-6 only. IDs 4/5 have a 284-byte block; ID 6 adds BGR
    colour and a pad. Returns None for ID 3 or implausible values.
    """
    if record_version not in (4, 5, 6):
        return None
    base = sample_list_start - (288 if record_version == 6 else 284)
    def flag(off):
        return data[base + off]
    def f32(off):
        return struct.unpack_from("<f", data, base + off)[0]
    def eq_band(off):
        return {"enabled_flag": flag(off), "gain": f32(off + 1),
                "freq": f32(off + 5)}
    flags = [flag(7), flag(252)] + [flag(o) for o in range(253, 257)]
    flags += [flag(o) for o in (257, 266, 275)]
    if any(v not in (0, 1) for v in flags):
        return None
    volume, bal = f32(9), f32(13)
    if not math.isfinite(volume) or volume < 0 or not math.isfinite(bal) or not -0.5 <= bal <= 0.5:
        return None
    out = {
        "layout": "direct-412" if record_version == 4 else "framed",
        "toggle01": flag(7),
        # Always 1 - toggle01.
        "toggle01_companion": flag(252),
        "volume_fader": volume, "bal": bal,
        "sub_assign": [flag(o) for o in range(253, 257)],
        "eq_l": eq_band(257), "eq_m": eq_band(266), "eq_h": eq_band(275),
    }
    if record_version == 6:
        out["color_bgr"] = list(data[base + 284:base + 287])
        out["color_pad"] = flag(287)
    return out


def parse_settings_block(settings, record_version):
    """Decode the settings block that follows the keymap.

    The first 130 bytes are laid out the same in IDs 3-6. The 16 send
    knobs are 13-byte records in ID 3 (flag, f32 value, f32 0.0, f32 1.0)
    and 6-byte records in IDs 4-6 (flag, f32 value, u8 index). Offsets 126,
    127, and (IDs 4-6) 149 link the instrument to a section 6 synth.
    """
    f32 = lambda off: struct.unpack_from("<f", settings, off)[0]
    if record_version == 3:
        knobs = [{"flag": settings[o], "value": f32(o + 1),
                  "aux": (f32(o + 5), f32(o + 9))}
                 for o in range(139, 139 + 16 * 13, 13)]
    else:
        knobs = [{"flag": settings[o], "value": f32(o + 1),
                  "index": settings[o + 5]}
                 for o in range(156, 156 + 16 * 6, 6)]
    out = {
        "send_knobs": knobs,
        # Almost always the identity map. Unknown.
        "table_25": list(settings[25:89]),
        # 126: 1 on VSTi-linked instruments (Probable).
        # 127: 0-based section 6 synth slot (Device 01 is 0).
        "ext_synth_mode": settings[126],
        "vsti_device": settings[127],
        # Probably the instrument filter. Defaults 5000, 5000, 50, 0.5,
        # 0.5, 0, 10. Unknown.
        "unidentified": {
            "u8_89": settings[89], "f32_90": f32(90), "f32_94": f32(94),
            "u8_98": settings[98], "f32_102": f32(102), "f32_106": f32(106),
            "f32_110": f32(110), "f32_114": f32(114), "f32_118": f32(118),
            "u8_122": settings[122], "u8_126": settings[126],
            "u8_127": settings[127],
        },
    }
    if record_version == 3:
        out["legacy_byte_130"] = settings[130]
        out["legacy_byte_138"] = settings[138]
    else:
        out["vsti_device_enabled"] = settings[149]
        out["byte_152"] = settings[152]
        out["byte_155"] = settings[155]
    return out


def instrument_prefix(data, name_end, record_version):
    """Return (128 local slots, keymap end, nested-list start, entries), or None.

    IDs 3/4 have one byte per keymap entry; IDs 5/6 have framed entries,
    read as `u8 flag, u8 layer_count, layer[layer_count]` with 4-byte
    layers. Every observed framed entry is `00 00` (unmapped) or
    `01 01 <slot> 00 7F 00`. The count reading is Probable, so other layer
    bytes are kept rather than rejected. Unmapped entries are slot 0 in the
    slot list and None in `entries`. Returns None for other record versions.
    """
    if record_version not in (3, 4, 5, 6):
        return None
    pos = name_end
    slots = []
    entries = None
    if record_version in (3, 4):
        if pos + 128 > len(data):
            raise ValueError("truncated direct keymap")
        slots = list(data[pos:pos + 128])
        pos += 128
    else:
        entries = []
        for _ in range(128):
            if pos + 2 > len(data):
                raise ValueError("truncated framed keymap entry")
            flag, count = data[pos], data[pos + 1]
            if flag not in (0, 1) or (flag == 1) != (count > 0):
                raise ValueError("invalid framed keymap entry header")
            end = pos + 2 + 4 * count
            if end > len(data):
                raise ValueError("truncated framed keymap entry")
            layers = [tuple(data[at:at + 4]) for at in range(pos + 2, end, 4)]
            entries.append(layers or None)
            slots.append(layers[0][0] if layers else 0)
            pos = end
    start = pos + {3: 401, 4: 284, 5: 284, 6: 288}[record_version]
    if start + HDR.size > len(data):
        raise ValueError("truncated instrument settings or nested list")
    return slots, pos, start, entries


def parse_instruments(chunk, version_raw=None):
    """Parse section 3. The instrument chunk ID is the record version.

    IDs 3-6 are read directly. For other IDs the nested list is found by
    locate_sample_list, `prefix_source` says so, and no keymap or mixer
    fields are reported.
    """
    records, consumed = read_chunks(chunk.data, base=chunk.offset + HDR.size)
    out = []
    for rec in records:
        if rec.tag == TAG_EOF or not rec.data:
            continue
        index = rec.data[0]
        name, nxt = cstring(rec.data, 1)
        entry = {
            "index": index,
            "name": name,
            "record_len": rec.length,
            "record_offset": rec.offset,
        }
        if nxt < len(rec.data):
            prefix = instrument_prefix(rec.data, nxt, rec.id)
            start = prefix[2] if prefix else locate_sample_list(
                rec.data, nxt, window=len(rec.data))
            entry["record_version"] = rec.id
            entry["prefix_source"] = "record-version" if prefix else "structural-search"
            if start is not None:
                nested, used = read_chunks(rec.data[start:])
                if (used != len(rec.data) - start or not nested
                        or nested[-1].tag != TAG_EOF
                        or any(_sample_subchunk_size_exact(sc.data) is False
                               for sc in nested if sc.id == 1 and sc.tag == 1)):
                    raise ValueError("invalid instrument nested list")
            entry["internals_located"] = start is not None
            if start is not None:
                prefix_len = start - nxt
                if prefix:
                    slots, keymap_end, _, framed = prefix
                    entry["keymap"] = slots[:96]  # playable-note compatibility view
                    entry["keymap_all_slots"] = slots
                    if framed is not None:
                        # Distinguishes `00 00` (unmapped) from an explicit
                        # mapping to local slot 0, which both read as 0 above.
                        entry["keymap_mapped"] = [e is not None for e in framed]
                        nonstandard = [
                            (note, e) for note, e in enumerate(framed)
                            if e is not None and (len(e) != 1 or e[0][1:] != (0, 0x7F, 0))]
                        if nonstandard:
                            entry["keymap_nonstandard_entries"] = nonstandard
                    entry["keymap_layout"] = ("direct-96-byte" if rec.id in (3, 4)
                                               else "framed-6-byte")
                    entry["keymap_end"] = rec.offset + HDR.size + keymap_end
                    entry["prefix_length"] = prefix_len
                    entry["post_keymap_length"] = start - keymap_end
                    entry["settings_raw"] = rec.data[keymap_end:start]
                    entry["settings"] = parse_settings_block(
                        entry["settings_raw"], rec.id)
                    entry["mute_toggle_raw"] = rec.data[keymap_end + 6]
                    entry["fadeout"] = struct.unpack_from("<H", rec.data, keymap_end)[0]
                    note_death = rec.data[keymap_end + 8]
                    entry["note_death_raw"] = note_death
                    entry["note_death"] = {0: "cut", 1: "note-off"}.get(note_death, "unknown")
                    entry["mixer_strip"] = parse_mixer_strip(
                        rec.data, start, prefix_len, rec.id)
                sub, _ = read_chunks(rec.data[start:],
                                      base=rec.offset + HDR.size + start)
                samples = []
                envelopes = {}
                envelope_grid = []
                other_subchunks = 0
                non_sample_subchunks = 0
                for s in sub:
                    if s.tag == TAG_EOF:
                        continue
                    if s.id == 1 and s.tag == 1:
                        samples.append(parse_sample_subchunk(s))
                    else:
                        non_sample_subchunks += 1
                        grid_env = parse_envelope_subchunk(s)
                        if grid_env is not None:
                            envelope_grid.append(grid_env)
                        envelope = (parse_instrument_envelope(s)
                                    if s.id in (2, 3) and s.tag == 2 else None)
                        if envelope is not None:
                            envelopes[envelope["type"]] = envelope
                        else:
                            other_subchunks += 1
                entry["samples"] = samples
                entry["envelopes"] = envelopes
                entry["envelope_grid"] = envelope_grid
                entry["envelope_grid_exact"] = (
                    len(envelope_grid) == 32
                    and non_sample_subchunks == 32
                    and [(e["row"], e["col"]) for e in envelope_grid]
                    == [(r, c) for r in range(8) for c in range(1, 5)]
                )
                entry["other_subchunks"] = other_subchunks
        else:
            entry["internals_located"] = False
        out.append(entry)
    return {"count": len(out), "bytes_consumed": consumed, "instruments": out}


def parse_fx_slot(rec):
    """
    Parse one FX slot record.

        u8    slot_index            0-based rack slot; empty slots omitted
        cstr  path                  plugin DLL path
        cstr  display_name          plugin's own name
        u8    loaded                always 1 so far
        f32   mixer_volume          FX strip fader, not limited to 0-1
        f32   wet_or_pan            usually 0.5; probably balance
        u8    bypassed              0 enabled, 1 disabled
        u32   param_count
        f32   params[param_count]
    """
    d = rec.data
    slot_index = d[0]
    path, n1 = cstring(d, 1)
    name, n2 = cstring(d, n1)
    loaded = d[n2]
    mixer_volume, wet_or_pan = struct.unpack_from("<ff", d, n2 + 1)
    bypassed = d[n2 + 9]
    (param_count,) = struct.unpack_from("<I", d, n2 + 10)
    params_off = n2 + 14
    params = list(struct.unpack_from(f"<{param_count}f", d, params_off))
    consumed = params_off + param_count * 4
    return {
        "slot_index": slot_index,
        "path": path,
        "display_name": name,
        "loaded": loaded,
        "mixer_volume": mixer_volume,
        # Older names, kept for compatibility.
        "enabled": loaded,
        "dry_wet": mixer_volume,
        "wet_or_pan": wet_or_pan,
        "bypassed": bypassed,
        "reserved": bypassed,
        "param_count": param_count,
        "params": params,
        "exact": consumed == len(d),
    }


def parse_fx_chain(chunk):
    """Parse section 4: one chunk (id 2, tag 1) per FX plugin, then EOF."""
    recs, consumed = read_chunks(chunk.data, base=chunk.offset + HDR.size)
    slots = []
    for rec in recs:
        if rec.tag == TAG_EOF or not rec.data:
            continue
        try:
            slots.append(parse_fx_slot(rec))
        except (struct.error, IndexError) as exc:
            slots.append({"error": f"{type(exc).__name__}: {exc}",
                          "record_offset": rec.offset, "record_len": rec.length})
    dlls = [s["path"] for s in slots if "path" in s]
    return {"bytes_consumed": consumed, "slots": slots, "plugins": dlls}


def parse_vsti_skale_state(raw):
    """Decode the 110-byte mixer strip at the end of a section 6 synth record.

        offset 0       u8    unknown_0 (always 0)
        offset 1..96   16x   send_knob (u8 flag, f32 value, u8 pad)
        offset 97..100 f32   bal (zero-centered in [-0.5, +0.5], default 0.0)
        offset 101..104 f32  volume_fader (default 1.0)
        offset 105..108 u8[4] sub_assign (SUB1..SUB4 routing flags in {0, 1})
        offset 109     u8    mute_or_toggle (in {0, 1}, default 0)

    Returns None if the length or any value is out of range.
    """
    if len(raw) != 110:
        return None
    unknown_0 = raw[0]
    knobs = []
    for i in range(16):
        off = 1 + 6 * i
        flag = raw[off]
        val = struct.unpack_from("<f", raw, off + 1)[0]
        pad = raw[off + 5]
        if flag not in (0, 1) or pad != 0 or not math.isfinite(val):
            return None
        knobs.append({"flag": flag, "value": val, "pad": pad})
    bal, volume_fader = struct.unpack_from("<ff", raw, 97)
    sub_assign = list(raw[105:109])
    mute_or_toggle = raw[109]
    if (unknown_0 != 0
            or not math.isfinite(bal) or not -0.5 <= bal <= 0.5
            or not math.isfinite(volume_fader) or volume_fader < 0
            or any(b not in (0, 1) for b in sub_assign)
            or mute_or_toggle not in (0, 1)):
        return None
    return {
        "unknown_0": unknown_0,
        "send_knobs": knobs,
        "bal": bal,
        "volume_fader": volume_fader,
        "sub_assign": sub_assign,
        "mute_or_toggle": mute_or_toggle,
    }


def parse_section6(chunk):
    """
    Parse section 6: one record per loaded VSTi synth.

        u8    slot_index
        cstr  path
        cstr  display_name
        u32   plugin_param_count
        f32   plugin_params[plugin_param_count]
        u8    skale_state[110]      see parse_vsti_skale_state
    """
    recs, consumed = read_chunks(chunk.data, base=chunk.offset + HDR.size)
    entries = []
    for rec in recs:
        if rec.tag == TAG_EOF or not rec.data:
            continue
        d = rec.data
        try:
            slot_index = d[0]
            path, n1 = cstring(d, 1)
            name, n2 = cstring(d, n1)
            trailing = d[n2:]
            entry = {
                "slot_index": slot_index,
                "path": path,
                "display_name": name,
                "trailing_bytes": len(trailing),
                "trailing_raw": trailing,
            }
            if len(trailing) >= 8:
                (param_count,) = struct.unpack_from("<I", trailing, 0)
                params_end = 4 + param_count * 4
                if param_count <= 65536 and params_end <= len(trailing):
                    params = list(struct.unpack_from(
                        f"<{param_count}f", trailing, 4))
                    skale_state_raw = trailing[params_end:]
                    skale_state = parse_vsti_skale_state(skale_state_raw)
                    entry["plugin_param_count"] = param_count
                    entry["plugin_params"] = params
                    entry["skale_state_raw"] = skale_state_raw
                    entry["skale_state"] = skale_state
                    entry["skale_state_exact"] = skale_state is not None
                    entry["structured_prefix_exact"] = True
            entries.append(entry)
        except IndexError as exc:
            entries.append({"error": f"{type(exc).__name__}: {exc}",
                            "record_offset": rec.offset, "record_len": rec.length})
    return {"empty": len(entries) == 0, "bytes_consumed": consumed, "entries": entries}


def parse_global(chunk):
    """Parse section 5 (global mixer).

    Header version below 7600: 4 bytes, one f32 (probably master volume).
    Version 7600: 424 bytes.

        0-3      f32 master_volume
        4-135    SUB1-4, 33 bytes each:
                   u8   flag0       usually 0; unknown
                   f32  fader       default 1.0
                   f32  balance     default 0.5
                   4 send knobs, 6 bytes each:
                     u8   pad       1 when the knob's LED is clicked
                     f32  value     default 1.0
                     u8   index     0-3, in order
        136-423  FX-bus sends, 32 x 9 bytes (8 buses x 4 sends):
                   u8   enabled_flag    unknown
                   u32  target_bus      0xFFFFFFFF = none
                   f32  send_level

    An FX bus's own fader and balance are in section 4, not here.
    `sub1_balance` is a shortcut to SUB1's balance.
    """
    data = chunk.data
    out = {"raw": data.hex()}
    if chunk.length == 4:
        out["master_volume"] = struct.unpack_from("<f", data, 0)[0]
        return out
    if chunk.length != 424:
        return out

    out["master_volume"] = struct.unpack_from("<f", data, 0)[0]
    out["sub1_balance"] = struct.unpack_from("<f", data, 9)[0]

    sub_buses = []
    for b in range(4):
        rec = data[4 + b * 33: 4 + (b + 1) * 33]
        knobs = []
        off = 9
        for k in range(4):
            knobs.append({
                "pad": rec[off],
                "value": struct.unpack_from("<f", rec, off + 1)[0],
                "index": rec[off + 5],
            })
            off += 6
        sub_buses.append({
            "flag0": rec[0],
            "fader": struct.unpack_from("<f", rec, 1)[0],
            "balance": struct.unpack_from("<f", rec, 5)[0],
            "knobs": knobs,
        })
    out["sub_buses"] = sub_buses

    matrix = []
    for i in range(32):
        off = 136 + i * 9
        # Unknown. Usually 0, sometimes 1; changing send_level alone
        # leaves it 0. Possibly the LED beside each send knob.
        enabled_flag = data[off]
        target_bus = struct.unpack_from("<I", data, off + 1)[0]
        send_level = struct.unpack_from("<f", data, off + 5)[0]
        matrix.append({
            "source_bus": i // 4,
            "slot": i % 4,
            "enabled_flag": enabled_flag,
            "target_bus": None if target_bus == 0xFFFFFFFF else target_bus,
            "send_level": send_level,
        })
    out["fx_bus_matrix"] = matrix
    return out


def parse_skm(path):
    raw = Path(path).read_bytes()
    chunks, consumed = read_chunks(raw)

    result = {
        "file": str(path),
        "size": len(raw),
        "bytes_consumed": consumed,
        "fully_covered": consumed == len(raw),
        "chunks": [
            {"offset": c.offset, "id": c.id, "tag": c.tag,
             "section": c.name, "length": c.length}
            for c in chunks
        ],
    }

    handlers = {
        TAG_HEADER: ("header", parse_header),
        1: ("song_text", parse_song_text),
        2: ("patterns", parse_patterns),
        3: ("instruments", parse_instruments),
        4: ("fx_chain", parse_fx_chain),
        5: ("global", parse_global),
        6: ("section6", parse_section6),
    }
    for c in chunks:
        entry = handlers.get(c.tag)
        if not entry:
            continue
        key, fn = entry
        try:
            result[key] = (fn(c, result.get("header", {}).get("version_raw"))
                           if c.tag == 3 else fn(c))
        except Exception as exc:  # report the error and parse the other sections
            result[key] = {"error": f"{type(exc).__name__}: {exc}"}

    result["has_ogg_samples"] = b"OggS" in raw
    return result


def report(info):
    print("=" * 68)
    print(f"{Path(info['file']).name}   {info['size']:,} bytes")
    cov = "exact" if info["fully_covered"] else \
          f"MISMATCH (consumed {info['bytes_consumed']:,})"
    print(f"  chunk coverage : {cov}")

    if "header" in info:
        h = info["header"]
        print(f"  magic/version  : {h.get('magic')} v{h.get('version')} "
              f"(raw {h.get('version_raw')})")
    if "song_text" in info:
        t = info["song_text"]
        print(f"  title          : {t.get('title')!r}")
        msg = (t.get("message") or "").replace("\r", " ").strip()
        print(f"  message        : {msg[:60]!r}{'...' if len(msg) > 60 else ''}")
        print(f"  initial timing : bpm={t.get('initial_bpm')} "
              f"speed={t.get('initial_speed')} channels={t.get('channel_count')}")
    if "patterns" in info:
        p = info["patterns"]
        print(f"  channels       : {p.get('channel_count')}")
        print(f"  order list     : {p.get('order_list_used')} entries, "
              f"{len(p.get('unique_patterns', []))} unique")
        print(f"                   {p.get('order_list')}")
        print(f"  repeat pattern : order {p.get('repeat_pattern')}")
        print(f"  patterns       : {p.get('pattern_count')} records, "
              f"rows={p.get('rows_seen')}, "
              f"walk={'clean' if p.get('walk_clean') else 'BROKE'}, "
              f"seq-indices={p.get('indices_sequential')}")
        all_tracks = [t for r in p.get("patterns", []) for t in r.get("tracks", [])]
        clean_tracks = sum(1 for t in all_tracks if t.get("events_clean"))
        pct = (100 * clean_tracks / len(all_tracks)) if all_tracks else 0
        print(f"  tracks         : channel-major, {clean_tracks}/{len(all_tracks)} "
              f"({pct:.1f}%) decode with exact byte consumption "
              f"(should be 100%)")
    if "instruments" in info:
        ins = info["instruments"]
        recs = ins.get("instruments", [])
        located = sum(1 for r in recs if r.get("internals_located"))
        print(f"  instruments    : {ins.get('count')} records, "
              f"internals located for {located}/{len(recs)}")
        for rec in recs[:8]:
            nm = rec["name"][:40]
            loc = "?" if "internals_located" not in rec else \
                  ("ok" if rec["internals_located"] else "NOT FOUND")
            print(f"      [{rec['index']:3d}] {nm!r:<44} {rec['record_len']:>9,} bytes  "
                  f"internals={loc}")
            if "keymap_layout" in rec:
                print(f"            keymap={rec['keymap_layout']} "
                      f"entries={len(rec['keymap'])}")
            if "fadeout" in rec:
                print(f"            fadeout={rec['fadeout']:#06x}")
            for s in rec.get("samples", []):
                if "error" in s:
                    print(f"            sample {s['name']!r}: ERROR {s['error']}")
                    continue
                print(f"            sample {s['name']!r:<30} vol={s['volume']:#04x} "
                      f"pan={s['panning']:#04x} finetune={s['finetune']} "
                      f"relnote={s['relative_note']} loop={s['loop_type']} "
                      f"[{s['loop_start']}-{s['loop_end']}]")
                if s.get("audio_located"):
                    print(f"              audio: {s['format']} "
                          f"values={s.get('stored_value_count', s['frames'])} "
                          f"frames/ch={s.get('frame_count_per_channel')} "
                          f"channels={s['channels']} "
                          f"data_len={s['audio_data_length']:,} "
                          f"size_exact={s['size_exact']}")
            for env in rec.get("envelopes", {}).values():
                flags = [name for name, active in (
                    ("enabled", env["enabled"]),
                    ("sustain", env["sustain_enabled"]),
                    ("loop", env["loop_enabled"])) if active]
                print(f"            {env['type']} envelope: "
                      f"{len(env['points'])} points "
                      f"flags={','.join(flags) if flags else 'off'}")
            if rec.get("other_subchunks"):
                print(f"            + {rec['other_subchunks']} preset/parameter "
                      f"sub-chunks (undecoded)")
        if ins.get("count", 0) > 8:
            print(f"      ... {ins['count'] - 8} more")
    if "fx_chain" in info:
        fx = info["fx_chain"]
        for s in fx.get("slots", []):
            if "error" in s:
                print(f"  fx slot        : ERROR {s['error']}")
                continue
            print(f"  fx slot {s['slot_index']:2d}    : {s['display_name']!r:<24} "
                  f"mixer_volume={s['mixer_volume']:.3f} "
                  f"wet_or_pan={s['wet_or_pan']:.3f} bypassed={s['bypassed']} "
                  f"params={s['param_count']} exact={s['exact']}")
    if "global" in info:
        g = info["global"]
        print(f"  global (sec 5) : master_volume={g.get('master_volume')} "
              f"sub1_balance={g.get('sub1_balance')}")
        if "sub_buses" in g:
            for i, sb in enumerate(g["sub_buses"], 1):
                print(f"                   SUB{i}: flag0={sb['flag0']} "
                      f"fader={sb['fader']:.3f} balance={sb['balance']:.3f} "
                      f"knobs={[round(k['value'], 3) for k in sb['knobs']]}")
        if "fx_bus_matrix" in g:
            sends = [e for e in g["fx_bus_matrix"] if e["target_bus"] is not None]
            print(f"                   fx_bus_matrix: {len(sends)}/32 slots routed")
    if "section6" in info:
        s6 = info["section6"]
        if s6.get("empty"):
            print(f"  section 6      : empty")
        else:
            for e in s6.get("entries", []):
                if "error" in e:
                    print(f"  section 6      : ERROR {e['error']}")
                    continue
                if "plugin_params" in e:
                    print(f"  section 6      : slot={e['slot_index']} "
                          f"path={e['path']!r} name={e['display_name']!r} "
                          f"params={e['plugin_param_count']} "
                          f"Skale_state={len(e['skale_state_raw'])} bytes")
                else:
                    print(f"  section 6      : slot={e['slot_index']} "
                          f"path={e['path']!r} name={e['display_name']!r} "
                          f"trailing={e['trailing_bytes']} bytes (undecoded)")
    print(f"  ogg samples    : {info['has_ogg_samples']}")


def _malformed_fixtures(root, files):
    """
    Return (expected_reject, expected_invalid) sets of paths from
    `root/manifest.json`. Both are empty when there is no manifest.
    """
    manifest_path = Path(root) / "manifest.json"
    if not manifest_path.is_file():
        return set(), set()
    rejects = set()

    def walk(o):
        if isinstance(o, dict):
            if o.get("expected_parse") == "reject" and "path" in o:
                rejects.add(Path(o["path"]).as_posix())
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.loads(manifest_path.read_text()))
    expected_reject = {f for f in files
                       if any(r == f.as_posix() or r.endswith("/" + f.relative_to(root).as_posix())
                              for r in rejects)}
    expected_invalid = {f for f in files
                        if f.name.startswith("invalid-") and f not in expected_reject}
    return expected_reject, expected_invalid


def verify_corpus(root):
    """
    Check every .skm under `root` and print pass/fail counts per check:
    container coverage, song-text trailer against header and channel
    count, FX slot and synth record exactness, track decoding, pattern
    framing, instrument layout, samples, order lists, and the global mixer.

    Returns nonzero if any file fails a hard check, so it can gate CI.
    Every track must decode exactly. The share of synth parameters in
    [0, 1] is informational only.

    If `root` holds a fixture `manifest.json`, deliberately malformed
    fixtures are reported separately instead of as hard failures: a file
    with `expected_parse: reject` must fail to parse, and a file named
    `invalid-*` may fail content checks but must still parse.
    """
    files = sorted(Path(root).glob("**/*.skm"))
    n = len(files)
    expected_reject, expected_invalid = _malformed_fixtures(root, files)
    hard_failures = []
    expected_failures = []

    def fail(entry):
        f_ = entry[0]
        if f_ in expected_reject or f_ in expected_invalid:
            expected_failures.append(entry)
        else:
            hard_failures.append(entry)

    fully_covered = 0
    trailer_checks = {"channel_match": 0, "version_match": 0, "reserved_zero": 0, "total": 0}
    fx_slots_total = fx_slots_exact = 0
    s6_entries_total = s6_entries_in_range = s6_skale_state_exact = 0
    tracks_total = tracks_clean = 0
    pattern_sections_total = pattern_sections_exact = 0
    patterns_total = patterns_rows_nonzero = 0
    tracks_row_offset_consistent = 0
    row_overflow = []
    instruments_total = instruments_located = 0
    envelope_grids_total = envelope_grids_exact = 0
    mixer_strip_total = mixer_strip_sane = 0
    samples_total = samples_size_exact = 0
    samples_extract_total = samples_extract_ok = 0
    order_lists_total = order_lists_in_range = 0
    repeat_patterns_total = repeat_patterns_in_range = 0
    global_424_total = global_424_clean = 0
    sub_bus_records_total = sub_bus_records_clean = 0

    for f in files:
        try:
            info = parse_skm(f)
            raw = f.read_bytes()
        except Exception as exc:
            if f in expected_invalid:
                hard_failures.append((f, "invalid-* fixture must still parse; "
                                      f"parse_skm raised: {type(exc).__name__}: {exc}"))
            else:
                fail((f, f"parse_skm raised: {type(exc).__name__}: {exc}"))
            continue
        if f in expected_reject:
            hard_failures.append((f, "manifest expects this file to be "
                                  "rejected, but it parsed"))
            continue
        if not info.get("fully_covered"):
            fail((f, f"container coverage mismatch: consumed "
                  f"{info['bytes_consumed']:,} of {info['size']:,}"))
        else:
            fully_covered += 1

        h = info.get("header", {})
        t = info.get("song_text", {})
        p = info.get("patterns", {})
        if t and "version_raw" in t:
            trailer_checks["total"] += 1
            if t.get("version_raw") == h.get("version_raw"):
                trailer_checks["version_match"] += 1
            if t.get("reserved") == 0:
                trailer_checks["reserved_zero"] += 1
            if t.get("channel_count") == p.get("channel_count"):
                trailer_checks["channel_match"] += 1

        for s in info.get("fx_chain", {}).get("slots", []):
            if "error" in s:
                continue
            fx_slots_total += 1
            if s.get("exact"):
                fx_slots_exact += 1

        for e in info.get("section6", {}).get("entries", []):
            if "plugin_params" not in e:
                continue
            s6_entries_total += 1
            if all(0.0 <= p <= 1.0 for p in e["plugin_params"]):
                s6_entries_in_range += 1
            if e.get("skale_state_exact"):
                s6_skale_state_exact += 1
            else:
                fail((f, f"section-6 slot {e.get('slot_index')} "
                      "skale_state_raw is not a valid 110-byte strip"))

        if p:
            pattern_sections_total += 1
            if p.get("walk_clean") and p.get("all_tracks_clean") is not False:
                pattern_sections_exact += 1
            else:
                fail((f, "section-2 chunk list or track framing not exact"))
        for r in p.get("patterns", []):
            patterns_total += 1
            if r.get("rows"):
                patterns_rows_nonzero += 1
            else:
                fail((f, f"pattern {r.get('index')} has u16 rows == 0"))
            for tr in r.get("tracks", []):
                tracks_total += 1
                if tr.get("events_clean"):
                    tracks_clean += 1
                if tr.get("row_offset_consistent"):
                    tracks_row_offset_consistent += 1
                # `parse_patterns` right-pads to the record's own `rows`
                # (with the 256-wrap fix applied) -- a track ending up
                # longer than that would mean the padding logic or the
                # wrap fix itself is wrong, not just an open-percentage
                # residual like row_offset_consistent above.
                if len(tr["rows"]) > r["rows"]:
                    row_overflow.append((f, r["index"], tr["channel"]))

        if "order_list_in_range" in p:
            order_lists_total += 1
            if p["order_list_in_range"]:
                order_lists_in_range += 1
        if "repeat_pattern" in p and p.get("song_length", 0) > 0:
            repeat_patterns_total += 1
            if p["repeat_pattern"] < p["song_length"]:
                repeat_patterns_in_range += 1
            else:
                fail((f, f"repeat_pattern {p['repeat_pattern']} "
                      f"is outside song_length {p['song_length']}"))

        g = info.get("global", {})
        if "sub_buses" in g:
            for sb in g["sub_buses"]:
                sub_bus_records_total += 1
                clean = sb["flag0"] in (0, 1) and all(
                    k["pad"] in (0, 1) and k["index"] == idx
                    for idx, k in enumerate(sb["knobs"])
                )
                if clean:
                    sub_bus_records_clean += 1
        if "fx_bus_matrix" in g:
            for e in g["fx_bus_matrix"]:
                global_424_total += 1
                expected = e["source_bus"] + e["slot"] + 1
                if expected > 7:
                    expected = None
                if e["target_bus"] == expected:
                    global_424_clean += 1

        for rec in info.get("instruments", {}).get("instruments", []):
            if "internals_located" not in rec:
                continue
            instruments_total += 1
            if rec["internals_located"]:
                instruments_located += 1
                envelope_grids_total += 1
                if rec.get("envelope_grid_exact"):
                    envelope_grids_exact += 1
                else:
                    fail((f, f"instrument {rec.get('index')} "
                          "envelope grid is not an exact 8x4 grid"))
            if "mixer_strip" in rec and h.get("version_raw") == 7600:
                mixer_strip_total += 1
                if rec["mixer_strip"] is not None:
                    mixer_strip_sane += 1
            for s in rec.get("samples", []):
                if not s.get("audio_located"):
                    continue
                samples_total += 1
                if s.get("size_exact"):
                    samples_size_exact += 1
                if not s.get("size_exact"):
                    continue
                samples_extract_total += 1
                try:
                    fmt = s.get("format_raw")
                    if fmt in (2, 3):
                        arr = extract_pcm_samples(raw, s)
                        ok = len(arr) == s["frames"]
                    elif fmt == 4:
                        ok = extract_ogg_stream(raw, s)[:4] == b"OggS"
                    else:
                        ok = False
                except Exception:
                    ok = False
                if ok:
                    samples_extract_ok += 1

    def pct(n_, d_):
        return f"{n_}/{d_} ({100*n_/d_:.1f}%)" if d_ else "n/a"

    print("=" * 68)
    print(f"corpus verification: {n} files under {root}")
    print()
    print(f"  container coverage       : {pct(fully_covered, n - len(expected_reject))}  "
          f"<- must be 100%, excluding files the manifest expects to be rejected")
    if expected_reject or expected_invalid:
        print(f"  deliberately malformed    : {len(expected_reject)} expected to be "
              f"rejected, {len(expected_invalid)} invalid-* expected to parse")
        for f, msg in expected_failures:
            print(f"      (expected) {f}: {msg}")
    if hard_failures:
        print(f"  HARD FAILURES             : {len(hard_failures)}")
        for f, msg in hard_failures[:20]:
            print(f"      {f}: {msg}")
        if len(hard_failures) > 20:
            print(f"      ... {len(hard_failures) - 20} more")
    print()
    print("  section 1 trailer cross-checks (must be 100%):")
    print(f"      version_raw == header version : "
          f"{pct(trailer_checks['version_match'], trailer_checks['total'])}")
    print(f"      reserved byte == 0            : "
          f"{pct(trailer_checks['reserved_zero'], trailer_checks['total'])}")
    print(f"      channel_count == section 2    : "
          f"{pct(trailer_checks['channel_match'], trailer_checks['total'])}")
    print()
    print(f"  FX chain slots exact      : {pct(fx_slots_exact, fx_slots_total)}  "
          f"<- must be 100%")
    print(f"  section 6 plugin params    : {pct(s6_entries_in_range, s6_entries_total)}  "
          f"<- counted prefixes recognized; [0,1] range is informational "
          f"and plugin-specific")
    print(f"  section 6 skale_state     : {pct(s6_skale_state_exact, s6_entries_total)}  "
          f"<- must be 100% (110-byte synth mixer strip)")
    print()
    print(f"  pattern chunk lists exact : {pct(pattern_sections_exact, pattern_sections_total)}  "
          f"<- must be 100%: pattern chunks, track chunks, and EOF, "
          f"one track per channel")
    print(f"  pattern rows (u16) > 0    : {pct(patterns_rows_nonzero, patterns_total)}  "
          f"<- must be 100%: Skale writes 256 rows as 00 01")
    print(f"  pattern tracks exact      : {pct(tracks_clean, tracks_total)}  "
          f"<- must be 100%")
    print(f"  reserved/last_row consist.: {pct(tracks_row_offset_consistent, tracks_total)}  "
          f"<- expected 100%; rows are positioned from `reserved`")
    if row_overflow:
        print(f"  ROW PADDING OVERFLOW      : {len(row_overflow)}  "
              f"<- must be 0 (a track ended up longer than its pattern's "
              f"own row count -- the padding logic is wrong)")
        for f, idx, ch in row_overflow[:10]:
            print(f"      {f}: pattern {idx} channel {ch}")
    print(f"  instrument internals loc. : {pct(instruments_located, instruments_total)}  "
          f"<- includes instruments with no samples")
    print(f"  instrument 8x4 env grids  : {pct(envelope_grids_exact, envelope_grids_total)}  "
          f"<- must be 100%: 32 envelope chunks per instrument, except "
          f"deliberately malformed fixtures")
    print(f"  mixer_strip sane (0.76)   : {pct(mixer_strip_sane, mixer_strip_total)}  "
          f"<- record versions 4-6; unknown fields stay raw")
    print(f"  sample header+audio exact : {pct(samples_size_exact, samples_total)}  "
          f"<- must be 100% where located")
    print(f"  sample audio extracted    : {pct(samples_extract_ok, samples_extract_total)}  "
          f"<- must be 100% where size-exact, except deliberately "
          f"malformed fixtures")
    print(f"  order list in range       : {pct(order_lists_in_range, order_lists_total)}  "
          f"<- informational: Skale may preserve references to absent "
          f"pattern IDs and presents them as synthetic empty patterns")
    print(f"  repeat pattern in range   : {pct(repeat_patterns_in_range, repeat_patterns_total)}  "
          f"<- must be 100% (Skale's REPEAT PATT. restart order)")
    print(f"  global (sec5) fx targets  : {pct(global_424_clean, global_424_total)}  "
          f"at their structural default (source_bus+slot+1, sentinel past "
          f"bus 7) <- informational: a different target is a "
          f"re-routed send, not an error")
    print(f"  global (sec5) SUB records : {pct(sub_bus_records_clean, sub_bus_records_total)}  "
          f"<- must be 100%: flag0 and knob pad bytes are 0 or 1, and "
          f"knob indices are 0,1,2,3")
    print("=" * 68)

    return len(hard_failures) == 0


def main():
    ap = argparse.ArgumentParser(description="Parse Skale Tracker .SKM modules")
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a report")
    ap.add_argument("--verify-corpus", metavar="DIR",
                     help="regression-check every .skm under DIR instead of "
                          "reporting on individual files")
    ap.add_argument("--extract-samples", metavar="OUTDIR", type=Path,
                     help="export every located sample from the given file(s) "
                          "to OUTDIR as .ogg/.wav (see export_sample); raw-PCM "
                          "rate is derived from relative_note/finetune "
                          "unless --sample-rate overrides it")
    ap.add_argument("--sample-rate", type=int, default=None,
                     help="override the auto-derived sample rate (Hz) when "
                          "exporting raw-PCM samples with --extract-samples")
    args = ap.parse_args()

    if args.verify_corpus:
        ok = verify_corpus(args.verify_corpus)
        sys.exit(0 if ok else 1)

    if not args.files:
        ap.error("provide one or more files, or use --verify-corpus DIR")

    if args.extract_samples:
        args.extract_samples.mkdir(parents=True, exist_ok=True)
        for f in args.files:
            info = parse_skm(f)
            raw = f.read_bytes()
            for instr in info.get("instruments", {}).get("instruments", []):
                for s in instr.get("samples", []):
                    if not s.get("audio_located") or not s.get("size_exact"):
                        continue
                    ext = "ogg" if s.get("format_raw") == 4 else "wav"
                    stem = Path(s["name"]).stem or s["name"]
                    out = args.extract_samples / (
                        f"{f.stem}_instr{instr['index']}_{stem}.{ext}")
                    try:
                        export_sample(raw, s, out, sample_rate=args.sample_rate)
                        print(f"wrote {out}")
                    except ValueError as exc:
                        print(f"skipped {instr['name']!r}/{s['name']!r}: {exc}",
                              file=sys.stderr)
        return

    results = []
    for f in args.files:
        try:
            results.append(parse_skm(f))
        except Exception as exc:
            msg = {"file": str(f), "error": f"{type(exc).__name__}: {exc}"}
            results.append(msg)
            if not args.json:
                print(f"!! {f}: {msg['error']}", file=sys.stderr)

    if args.json:
        json.dump(results, sys.stdout, indent=2, default=_json_default)
        print()
    else:
        for r in results:
            if "error" not in r:
                report(r)


if __name__ == "__main__":
    main()
