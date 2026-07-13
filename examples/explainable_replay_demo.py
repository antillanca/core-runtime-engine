from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core_runtime.core.explainability import StaticExplainer  # noqa: E402


DEFAULT_FIXTURE_DIR = Path("tests/fixtures/explainability/v4_2_0_minimal")


class FrozenArtifact:
    __slots__ = ("_payload",)

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def __getattr__(self, name: str) -> Any:
        if name in self._payload:
            return self._payload[name]
        raise AttributeError(name)

    def to_dict(self) -> dict[str, Any]:
        return _unwrap(self._payload)


def _wrap(value: Any) -> Any:
    if isinstance(value, dict):
        return FrozenArtifact({key: _wrap(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_wrap(item) for item in value]
    return value


def _unwrap(value: Any) -> Any:
    if isinstance(value, FrozenArtifact):
        return value.to_dict()
    if isinstance(value, list):
        return [_unwrap(item) for item in value]
    if isinstance(value, dict):
        return {key: _unwrap(item) for key, item in value.items()}
    return value


def load_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl_if_exists(path: Path) -> list[Any] | None:
    if not path.exists():
        return None
    rows: list[Any] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_first_existing(root: Path, *names: str) -> Any | None:
    for name in names:
        value = load_json_if_exists(root / name)
        if value is not None:
            return value
    return None


def collect_candidate_ids(value: Any, *, keywords: tuple[str, ...]) -> list[str]:
    hits: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                key_str = str(key)
                lowered_key = key_str.lower()

                if any(keyword in lowered_key for keyword in keywords):
                    if isinstance(item, str):
                        hits.add(item)
                    elif isinstance(item, list):
                        hits.update(element for element in item if isinstance(element, str))

                visit(item)

        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(value)
    return sorted(hits)


def pick_preferred_candidate(candidates: list[str]) -> str:
    if not candidates:
        return ""

    def score(value: str) -> tuple[int, int, str]:
        lowered = value.lower()
        looks_like_long_hash = len(value) >= 16 and all(char in "0123456789abcdef" for char in lowered)
        starts_like_projection = lowered.startswith("proj")
        starts_like_event = lowered.startswith("event") or lowered.endswith("event")
        return (
            0 if starts_like_projection else 1 if starts_like_event else 2 if not looks_like_long_hash else 3,
            len(value),
            value,
        )

    return sorted(candidates, key=score)[0]


def load_fixture_artifacts(root: Path = DEFAULT_FIXTURE_DIR) -> tuple[Any, Any, Any, Any, Any]:
    execution_graph = load_first_existing(root, "execution_graph.json", "graph.json")
    event_log = load_first_existing(root, "event_log.json", "events.json")
    knowledge_base = load_jsonl_if_exists(root / "kb_export.jsonl")
    if knowledge_base is None:
        knowledge_base = load_first_existing(root, "kb_export.json", "knowledge_base.json", "kb.json")
    replay_metadata = load_first_existing(root, "replay_metadata.json", "metadata.json")
    manifest = load_first_existing(root, "manifest.json")

    if execution_graph is not None:
        execution_graph = _wrap(execution_graph)
    if event_log is not None:
        event_log = _wrap({"events": event_log})
    if knowledge_base is not None:
        if isinstance(knowledge_base, list):
            knowledge_base = _wrap({"facts": knowledge_base})
        else:
            knowledge_base = _wrap(knowledge_base)
    if replay_metadata is not None:
        replay_metadata = _wrap(replay_metadata)

    return execution_graph, event_log, knowledge_base, replay_metadata, manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run static explainability over a frozen CORE replay fixture."
    )
    parser.add_argument(
        "--fixture",
        default=str(DEFAULT_FIXTURE_DIR),
        help="Path to frozen explainability fixture.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Print a small human-readable preface before JSON output.",
    )
    return parser.parse_args()


def build_report(root: Path = DEFAULT_FIXTURE_DIR) -> dict[str, Any]:
    execution_graph, event_log, knowledge_base, replay_metadata, manifest = load_fixture_artifacts(root)

    if execution_graph is None:
        raise SystemExit(f"Missing execution graph fixture under {root}")

    explainer = StaticExplainer(
        execution_graph=execution_graph,
        event_log=event_log,
        knowledge_base=knowledge_base,
        replay_metadata=replay_metadata,
        manifest=manifest,
    )

    projection_candidates = collect_candidate_ids(
        execution_graph.to_dict() if hasattr(execution_graph, "to_dict") else execution_graph,
        keywords=("projection",),
    )
    event_candidates = collect_candidate_ids(
        event_log.to_dict() if hasattr(event_log, "to_dict") else (event_log or execution_graph),
        keywords=("event",),
    )
    fact_candidates = collect_candidate_ids(
        knowledge_base.to_dict() if hasattr(knowledge_base, "to_dict") else (knowledge_base or execution_graph),
        keywords=("fact",),
    )

    projection_id = pick_preferred_candidate(projection_candidates) or "projection:missing"
    event_id = pick_preferred_candidate(event_candidates) or "event:missing"
    fact_id = pick_preferred_candidate(fact_candidates) or "fact:missing"

    return {
        "fixture_dir": str(root),
        "cause_of_projection": explainer.cause_of_projection(projection_id).to_dict(),
        "trace_of_event": explainer.trace_of_event(event_id).to_dict(),
        "lineage_of_fact": explainer.lineage_of_fact(fact_id).to_dict(),
        "origin_projection": explainer.origin_projection(fact_id).to_dict(),
    }


def main() -> int:
    args = parse_args()
    root = Path(args.fixture)
    report = build_report(root)

    if args.pretty:
        projection_id = report["cause_of_projection"].get("target_id", "")
        event_id = report["trace_of_event"].get("target_id", "")
        fact_id = report["lineage_of_fact"].get("target_id", "")
        print("CORE explainable replay demo")
        print(f"fixture={root}")
        print(f"projection_id={projection_id}")
        print(f"event_id={event_id}")
        print(f"fact_id={fact_id}")
        print("---")

    if args.pretty:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
