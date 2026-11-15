<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Contributing

The most useful contribution is an example file from `EXAMPLES_NEEDED.md`.

## Format claims

Separate what the bytes are from what they mean. Back each claim with a
fixture, a controlled save, or another evidence source someone else can
check, and label it Verified, Probable, or Unknown as defined in `FORMAT.md`.
Describe fields as stored values, not in terms of a particular player.

## Files

Do not submit copyrighted songs, samples of unknown origin, executables,
plugins, personal data, or anything extracted from them. A new fixture needs
its input hashes, creation steps, creator, license, and a manifest entry; see
`tests/fixtures/README.md`. A file made from other files carries the rights
requirements of all of them.

## Licenses

Code is BSD-2-Clause, documentation is CC-BY-4.0, and fixtures and the Kaitai
schema are CC0-1.0, as set out in `LICENSE_POLICY.md`.

## Checks

Parser changes should come with a fixture or unit test. Before submitting,
run the tests, then the validator:

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 tools/validate_public_tree.py .
```

The validator rejects any `__pycache__` directory, so run the tests with `-B`
(or `PYTHONDONTWRITEBYTECODE=1`). It checks the filesystem, not Git, so
`.gitignore` does not help.
