<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Examples needed

Every open question about the format that a saved file could answer is listed
here. This is the single list; `FORMAT.md` and `PROVENANCE.md` point to it
rather than keeping their own.

Each entry says what is known, what is not, and the file that would settle
it. Unless an entry says otherwise:

- start from a new, empty song;
- use only the CC0 audio in `tests/fixtures/audio/` (or no samples at all);
- change one thing, save, and keep the save from before the change too;
- also export the song to `.xm` when the entry asks for it;
- record the Skale version and the exact steps you took.

`tests/fixtures/README.md` describes how to add a file to the fixture set and
the CC0 declaration it needs.

## Untested Skale versions

The tested versions are 0.70, 0.71, 0.75, 0.76, 0.80, 0.802, and 0.81.
*Needed:* if you have a released version outside this list, an empty song,
then the same song with one instrument holding one sample. Record the
application version so its file layout can be compared with `FORMAT.md`.

## Song text

**Non-ASCII characters.** ISO-8859-1 is assumed for titles and messages but
has not been tested.
*Needed:* a song whose title contains `é` and whose message contains `€`, plus
a screenshot of how Skale displays both. `€` is byte `0x80` in Windows-1252
and has no ISO-8859-1 encoding, so it tells the two apart.

## Patterns

**Effect commands `10`–`13`.** Names and parameter ranges come from Skale's
Help. None of these commands occurs in any file examined so far, so the
stored parameter bytes are unconfirmed.
*Needed:* one pattern, one channel, with these rows: `10 11`, `10 10`,
`11 01`, `11 00`, `12 00`, `12 80`, `12 FF`, `13 00`, `13 80`, `13 FF`.
Save `.skm` and `.xm`.

**Effect `0F` threshold.** Skale's Help says values above 31 set speed and
lower values set tempo. That is the reverse of XM, and is assumed to be a
wording error.
*Needed:* a pattern with `0F 1F` on one row and `0F 20` on a later row. Save
`.skm` and `.xm`, and note what Skale's BPM and speed displays show while each
row plays.

**Effects `00`–`0F` in a public file.** The match with XM numbering, and
`0C`'s halved parameter, rest on private songs.
*Needed:* one pattern using each of `00`–`0F` once with a distinctive
parameter, including `0C 80` and `0C 40`. Save `.skm` and `.xm`.

**Second volume-column byte.** A volume entry is two bytes. Second byte `00`
means a plain volume and `80` means no volume. No other second-byte values
have been observed; whether Skale supports other volume-column commands is
unknown.
*Needed:* one row for each kind of entry Skale's volume column accepts
(slides, panning, or anything else it offers), each with a distinctive value.
Save `.skm` and `.xm`.

**256-row pattern, saved by Skale.** Skale stores 256 rows as `u16` `00 01`.
This is established from private songs; the public 256-row fixture is
synthetic.
*Needed:* a pattern expanded to 256 rows with a note on the last row.

**Stored row count of 0.** Skale never writes it. Unknown how Skale loads it.
*Needed:* not a new save. Load a synthetic file with `rows = 0` (the project
can supply one) and report what Skale shows.

## Instruments

**Instrument filter controls.** Settings bytes `+89..+125` hold flags and
floats that look like a filter (defaults 5000, 5000, 50, 0.5, 0.5, 0, 10, and
a 3-bit mask at `+122`). No control has been tied to them.
*Needed:* change each filter control in the instrument editor in turn, one
control per file.

**Other unnamed settings bytes.** The 64-byte table at `+25..+88` is the
mapping of each index to itself in nearly every record. `+152`, `+132..+147`
(always `FF`), and `+155` (always `7F`) are unnamed. *Needed:* one save per
control on the extended instrument editor screen, including any MIDI or
note-remapping options. Any song where the `+25` table is not the identity map
is also useful, with a note of what was changed.

**VSTi linkage bytes `+126` and `+149`.** `+126` is 1 on every VSTi-linked
instrument and 0 otherwise, but no save has changed it on its own. `+149`
follows the device enable light in private saves, yet the public 0.81 VSTi
fixtures store 0 while linked.
*Needed:* in 0.81, with mda JX10 loaded, link an instrument to it, then save
once with the device light on and once with it off.

**Envelope grid columns 3 and 4.** Each instrument holds an 8 × 4 grid of
envelopes. Column 1 is volume and column 2 is panning. Columns 3 and 4 are
unidentified.
*Needed:* edit one envelope point in column 3 and save, then the same in
column 4, noting which on-screen envelope you edited.

**Keymap entries with more than one layer.** Framed keymap entries (0.80 and
later) are read as flag, layer count, and layers, but every observed count is
0 or 1.
*Needed:* in 0.80 or later, map two samples to the same key, if the editor
allows it.

**Unmapped keys.** Unknown whether Skale plays anything for a key with no
mapping.
*Needed:* in 0.80 or later, unmap one playable key, save, and report whether
playing that note makes a sound.

**Sample metadata byte `+4`.** It is 8 or 16. In older private songs it
tracks bit depth; fresh 0.81 saves always store 8.
*Needed:* the same 16-bit sample saved by 0.75 or 0.76 and by 0.81.

**Sample panning hard right.** `0x80` is centre and `0x00` is hard left. The
right endpoint is untested.
*Needed:* set a sample's panning to its maximum and save.

**Negative finetune and relative note.** Both are read as signed bytes. A
paired XM export supports this, but no save has moved them below zero on its
own.
*Needed:* save with finetune at -1, then with the sample transposed one
halftone down. Save `.skm` and `.xm` for each.

**Instrument fadeout.** Fadeout at keymap end `+0` matches Skale's XM export
in every private song checked; there is no public fixture.
*Needed:* set a distinctive fadeout on one instrument. Save `.skm` and `.xm`.

## Mixer, effects, and synths

**Section 5 in a public file.** The 0.76 master volume, SUB fader, balance,
and send-knob fields rest on private saves.
*Needed:* in 0.76, one save each after moving the master fader, SUB1's fader,
SUB1's balance, and one SUB1 send knob.

**Pre-0.76 master volume.** Before 0.76, section 5 is a single 4-byte `f32`,
assumed to be the master fader because 0.76 stores master volume first.
*Needed:* in 0.75, move the master fader and save.

**FX slot `wet_or_pan` and `loaded`.** In section 4, `wet_or_pan` is usually
0.5 and changes independently of the fader. `loaded` is 1 in every file seen.
*Needed:* with mda Delay in an FX slot in 0.76, move the FX bus balance and
save. Separately, a song saved while one FX slot's plugin is missing.

**Mixer toggle bytes.** In section 5, each sub-bus record starts with
`flag0`, and each FX-bus send has an `enabled_flag`. Both are 0 by default and
1 in some songs; the control that sets them is unknown.
*Needed:* one save per small toggle, LED, or button on the SUB and FX bus
strips.

**VSTi mixer strip.** The 110-byte strip after a synth's plugin parameters
ends in a byte at `+109`, provisionally `mute_or_toggle`.
*Needed:* in 0.81, toggle each button on the synth's mixer strip, one per
save.

**Subsongs.** No Skale version examined offers a way to create one, and no
file contains one. A single forum comment mentions them.
*Needed:* any song with more than one subsong, if one exists.
