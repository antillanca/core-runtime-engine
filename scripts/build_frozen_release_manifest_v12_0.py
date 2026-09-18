#!/usr/bin/env python3
"""Build the CORE v12.0.0 sealed release frozen manifest."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_frozen_release_manifest_v12_0 import build_v12_0_frozen_manifest  # noqa: E402
  # noqa: E402

def main() -> int:
    output = PROJECT_ROOT / "examples" / "frozen_release_manifest" / "accepted_v12_0_0_frozen.json"
    manifest = build_v12_0_frozen_manifest(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Built {output.relative_to(PROJECT_ROOT)} ({manifest['artifact_count']} artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())