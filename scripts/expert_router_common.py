"""Small deterministic Expert Router foundation used by release gates.

This module intentionally contains only offline validation and eligibility
selection.  It does not invoke a model, scheduler, provider, or command.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.audit_event import compute_operational_fingerprint  # noqa: E402


FIXTURE_SCHEMA = "core.expert_router_fixture.v1"


def load_fixture(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("routing fixture must be a JSON object")
    return payload


def fixture_label(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def fixture_fingerprint(payload: dict[str, Any]) -> str:
    return "sha256:" + compute_operational_fingerprint(payload)


def validate_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if payload.get("schema") != FIXTURE_SCHEMA:
        errors.append({"code": "schema_mismatch", "expected": FIXTURE_SCHEMA})
    for field in ("routing_id", "profile_id"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            errors.append({"code": "required_field_missing", "field": field})
    proposals = payload.get("proposals")
    if not isinstance(proposals, list) or not proposals:
        errors.append({"code": "proposals_required", "field": "proposals"})
        return errors
    seen: set[tuple[str, str]] = set()
    for index, proposal in enumerate(proposals):
        field = f"proposals[{index}]"
        if not isinstance(proposal, dict):
            errors.append({"code": "proposal_must_be_object", "field": field})
            continue
        expert_id = proposal.get("expert_id")
        proposal_id = proposal.get("proposal_id")
        if not isinstance(expert_id, str) or not expert_id.strip():
            errors.append({"code": "required_field_missing", "field": f"{field}.expert_id"})
        if not isinstance(proposal_id, str) or not proposal_id.strip():
            errors.append({"code": "required_field_missing", "field": f"{field}.proposal_id"})
        key = (str(expert_id).strip(), str(proposal_id).strip())
        if key in seen:
            errors.append({"code": "duplicate_proposal", "field": field})
        seen.add(key)
        if not isinstance(proposal.get("eligible"), bool):
            errors.append({"code": "eligible_must_be_boolean", "field": f"{field}.eligible"})
        priority = proposal.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, int):
            errors.append({"code": "priority_must_be_integer", "field": f"{field}.priority"})
    return errors


def validate_fixture(path: Path) -> dict[str, Any]:
    try:
        payload = load_fixture(path)
        errors = validate_payload(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        payload = {}
        errors = [{"code": "invalid_fixture", "message": str(exc)}]
    result: dict[str, Any] = {
        "schema": "core.expert_router_validation.v1",
        "status": "passed" if not errors else "failed",
        "execution_authorized": False,
        "fixture": fixture_label(path),
        "routing_id": payload.get("routing_id", ""),
        "profile_id": payload.get("profile_id", ""),
        "errors": errors,
        "warnings": [],
        "fixture_fingerprint": fixture_fingerprint(payload) if payload else None,
    }
    return result


def evaluate_fixture(path: Path) -> dict[str, Any]:
    validation = validate_fixture(path)
    if validation["status"] != "passed":
        return {
            "schema": "core.expert_router_evaluation.v1",
            "status": "failed",
            "execution_authorized": False,
            "routing_id": validation["routing_id"],
            "profile_id": validation["profile_id"],
            "selected_experts": [],
            "rejected_experts": [],
            "reason_codes": [error["code"] for error in validation["errors"]],
            "evaluation_summary": {"selected_count": 0, "rejected_count": 0, "total_proposals": 0},
            "source_fingerprint": validation["fixture_fingerprint"],
        }
    payload = load_fixture(path)
    proposals = sorted(
        payload["proposals"],
        key=lambda item: (-item["priority"], item["expert_id"], item["proposal_id"]),
    )
    selected = [
        {
            "expert_id": item["expert_id"],
            "proposal_id": item["proposal_id"],
            "reason": "eligible_by_fixture_policy",
        }
        for item in proposals
        if item["eligible"]
    ]
    rejected = [
        {
            "expert_id": item["expert_id"],
            "proposal_id": item["proposal_id"],
            "reason": "ineligible_by_fixture_policy",
        }
        for item in proposals
        if not item["eligible"]
    ]
    result: dict[str, Any] = {
        "schema": "core.expert_router_evaluation.v1",
        "status": "passed",
        "execution_authorized": False,
        "fixture": fixture_label(path),
        "routing_id": payload["routing_id"],
        "profile_id": payload["profile_id"],
        "selected_experts": selected,
        "rejected_experts": rejected,
        "reason_codes": [],
        "evaluation_summary": {
            "selected_count": len(selected),
            "rejected_count": len(rejected),
            "total_proposals": len(proposals),
        },
        "source_fingerprint": validation["fixture_fingerprint"],
    }
    result["evaluation_fingerprint"] = "sha256:" + compute_operational_fingerprint(result)
    return result


def fixture_paths(root: Path) -> list[Path]:
    return sorted((path for path in root.glob("*.json") if path.name != "README.json"), key=lambda path: path.name)
