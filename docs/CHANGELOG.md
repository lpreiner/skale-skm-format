<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Interpretation history

## Unreleased — initial public repository

- Established redistribution-safe fixtures for application versions 0.70,
  0.71, 0.75, 0.76, 0.80, 0.802, and 0.81.
- Distinguished direct and framed instrument keymap/prefix layouts despite
  shared serialized version values.
- Verified PCM8, PCM16, stereo interleaving, Ogg framing, loop types, primary
  envelopes, Note Off, Note Death policy, sample volume/pan, and direct-layout
  mixer fader/BAL fields.
- Added rights-safe VST2 effect and VSTi fixture families, verified zero-based
  stored slot indices, FX mixer-volume and bypass fields, counted VSTi plugin
  parameters, and deterministic reload/resave behavior.
- Kept pattern note value `0x80` unidentified; instrument Note Death policy is
  not evidence that it represents pattern Note Cut.
- Corrected loop-point interpretation after confirming that Skale's editor
  displays those values in hexadecimal.
