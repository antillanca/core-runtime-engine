#!/usr/bin/env python3
"""Bump the canonical version of CORE.

This script now delegates to the controlled CLI command
``python -m core_runtime.cli bump-version`` which provides
both dry-run and apply modes with full safety checks.

Legacy direct-mutation has been replaced by the transacted
apply path in Slice 3.

Usage:
    # Dry-run (preview changes)
    python scripts/bump_version.py 10.6.0

    # Apply (requires --confirm-current)
    python scripts/bump_version.py 10.6.0 --apply --confirm-current 10.5.0

    # Legacy --no-changelog flag (ignored, kept for compatibility)
    python scripts/bump_version.py 10.6.0 --no-changelog
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_MODULE = "core_runtime.cli"


def main() -> int:
    """Delegate to the CLI bump-version command."""
    # Build CLI args from script args
    # First arg is the target version
    script_args = sys.argv[1:]

    if not script_args:
        print("Usage: python scripts/bump_version.py <target_version> [--apply --confirm-current <current>]", file=sys.stderr)
        return 2

    # Detect --no-changelog (legacy: ignored, emit info)
    has_no_changelog = "--no-changelog" in script_args
    filtered_args = [a for a in script_args if a != "--no-changelog"]

    # Default to --dry-run if neither --dry-run nor --apply specified
    has_apply = "--apply" in filtered_args
    has_dry_run = "--dry-run" in filtered_args
    if not has_apply and not has_dry_run:
        filtered_args.insert(0, "--dry-run")

    # Build the CLI command
    cmd = [sys.executable, "-m", CLI_MODULE, "bump-version"] + filtered_args

    if has_no_changelog:
        print("[info] --no-changelog is deprecated; changelog is always handled by the CLI apply path")

    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
