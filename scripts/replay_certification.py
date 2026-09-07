#!/usr/bin/env python3
"""Certify deterministic replay over the frozen reference datasets.

The reference data predates the current public canonicalization helper.  The
manifest therefore remains the authority for historical sidecar fingerprints;
this tool verifies those bindings, parses every referenced artifact, and adds
current semantic digests without rewriting historical values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.canonicalization import canonical_json_hash  # noqa: E402
from core_runtime.core.schema_fingerprint import operational_fingerprint  # noqa: E402


SCHEMA = "core.replay_certification.v1"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"artifact path escapes reference dataset: {relative}") from exc
    return candidate


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_artifact(path: Path) -> Any:
    if path.suffix == ".jsonl":
        rows: list[Any] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    rows.append(json.loads(stripped))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
        return rows
    return _load_json(path)


def _sidecar_checks(root: Path, manifest: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    checks: dict[str, str] = {}
    errors: list[dict[str, Any]] = []
    for key, expected in sorted(manifest.items()):
        if not key.endswith("_fingerprint") and key not in {"projection_hash"}:
            continue
        if not isinstance(expected, str) or not expected:
            errors.append({"code": "invalid_manifest_fingerprint", "field": key})
            continue
        sidecar_key = f"{key}_file"
        sidecar_name = manifest.get(sidecar_key)
        if not isinstance(sidecar_name, str):
            continue
        try:
            sidecar_path = _safe_path(root, sidecar_name)
            actual = sidecar_path.read_text(encoding="utf-8").strip()
        except (OSError, ValueError) as exc:
            errors.append({"code": "fingerprint_sidecar_unreadable", "field": key, "message": str(exc)})
            continue
        if actual != expected:
            errors.append({"code": "fingerprint_sidecar_mismatch", "field": key, "expected": expected, "actual": actual})
        checks[key] = "passed" if actual == expected else "failed"
    return checks, errors


def certify_dataset(root: Path) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    checks: dict[str, str] = {}
    manifest_path = root / "manifest.json"
    try:
        manifest = _load_json(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "dataset": root.name,
            "status": "failed",
            "errors": [{"code": "invalid_manifest", "message": str(exc)}],
        }
    if not isinstance(manifest, dict):
        return {
            "dataset": root.name,
            "status": "failed",
            "errors": [{"code": "invalid_manifest_shape"}],
        }

    sidecar_checks, sidecar_errors = _sidecar_checks(root, manifest)
    checks.update(sidecar_checks)
    errors.extend(sidecar_errors)

    artifacts: dict[str, str] = {}
    semantic_digests: dict[str, str] = {}
    for key, relative in sorted(manifest.items()):
        if not key.endswith("_file") or not isinstance(relative, str):
            continue
        if key.endswith("_fingerprint_file") or key == "projection_hash_file":
            # Text sidecars are validated above and are not JSON artifacts.
            continue
        try:
            path = _safe_path(root, relative)
            if not path.is_file():
                raise FileNotFoundError(relative)
            payload = _load_artifact(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"code": "artifact_invalid", "field": key, "message": str(exc)})
            checks[key] = "failed"
            continue
        artifacts[relative] = _sha256_bytes(path.read_bytes())
        if path.suffix in {".json", ".jsonl"}:
            semantic_digests[relative] = canonical_json_hash(payload)
        checks[key] = "passed"

    # These current semantic bindings are safe to verify without changing the
    # legacy hashes recorded by the v4.x manifests.
    for manifest_key, artifact_key in (
        ("projection_hash", "projection_file"),
        ("sensor_trace_fingerprint", "sensor_trace_file"),
        ("execution_graph_graph_fingerprint", "execution_graph_file"),
        ("execution_graph_node_fingerprints", "execution_graph_node_fingerprints_file"),
    ):
        expected = manifest.get(manifest_key)
        relative = manifest.get(artifact_key)
        if not isinstance(expected, str) or not isinstance(relative, str):
            continue
        digest = semantic_digests.get(relative)
        if manifest_key == "projection_hash":
            try:
                digest = operational_fingerprint(_load_artifact(_safe_path(root, relative)))
            except (OSError, ValueError, json.JSONDecodeError):
                digest = None
        if manifest_key == "execution_graph_graph_fingerprint":
            try:
                graph = _load_artifact(_safe_path(root, relative))
                digest = graph.get("graph_fingerprint") if isinstance(graph, dict) else None
            except (OSError, ValueError, json.JSONDecodeError):
                digest = None
        if digest is not None:
            checks[manifest_key] = "passed" if digest == expected else "failed"
            if digest != expected:
                errors.append({"code": "semantic_fingerprint_mismatch", "field": manifest_key, "expected": expected, "actual": digest})

    event_file = manifest.get("event_log_file")
    if isinstance(event_file, str) and event_file in semantic_digests:
        try:
            events = _load_artifact(_safe_path(root, event_file))
            sequence = [item.get("seq") for item in events] if isinstance(events, list) else []
            checks["event_sequence"] = "passed" if sequence == list(range(len(sequence))) else "failed"
            if checks["event_sequence"] == "failed":
                errors.append({"code": "event_sequence_not_contiguous", "field": "event_log_file"})
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    status = "certified" if not errors else "failed"
    payload: dict[str, Any] = {
        "dataset": root.name,
        "status": status,
        "schema_version": manifest.get("schema_version"),
        "runtime_version": manifest.get("runtime_version"),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "semantic_digests": semantic_digests,
        "checks": checks,
        "errors": errors,
    }
    payload["fingerprint"] = "sha256:" + canonical_json_hash(payload)
    return payload


def _dataset_roots(reference_dir: Path) -> list[Path]:
    if (reference_dir / "manifest.json").is_file():
        return [reference_dir]
    return sorted((child for child in reference_dir.iterdir() if child.is_dir() and (child / "manifest.json").is_file()), key=lambda path: path.name)


def certify_reference_dir(reference_dir: Path) -> dict[str, Any]:
    roots = _dataset_roots(reference_dir)
    datasets = [certify_dataset(root) for root in roots]
    status = "certified" if roots and all(item["status"] == "certified" for item in datasets) else "failed"
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "authority": "validation_only",
        "execution_authorized": False,
        "reference_dir": reference_dir.as_posix(),
        "dataset_count": len(datasets),
        "datasets": datasets,
    }
    payload["report_fingerprint"] = "sha256:" + canonical_json_hash(payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Certify deterministic replay over frozen CORE reference data.")
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = certify_reference_dir(args.reference_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report["status"] == "certified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
