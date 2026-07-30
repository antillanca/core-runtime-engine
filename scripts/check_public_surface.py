#!/usr/bin/env python3
"""Public-surface privacy guard.

Fails (exit 1) if any tracked file's content or path — or, with --rev, any
commit message reachable from that rev — matches a private pattern. The
pattern list intentionally lives OUTSIDE this repository (this file must
never enumerate the private terms it guards against), loaded from:

    1. $CORE_PRIVATE_PATTERNS_FILE, if set; otherwise
    2. ../.core_private_patterns relative to the repo root.

Pattern file format: one case-insensitive substring or regex per line;
blank lines and lines starting with '#' are ignored. Lines wrapped as
/.../ are treated as regex, everything else as a literal substring.

A line that legitimately needs to quote a forbidden term — for example, a
negative test asserting the term is absent elsewhere, not leaking it here —
may opt out with a trailing `# privacy-guard:allow` comment. This is an
explicit, per-line, human-added marker, not a pattern-matching heuristic:
every other line is still scanned, and adding the marker to hide a real leak
is exactly as visible in review as any other line of code.

Run before every push of this repository:

    python scripts/check_public_surface.py            # working tree
    python scripts/check_public_surface.py --rev HEAD # tree + messages
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATTERNS = REPO_ROOT.parent / ".core_private_patterns"

TEXT_SUFFIXES = {
    ".py", ".md", ".json", ".toml", ".txt", ".yml", ".yaml", ".cfg",
    ".ini", ".sh", ".sol", ".lock",
}

ALLOW_MARKER = "privacy-guard:allow"


def _load_patterns() -> list[re.Pattern[str]]:
    override = os.environ.get("CORE_PRIVATE_PATTERNS_FILE")
    path = Path(override) if override else DEFAULT_PATTERNS
    if not path.is_file():
        print(
            f"ERROR: patterns file not found: {path}\n"
            "Refusing to pass with an empty guard (fail closed).",
            file=sys.stderr,
        )
        raise SystemExit(2)
    patterns: list[re.Pattern[str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if len(line) > 2 and line.startswith("/") and line.endswith("/"):
            patterns.append(re.compile(line[1:-1], re.IGNORECASE))
        else:
            patterns.append(re.compile(re.escape(line), re.IGNORECASE))
    if not patterns:
        print("ERROR: patterns file is empty (fail closed).", file=sys.stderr)
        raise SystemExit(2)
    return patterns


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def _scan_tree(patterns: list[re.Pattern[str]]) -> list[str]:
    hits: list[str] = []
    for rel in _git("ls-files").splitlines():
        for pat in patterns:
            if pat.search(rel):
                hits.append(f"path: {rel} ~ /{pat.pattern}/")
        target = REPO_ROOT / rel
        if target.suffix.lower() not in TEXT_SUFFIXES or not target.is_file():
            continue
        try:
            text = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if ALLOW_MARKER in line:
                continue
            for pat in patterns:
                if pat.search(line):
                    hits.append(f"content: {rel}:{lineno} ~ /{pat.pattern}/")
    return hits


def _scan_messages(rev: str, patterns: list[re.Pattern[str]]) -> list[str]:
    hits: list[str] = []
    log = _git("log", "--format=%H%x00%B%x01", rev)
    for chunk in log.split("\x01"):
        if "\x00" not in chunk:
            continue
        sha, body = chunk.split("\x00", 1)
        for pat in patterns:
            if pat.search(body):
                hits.append(f"commit-message: {sha.strip()[:12]} ~ /{pat.pattern}/")
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rev", default=None,
        help="Also scan every commit message reachable from this rev.",
    )
    args = parser.parse_args(argv)

    patterns = _load_patterns()
    hits = _scan_tree(patterns)
    if args.rev:
        hits.extend(_scan_messages(args.rev, patterns))

    if hits:
        print("PRIVACY GUARD: FAILED")
        for hit in hits:
            print(f"  - {hit}")
        return 1
    print(f"PRIVACY GUARD: PASSED ({len(patterns)} patterns, tree clean"
          + (f", messages of {args.rev} clean" if args.rev else "") + ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
