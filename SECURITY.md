<!-- SPDX-License-Identifier: CC-BY-4.0 -->

# Security

Treat SKM files as untrusted input. Report crashes, excessive allocation,
infinite loops, bad chunk-length handling, or unsafe extraction paths through
[GitHub private vulnerability reporting](https://github.com/lpreiner/skale-skm-format/security/advisories/new).
If that is unavailable, open an issue describing the problem without
attaching the file, and offer to send it privately.

The reference parser is research code. A file it accepts is not thereby safe.
