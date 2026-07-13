#!/usr/bin/env python3
"""Compatibility entrypoint for deterministic frozen-rule Merkle batching."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_rule_anchor_batch import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
