<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Public fixture corpus

Every binary in this directory is listed in `manifest.json`, has a pinned
SHA-256 digest, and is covered by the repository-level `CC0-AFFIRMATION.md`.
Copyrighted
scene songs, unknown-origin audio, Skale executables, plugins, and private
research files are not distributed.

Fixture classes:

- `authentic/`: files saved or exported by a recorded Skale version from a
  new song using only project-created CC0 inputs;
- `generated/`: deterministic template rewrites and boundary/malformed cases
  derived from approved authentic fixtures;
- `audio/`: deterministic CC0 WAV inputs used to author the sample fixtures.

Synthetic and malformed fixtures test consumers. They are not evidence that
Skale itself emits or accepts the mutated representation unless the manifest
explicitly records a separate application-side observation.

## Adding a fixture

1. Begin with a new song or an already-approved CC0 fixture.
2. Use only inputs with recorded redistribution rights.
3. Change one feature at a time when establishing field semantics.
4. Record the application version, environment, source hashes, exact action,
   output hashes, and expected parser behavior.
5. Obtain an explicit CC0 affirmation from every contributor whose work is not
   already covered by the repository-level affirmation.
6. Add the fixture to the source manifests and publication allowlist.
7. Run `python3 tools/validate_public_tree.py .` in the assembled repository.

Do not contribute third-party music merely because it is old, freely
downloadable, or historically significant. A hash-only metadata record does
not grant permission to copy or redistribute the referenced file.
