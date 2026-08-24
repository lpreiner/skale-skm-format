#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Validate an assembled standalone public SKM format repository."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


MAX_FILE_BYTES = 10 * 1024 * 1024
BINARY_SUFFIXES = {".skm", ".xm", ".wav"}
FORBIDDEN_PARTS = {
    ".git", ".claude", "libopenmpt-loader", "Skale Effects Commands",
    "__pycache__",
}
FORBIDDEN_FILENAMES = {"CLAUDE.md", "logo.png", "wav-tone-1s.wav"}
FORBIDDEN_TEXT = (
    "/" + "Users/",
    "C:" + "\\Users\\",
    "corpus/" + "singlevar/",
    "public-" + "corpus/",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_parser(root: Path):
    path = root / "reference" / "skmparse.py"
    spec = importlib.util.spec_from_file_location("public_skmparse", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate(root: Path) -> None:
    root = root.resolve()
    manifest_path = root / "tests" / "fixtures" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest.get("files", [])
    if manifest.get("schema_version") != 1 or not records:
        raise ValueError("fixture manifest is empty or has an unsupported schema")
    if manifest.get("rights_affirmation") != "CC0-AFFIRMATION.md":
        raise ValueError("fixture manifest lacks the repository CC0 affirmation")
    affirmation = root / "CC0-AFFIRMATION.md"
    if not affirmation.is_file() or "tests/fixtures/manifest.json" not in affirmation.read_text():
        raise ValueError("CC0 affirmation is missing or does not identify the manifest")

    declared: set[str] = set()
    for record in records:
        rel = record["path"]
        if rel in declared:
            raise ValueError(f"duplicate fixture path: {rel}")
        declared.add(rel)
        path = root / rel
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"missing or symlinked fixture: {rel}")
        if path.stat().st_size != record["bytes"]:
            raise ValueError(f"size mismatch: {rel}")
        if digest(path) != record["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {rel}")
        if record.get("license") != "CC0-1.0":
            raise ValueError(f"fixture lacks CC0-1.0 metadata: {rel}")

    actual = {
        path.relative_to(root).as_posix()
        for path in (root / "tests" / "fixtures").rglob("*")
        if path.is_file() and path.suffix.lower() in BINARY_SUFFIXES
    }
    if actual != declared:
        missing = sorted(declared - actual)
        extra = sorted(actual - declared)
        raise ValueError(f"fixture inventory mismatch; missing={missing}, extra={extra}")

    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if path.is_symlink():
            raise ValueError(f"symlink is not allowed: {rel}")
        if any(part in FORBIDDEN_PARTS for part in rel.parts):
            raise ValueError(f"forbidden path component: {rel}")
        if path.name in FORBIDDEN_FILENAMES:
            raise ValueError(f"forbidden file: {rel}")
        if not path.is_file():
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"unexpected large file: {rel}")
        if path.suffix.lower() not in BINARY_SUFFIXES:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"unexpected non-text file: {rel}") from exc
            for needle in FORBIDDEN_TEXT:
                if needle in text:
                    raise ValueError(f"private/local reference {needle!r} in {rel}")

    parser = load_parser(root)
    by_path = {record["path"]: record for record in records}
    for rel, record in by_path.items():
        if not rel.endswith(".skm"):
            continue
        should_reject = record.get("expected_parse") == "reject"
        try:
            parser.parse_skm(root / rel)
        except (ValueError, EOFError):
            if not should_reject:
                raise
        else:
            if should_reject:
                raise ValueError(f"malformed fixture unexpectedly parsed: {rel}")

    third_party = json.loads(
        (root / "corpus" / "third-party-manifest.json").read_text(
            encoding="utf-8"))
    if third_party.get("files_distributed") is not False:
        raise ValueError("third-party manifest must explicitly deny distribution")
    tested_versions = [
        item.get("display_version")
        for item in third_party.get("executables", [])
    ]
    expected_versions = [
        "0.70", "0.71", "0.75", "0.76", "0.80", "0.802", "0.81",
    ]
    if tested_versions != expected_versions:
        raise ValueError(
            "unexpected tested application versions: "
            f"{tested_versions!r} != {expected_versions!r}")

    print(f"validated {len(records)} fixture files in {root}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", nargs="?", type=Path, default=Path("."))
    args = ap.parse_args()
    validate(args.root)


if __name__ == "__main__":
    main()
