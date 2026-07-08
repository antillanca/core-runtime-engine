from __future__ import annotations

import json
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "examples" / "core_contracts"
SCHEMA_DIR = ROOT / "schemas" / "core"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema(name: str) -> dict:
    return _load_json(SCHEMA_DIR / name)


def _example(name: str) -> dict:
    return _load_json(EXAMPLES_DIR / name)


def test_memory_artifact_example_validates():
    jsonschema.validate(instance=_example("memory_artifact.v1.json"), schema=_schema("memory_artifact.v1.json"))


def test_control_decision_example_validates():
    jsonschema.validate(instance=_example("control_decision.v1.json"), schema=_schema("control_decision.v1.json"))


def test_execution_receipt_example_validates():
    jsonschema.validate(instance=_example("execution_receipt.v1.json"), schema=_schema("execution_receipt.v1.json"))


def test_causal_trace_example_validates():
    jsonschema.validate(instance=_example("causal_trace.v1.json"), schema=_schema("causal_trace.v1.json"))


def test_examples_do_not_use_absolute_paths():
    for example_path in EXAMPLES_DIR.glob("*.json"):
        payload = _load_json(example_path)
        text = json.dumps(payload)
        assert "/home/" not in text
        assert "artifact:private/" not in text
        assert not any(value.startswith("/") for value in payload.get("source_refs", []) if isinstance(value, str))
