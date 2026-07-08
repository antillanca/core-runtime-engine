"""Deterministic audit trail primitives.

This module is intentionally separate from the operational EventLog.
It defines a read-only audit schema, canonical fingerprints, and
derivation helpers for audit artifacts produced from already-existing
reports.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from core_runtime.core.numeric_normalization import quantize_float


AUDIT_SCHEMA_VERSION = "4.9.0"
ALLOWED_CORRELATION_PREFIXES = (
    "proposal::",
    "profile::",
    "pair::",
    "report::",
    "dataset::",
    "graph::",
    "router::",
    "gaia_pipeline::",
)


class EventAuthority(Enum):
    OBSERVATION = "observation"
    DERIVED = "derived"
    AUTHORITATIVE = "authoritative"


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        return quantize_float(value)
    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    if isinstance(value, set):
        return sorted((_normalize_value(item) for item in value), key=canonical_json)
    return value


def canonical_json(data: Any) -> str:
    return json.dumps(
        _normalize_value(data),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def compute_operational_fingerprint(payload: Any) -> str:
    canonical = canonical_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_audit_fingerprint(payload: Any) -> str:
    canonical = canonical_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_graph_fingerprint(payload: Any) -> str:
    canonical = canonical_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_correlation_id(correlation_id: str) -> str:
    if not isinstance(correlation_id, str):
        raise TypeError(f"Expected string correlation_id, got {type(correlation_id).__name__}")
    normalized = correlation_id.strip()
    if not normalized:
        raise ValueError("correlation_id must not be empty")
    if not normalized.startswith(ALLOWED_CORRELATION_PREFIXES):
        raise ValueError(
            "correlation_id must use a semantic namespace such as "
            "'proposal::<id>' or 'report::<id>'"
        )
    namespace, _, suffix = normalized.partition("::")
    if not namespace or not suffix.strip():
        raise ValueError("correlation_id must include a non-empty semantic identifier")
    return normalized


def proposal_correlation_id(proposal_id: str) -> str:
    return _validate_correlation_id(f"proposal::{proposal_id.strip()}")


def profile_correlation_id(profile_id: str) -> str:
    return _validate_correlation_id(f"profile::{profile_id.strip()}")


def pair_correlation_id(pair_id: str) -> str:
    return _validate_correlation_id(f"pair::{pair_id.strip()}")


def report_correlation_id(report_id: str) -> str:
    return _validate_correlation_id(f"report::{report_id.strip()}")


def dataset_correlation_id(dataset_id: str) -> str:
    return _validate_correlation_id(f"dataset::{dataset_id.strip()}")


def graph_correlation_id(graph_id: str) -> str:
    return _validate_correlation_id(f"graph::{graph_id.strip()}")


def router_correlation_id(router_id: str) -> str:
    return _validate_correlation_id(f"router::{router_id.strip()}")


def gaia_pipeline_correlation_id(run_id: str) -> str:
    return _validate_correlation_id(f"gaia_pipeline::{run_id.strip()}")


def pair_canonical_key(pair: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(pair.get("pair_id", "")),
        str(pair.get("profile_id", "")),
        str(pair.get("proposal_id", "")),
        str(pair.get("actual_status", "")),
    )


def compute_audit_event_id(
    event_type: str,
    correlation_id: str,
    logical_tick: int,
    payload_hash: str,
) -> str:
    canonical = canonical_json(
        {
            "correlation_id": _validate_correlation_id(correlation_id),
            "event_type": str(event_type),
            "logical_tick": int(logical_tick),
            "payload_hash": str(payload_hash),
        }
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _event_body(
    *,
    event_id: str,
    event_type: str,
    authority: EventAuthority,
    logical_tick: int,
    correlation_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "event_id": event_id,
        "event_type": event_type,
        "authority": authority.value,
        "logical_tick": int(logical_tick),
        "correlation_id": correlation_id,
        "payload": payload,
    }


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    event_type: str
    authority: EventAuthority
    logical_tick: int
    correlation_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""
    schema_version: str = AUDIT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.logical_tick, int):
            raise TypeError(f"Expected int logical_tick, got {type(self.logical_tick).__name__}")
        if self.logical_tick < 0:
            raise ValueError("logical_tick must be non-negative")

        normalized_authority = self.authority
        if not isinstance(normalized_authority, EventAuthority):
            normalized_authority = EventAuthority(str(normalized_authority))

        normalized_correlation_id = _validate_correlation_id(self.correlation_id)
        normalized_payload = _normalize_value(dict(self.payload))
        payload_hash = compute_audit_fingerprint(normalized_payload)
        expected_event_id = compute_audit_event_id(
            self.event_type,
            normalized_correlation_id,
            self.logical_tick,
            payload_hash,
        )
        body = _event_body(
            event_id=expected_event_id,
            event_type=self.event_type,
            authority=normalized_authority,
            logical_tick=self.logical_tick,
            correlation_id=normalized_correlation_id,
            payload=normalized_payload,
        )
        expected_fingerprint = compute_audit_fingerprint(body)

        if self.event_id and self.event_id != expected_event_id:
            raise ValueError("event_id does not match deterministic audit fingerprint")
        if self.fingerprint and self.fingerprint != expected_fingerprint:
            raise ValueError("fingerprint does not match deterministic audit fingerprint")

        object.__setattr__(self, "authority", normalized_authority)
        object.__setattr__(self, "correlation_id", normalized_correlation_id)
        object.__setattr__(self, "payload", normalized_payload)
        object.__setattr__(self, "event_id", expected_event_id)
        object.__setattr__(self, "fingerprint", expected_fingerprint)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "authority": self.authority.value,
            "logical_tick": self.logical_tick,
            "correlation_id": self.correlation_id,
            "payload": _normalize_value(self.payload),
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AuditEvent":
        return cls(
            event_id=str(data.get("event_id", "")),
            event_type=str(data.get("event_type", "")),
            authority=EventAuthority(str(data.get("authority", EventAuthority.DERIVED.value))),
            logical_tick=int(data.get("logical_tick", 0)),
            correlation_id=str(data.get("correlation_id", "")),
            payload=dict(data.get("payload", {})),
            fingerprint=str(data.get("fingerprint", "")),
            schema_version=str(data.get("schema_version", AUDIT_SCHEMA_VERSION)),
        )


def canonical_event_sort_key(event: AuditEvent) -> tuple[int, str, str, str]:
    return (
        int(event.logical_tick),
        event.correlation_id,
        event.event_type,
        event.event_id,
    )


def _compatibility_terminal_event_type(pair: Mapping[str, Any]) -> str:
    status = str(pair.get("actual_status", "")).lower()
    profile_id = str(pair.get("profile_id", "")).lower()
    pair_id = str(pair.get("pair_id", "")).lower()
    if status != "compatible":
        return "CompatibilityRejected"
    if "certified" in pair_id or "certified" in profile_id:
        return "CompatibilityCertified"
    return "CompatibilityAccepted"


def derive_compatibility_audit_events(
    report: Mapping[str, Any],
    *,
    source_fingerprint: str | None = None,
) -> list[AuditEvent]:
    report_fingerprint = source_fingerprint or compute_operational_fingerprint(report)
    report_id = report_fingerprint
    correlation = report_correlation_id(report_id)
    pairs = list(report.get("matrix", []))
    if not pairs:
        pairs = list(report.get("pairs", []))
    pairs = sorted(
        [pair for pair in pairs if isinstance(pair, Mapping)],
        key=pair_canonical_key,
    )

    events: list[AuditEvent] = []
    for index, pair in enumerate(pairs):
        pair_id = str(pair.get("pair_id", "")).strip()
        if not pair_id:
            continue
        pair_correlation = pair_correlation_id(pair_id)
        payload = {
            "pair_id": pair_id,
            "profile_id": str(pair.get("profile_id", "")),
            "proposal_id": str(pair.get("proposal_id", "")),
            "expected_status": str(pair.get("expected_status", "")),
            "actual_status": str(pair.get("actual_status", "")),
            "incompatible_reason": pair.get("incompatible_reason"),
            "report_id": report_id,
        }
        events.append(
            AuditEvent(
                event_id="",
                event_type="CompatibilityChecked",
                authority=EventAuthority.DERIVED,
                logical_tick=index * 2,
                correlation_id=pair_correlation,
                payload=payload,
            )
        )
        terminal_type = _compatibility_terminal_event_type(pair)
        if terminal_type == "CompatibilityRejected":
            terminal_payload = {
                **payload,
                "decision": "rejected",
            }
        elif terminal_type == "CompatibilityCertified":
            terminal_payload = {
                **payload,
                "decision": "certified",
            }
        else:
            terminal_payload = {
                **payload,
                "decision": "accepted",
            }
        events.append(
            AuditEvent(
                event_id="",
                event_type=terminal_type,
                authority=EventAuthority.DERIVED,
                logical_tick=index * 2 + 1,
                correlation_id=pair_correlation,
                payload=terminal_payload,
            )
        )

    report_payload = {
        "report_id": report_id,
        "report_schema": str(report.get("schema", "")),
        "status": str(report.get("status", "")),
        "summary": dict(report.get("summary", {})) if isinstance(report.get("summary", {}), Mapping) else report.get("summary", {}),
        "pair_count": len(pairs),
    }
    events.append(
        AuditEvent(
            event_id="",
            event_type="CompatibilityMatrixReported",
            authority=EventAuthority.DERIVED,
            logical_tick=len(events),
            correlation_id=correlation,
            payload=report_payload,
        )
    )
    return events


def _decision_event_type(decision: str) -> str:
    normalized = decision.lower().strip()
    if normalized == "certified":
        return "ProposalCertified"
    if normalized == "accepted":
        return "ProposalAccepted"
    if normalized == "unsafe":
        return "ProposalUnsafe"
    if normalized == "unsupported":
        return "ProposalUnsupported"
    if normalized == "missing_evidence":
        return "ProposalMissingEvidence"
    return "ProposalRejected"


def derive_expert_report_audit_events(
    report: Mapping[str, Any],
    *,
    source_fingerprint: str | None = None,
) -> list[AuditEvent]:
    report_fingerprint = source_fingerprint or compute_operational_fingerprint(report)
    report_id = report_fingerprint
    correlation = report_correlation_id(report_id)
    proposals = list(report.get("proposals", []))
    proposals = sorted(
        [proposal for proposal in proposals if isinstance(proposal, Mapping)],
        key=lambda proposal: (
            str(proposal.get("proposal_id", "")),
            str(proposal.get("file", "")),
            str(proposal.get("decision", "")),
        ),
    )

    events: list[AuditEvent] = []
    for index, proposal in enumerate(proposals):
        proposal_id = str(proposal.get("proposal_id", "")).strip()
        if not proposal_id:
            continue
        proposal_correlation = proposal_correlation_id(proposal_id)
        payload = {
            "proposal_id": proposal_id,
            "decision": str(proposal.get("decision", "")),
            "reason_code": str(proposal.get("reason_code", "")),
            "status": str(proposal.get("status", "")),
            "file": str(proposal.get("file", "")),
            "report_id": report_id,
        }
        events.append(
            AuditEvent(
                event_id="",
                event_type="ProposalEvaluated",
                authority=EventAuthority.DERIVED,
                logical_tick=index * 2,
                correlation_id=proposal_correlation,
                payload=payload,
            )
        )
        decision_event_type = _decision_event_type(payload["decision"])
        events.append(
            AuditEvent(
                event_id="",
                event_type=decision_event_type,
                authority=EventAuthority.DERIVED,
                logical_tick=index * 2 + 1,
                correlation_id=proposal_correlation,
                payload=payload,
            )
        )

    report_payload = {
        "report_id": report_id,
        "report_schema": str(report.get("schema", "")),
        "status": str(report.get("status", "")),
        "summary": dict(report.get("summary", {})) if isinstance(report.get("summary", {}), Mapping) else report.get("summary", {}),
        "proposal_count": len(proposals),
    }
    events.append(
        AuditEvent(
            event_id="",
            event_type="ExpertProposalBatchReported",
            authority=EventAuthority.DERIVED,
            logical_tick=len(events),
            correlation_id=correlation,
            payload=report_payload,
        )
    )
    return events


def _router_validation_audit_events(
    payload: Mapping[str, Any],
    *,
    source_fingerprint: str | None = None,
) -> list[AuditEvent]:
    routing_id = str(payload.get("routing_id", "")).strip() or source_fingerprint or "router"
    warnings = [item for item in payload.get("warnings", []) if isinstance(item, Mapping)]
    errors = [item for item in payload.get("errors", []) if isinstance(item, Mapping)]
    event_payload = {
        "routing_id": routing_id,
        "validation_schema": str(payload.get("schema", "")),
        "status": str(payload.get("status", "")),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "error_codes": [
            str(item.get("code", "")).strip()
            for item in errors
            if str(item.get("code", "")).strip()
        ],
        "warning_codes": [
            str(item.get("code", "")).strip()
            for item in warnings
            if str(item.get("code", "")).strip()
        ],
        "source_fingerprint": source_fingerprint or compute_operational_fingerprint(payload),
    }
    return [
        AuditEvent(
            event_id="",
            event_type="RouterFixtureValidated",
            authority=EventAuthority.DERIVED,
            logical_tick=0,
            correlation_id=router_correlation_id(routing_id),
            payload=event_payload,
        )
    ]


def _router_evaluation_audit_events(
    payload: Mapping[str, Any],
    *,
    source_fingerprint: str | None = None,
) -> list[AuditEvent]:
    routing_id = str(payload.get("routing_id", "")).strip() or source_fingerprint or "router"
    profile_id = str(payload.get("profile_id", "")).strip()
    summary = payload.get("evaluation_summary", {})
    summary_payload = dict(summary) if isinstance(summary, Mapping) else {}
    selected_experts = [item for item in payload.get("selected_experts", []) if isinstance(item, Mapping)]
    rejected_experts = [item for item in payload.get("rejected_experts", []) if isinstance(item, Mapping)]
    selected_expert_records = [
        {
            "decision": "selected",
            "expert_id": str(item.get("expert_id", "")).strip(),
            "proposal_id": str(item.get("proposal_id", "")).strip(),
            "reason": str(item.get("reason", "")).strip(),
        }
        for item in selected_experts
        if str(item.get("expert_id", "")).strip() and str(item.get("proposal_id", "")).strip()
    ]
    rejected_expert_records = [
        {
            "decision": "rejected",
            "expert_id": str(item.get("expert_id", "")).strip(),
            "proposal_id": str(item.get("proposal_id", "")).strip(),
            "reason": str(item.get("reason", "")).strip(),
        }
        for item in rejected_experts
        if str(item.get("expert_id", "")).strip() and str(item.get("proposal_id", "")).strip()
    ]
    event_payload = {
        "routing_id": routing_id,
        "profile_id": profile_id,
        "evaluation_schema": str(payload.get("schema", "")),
        "status": str(payload.get("status", "")),
        "selected_count": int(summary_payload.get("selected_count", len(selected_experts))),
        "rejected_count": int(summary_payload.get("rejected_count", len(rejected_experts))),
        "total_proposals": int(summary_payload.get("total_proposals", len(selected_experts) + len(rejected_experts))),
        "reason_codes": [
            str(code).strip()
            for code in payload.get("reason_codes", [])
            if str(code).strip()
        ],
        "selected_expert_ids": [
            str(item.get("expert_id", "")).strip()
            for item in selected_experts
            if str(item.get("expert_id", "")).strip()
        ],
        "rejected_expert_ids": [
            str(item.get("expert_id", "")).strip()
            for item in rejected_experts
            if str(item.get("expert_id", "")).strip()
        ],
        "selected_experts": selected_expert_records,
        "rejected_experts": rejected_expert_records,
        "source_fingerprint": source_fingerprint or compute_operational_fingerprint(payload),
    }
    return [
        AuditEvent(
            event_id="",
            event_type="RouterEligibilityEvaluated",
            authority=EventAuthority.DERIVED,
            logical_tick=0,
            correlation_id=router_correlation_id(routing_id),
            payload=event_payload,
        )
    ]


def _router_report_audit_events(
    payload: Mapping[str, Any],
    *,
    source_fingerprint: str | None = None,
) -> list[AuditEvent]:
    report_id = source_fingerprint or compute_operational_fingerprint(payload)
    summary = payload.get("summary", {})
    summary_payload = dict(summary) if isinstance(summary, Mapping) else {}
    fixtures = [item for item in payload.get("fixtures", []) if isinstance(item, Mapping)]
    event_payload = {
        "report_id": report_id,
        "report_schema": str(payload.get("schema", "")),
        "status": str(payload.get("status", "")),
        "summary": summary_payload,
        "fixture_count": len(fixtures),
        "fixture_files": [
            str(item.get("file", "")).strip()
            for item in fixtures
            if str(item.get("file", "")).strip()
        ],
        "source_fingerprint": source_fingerprint or compute_operational_fingerprint(payload),
    }
    return [
        AuditEvent(
            event_id="",
            event_type="RouterBatchReportGenerated",
            authority=EventAuthority.DERIVED,
            logical_tick=0,
            correlation_id=report_correlation_id(report_id),
            payload=event_payload,
        )
    ]


def _router_replay_audit_events(
    payload: Mapping[str, Any],
    *,
    source_fingerprint: str | None = None,
) -> list[AuditEvent]:
    routing_id = str(payload.get("routing_id", "")).strip()
    event_type = "RouterReplayCertified" if str(payload.get("status", "")).strip() == "certified" else "RouterReplayDiverged"
    run_1 = payload.get("run_1", {})
    run_2 = payload.get("run_2", {})
    event_payload = {
        "replay_schema": str(payload.get("replay_schema", payload.get("schema", ""))),
        "status": str(payload.get("status", "")),
        "fixture": str(payload.get("fixture", "")).strip(),
        "routing_id": routing_id,
        "fingerprint": payload.get("fingerprint"),
        "diff": payload.get("diff"),
        "run_1_output_hash": run_1.get("output_hash") if isinstance(run_1, Mapping) else None,
        "run_2_output_hash": run_2.get("output_hash") if isinstance(run_2, Mapping) else None,
        "source_fingerprint": source_fingerprint or compute_operational_fingerprint(payload),
    }
    correlation_seed = routing_id or source_fingerprint or compute_operational_fingerprint(payload)
    return [
        AuditEvent(
            event_id="",
            event_type=event_type,
            authority=EventAuthority.DERIVED,
            logical_tick=0,
            correlation_id=router_correlation_id(correlation_seed),
            payload=event_payload,
        )
    ]


def _gaia_surrogate_sort_key(entry: Mapping[str, Any]) -> tuple[int, str, int, str]:
    source_id = str(entry.get("source_id", "")).strip()
    row_index = entry.get("row_index", 0)
    try:
        numeric_source_id = int(source_id)
    except ValueError:
        numeric_source_id = 0
    try:
        numeric_row_index = int(row_index)
    except (TypeError, ValueError):
        numeric_row_index = 0
    return (
        numeric_row_index,
        source_id,
        numeric_source_id,
        str(entry.get("proposal_id", "")),
    )


def derive_gaia_surrogate_audit_events(
    evaluation: Mapping[str, Any],
    *,
    source_fingerprint: str | None = None,
) -> list[AuditEvent]:
    evaluation_fingerprint = source_fingerprint or compute_operational_fingerprint(evaluation)
    run_id = str(evaluation.get("run_id", "")).strip() or evaluation_fingerprint
    correlation = gaia_pipeline_correlation_id(run_id)
    proposal_id = str(evaluation.get("proposal_id", "")).strip()
    proposal_hash = str(evaluation.get("proposal_hash", "")).strip()
    weights_hash = str(evaluation.get("weights_hash", "")).strip()
    mismatches = list(evaluation.get("mismatches", []))
    mismatches = sorted(
        [entry for entry in mismatches if isinstance(entry, Mapping)],
        key=_gaia_surrogate_sort_key,
    )

    total_evaluated = int(evaluation.get("total_evaluated", len(mismatches)))
    correct_predictions = int(evaluation.get("correct_predictions", max(total_evaluated - len(mismatches), 0)))
    agreement_rate = float(evaluation.get("agreement_rate", 0.0))
    decision_threshold = float(evaluation.get("decision_threshold", 0.5))

    summary_payload = {
        "run_id": run_id,
        "proposal_id": proposal_id,
        "proposal_hash": proposal_hash,
        "evaluation_hash": evaluation_fingerprint,
        "weights_hash": weights_hash,
        "feature_columns": list(evaluation.get("feature_columns", [])),
        "decision_threshold": decision_threshold,
        "total_evaluated": total_evaluated,
        "correct_predictions": correct_predictions,
        "mismatch_count": len(mismatches),
        "agreement_rate": agreement_rate,
    }
    events: list[AuditEvent] = [
        AuditEvent(
            event_id="",
            event_type="GaiaSurrogateProposalEvaluated",
            authority=EventAuthority.DERIVED,
            logical_tick=0,
            correlation_id=correlation,
            payload=summary_payload,
        )
    ]

    for index, mismatch in enumerate(mismatches, start=1):
        mismatch_payload = {
            "run_id": run_id,
            "proposal_id": proposal_id,
            "source_id": str(mismatch.get("source_id", "")).strip(),
            "row_index": int(mismatch.get("row_index", index)),
            "predicted_nearby": bool(mismatch.get("predicted_nearby", False)),
            "actual_nearby": bool(mismatch.get("actual_nearby", False)),
            "probability": mismatch.get("probability"),
            "distance_pc": mismatch.get("distance_pc"),
            "decision_threshold": decision_threshold,
            "evaluation_hash": evaluation_fingerprint,
        }
        events.append(
            AuditEvent(
                event_id="",
                event_type="GaiaSurrogatePredictionMismatch",
                authority=EventAuthority.DERIVED,
                logical_tick=index,
                correlation_id=correlation,
                payload=mismatch_payload,
            )
        )

    completion_payload = {
        "run_id": run_id,
        "proposal_id": proposal_id,
        "evaluation_hash": evaluation_fingerprint,
        "proposal_hash": proposal_hash,
        "weights_hash": weights_hash,
        "total_evaluated": total_evaluated,
        "mismatch_count": len(mismatches),
        "agreement_rate": agreement_rate,
        "status": str(evaluation.get("status", "passed")),
    }
    events.append(
        AuditEvent(
            event_id="",
            event_type="GaiaSurrogateEvaluationCompleted",
            authority=EventAuthority.DERIVED,
            logical_tick=len(events),
            correlation_id=correlation,
            payload=completion_payload,
        )
    )
    return events


def derive_events_for_source(
    *,
    artifact_type: str,
    artifact_payload: Mapping[str, Any],
    source_fingerprint: str | None = None,
) -> list[AuditEvent]:
    normalized_type = artifact_type.strip().lower()
    if normalized_type == "compatibility_matrix":
        return derive_compatibility_audit_events(artifact_payload, source_fingerprint=source_fingerprint)
    if normalized_type == "expert_report":
        return derive_expert_report_audit_events(artifact_payload, source_fingerprint=source_fingerprint)
    if normalized_type == "expert_router_validation":
        return _router_validation_audit_events(artifact_payload, source_fingerprint=source_fingerprint)
    if normalized_type == "expert_router_evaluation":
        return _router_evaluation_audit_events(artifact_payload, source_fingerprint=source_fingerprint)
    if normalized_type in {"expert_router_report", "expert_router_batch_report"}:
        return _router_report_audit_events(artifact_payload, source_fingerprint=source_fingerprint)
    if normalized_type in {"expert_router_replay_certification", "expert_router_replay_certification_batch"}:
        return _router_replay_audit_events(artifact_payload, source_fingerprint=source_fingerprint)
    if normalized_type == "gaia_surrogate":
        return derive_gaia_surrogate_audit_events(artifact_payload, source_fingerprint=source_fingerprint)
    raise ValueError(f"Unsupported audit source type: {artifact_type}")
