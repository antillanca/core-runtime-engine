from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_frozen_release_manifest_v11_5 import (
    INVENTORY_PROFILE,
    RELEASE_VERSION,
    required_v11_5_candidate_artifacts,
    validate_v11_5_release_manifest,
)

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "examples/frozen_release_manifest/accepted_v11_5_0_candidate.json"


def test_v11_5_candidate_manifest_is_historical() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report = validate_v11_5_release_manifest(MANIFEST, verify_live_artifacts=False)
    assert report["status"] == "passed", report["errors"]
    assert payload["release_version"] == RELEASE_VERSION
    assert payload["inventory_profile"] == INVENTORY_PROFILE
    assert payload["artifact_count"] == len(required_v11_5_candidate_artifacts())
