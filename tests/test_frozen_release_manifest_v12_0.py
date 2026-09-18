#!/usr/bin/env python3
"""Test v12.0.0 frozen release manifest validation."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_frozen_release_manifest_v12_0 import validate_v12_0_release_manifest

MANIFEST = PROJECT_ROOT / "examples" / "frozen_release_manifest" / "accepted_v12_0_0_frozen.json"


def test_v12_0_frozen_manifest_is_exact_and_live() -> None:
    report = validate_v12_0_release_manifest(MANIFEST, verify_live_artifacts=True)
    assert report["status"] == "passed", report["errors"]
    assert report["release_version"] == "v12.0.0"
    assert report["inventory_profile"] == "core.sealed_public_release.v12_0_0"
    assert report["manifest_valid"] is True
    assert report["live_artifacts_verified"] is True
    assert report["artifact_count"] == 208


if __name__ == "__main__":
    test_v12_0_frozen_manifest_is_exact_and_live()
    print("test_v12_0_frozen_manifest_is_exact_and_live PASSED")