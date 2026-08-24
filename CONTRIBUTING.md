<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Contributing

Contributions should distinguish observed bytes from interpretation. Format
claims need a reproducible fixture, a controlled comparison, or another clear
evidence source. Label conclusions as Verified, Probable, or Unknown.

Code contributions are BSD-2-Clause, documentation contributions are
CC-BY-4.0, and fixture/specification contributions are CC0-1.0 under the scope
described in `LICENSE_POLICY.md`.

Do not submit copyrighted modules, unknown-origin samples, executables,
plugins, personal data, or material extracted from them. New binary fixtures
require source/input hashes, creation steps, creator identification, an
explicit license declaration, and a manifest entry. A derivative inherits the
rights requirements of every input from which it was made.

Run:

```sh
python3 tools/validate_public_tree.py .
python3 -m unittest discover -s tests -p 'test_*.py'
```

Parser changes should add a focused fixture or unit test. Avoid defining SKM
fields in terms of a particular player's internal structures.
