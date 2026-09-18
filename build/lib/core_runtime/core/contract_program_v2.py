#!/usr/bin/env python3
"""ContractProgram v2 — Contract-Oriented Reproducible Evaluation.

Traverses 6 eslabones (PERFIL→VOCABULARIO→QUERYSPEC→RESULTADO→VISTA→EVIDENCIA),
validates DSK declarations at each crossing, emits one of 9 verdicts.

Deterministic. No LLM. Same input → same verdict.
"""
from __future__ import annotations
import hashlib, json, sys
from typing import Any

SCHEMA_VERSION = "core.contract_program.v2"
ESLABONES = ["PERFIL", "VOCABULARIO", "QUERYSPEC", "RESULTADO", "VISTA", "EVIDENCIA"]
VERDICTS = [
    "pass", "incomplete", "scale_violation", "authority_violation",
    "loss_undeclared", "temporal_violation", "translation_missing",
    "intent_unconfirmed", "aborted"
]


def evaluate_contract_v2(contract: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a ContractProgram v2 contract. Returns verdict + findings."""
    findings: list[dict[str, str]] = []

    # Validate structure
    eslabones = contract.get("eslabones", [])
    if len(eslabones) != 6:
        findings.append({"eslabon": "ALL", "code": "incomplete", "detail": f"expected 6 eslabones, got {len(eslabones)}"})
        return _result(contract, "incomplete", findings)

    # Check order and names
    for i, expected_name in enumerate(ESLABONES):
        eslabon = eslabones[i] if i < len(eslabones) else {}
        name = eslabon.get("name", "")
        if name != expected_name:
            findings.append({"eslabon": f"order_{i}", "code": "incomplete",
                            "detail": f"position {i} expected {expected_name}, got {name}"})

    if any(f["code"] == "incomplete" for f in findings):
        return _result(contract, "incomplete", findings)

    # Validate DSK declarations at each crossing
    for eslabon in eslabones:
        name = eslabon.get("name", "")
        dsk = eslabon.get("dsk_declaration", {})

        # Check composition_rule
        if not dsk.get("composition_rule"):
            findings.append({"eslabon": name, "code": "scale_violation",
                            "detail": "missing composition_rule"})

        # Check declared_loss
        loss = dsk.get("declared_loss", {})
        if not loss.get("properties") or not loss.get("evidence_refs"):
            findings.append({"eslabon": name, "code": "loss_undeclared",
                            "detail": "declared_loss missing properties or evidence_refs"})

        # Check authority_ceiling
        auth = dsk.get("authority_ceiling", "")
        if auth not in ("reference_only", "advisory_only", "domain_authoritative", "externally_validated"):
            findings.append({"eslabon": name, "code": "authority_violation",
                            "detail": f"invalid authority_ceiling: {auth}"})

        # Check temporal_invariant if present
        ti = dsk.get("temporal_invariant")
        if ti is not None:
            if not ti.get("captured_at") or not ti.get("valid_until"):
                findings.append({"eslabon": name, "code": "temporal_violation",
                                "detail": "temporal_invariant missing captured_at or valid_until"})

        # Check translation_map if present
        tm = dsk.get("translation_map")
        if tm is not None:
            if not tm.get("source_field") or not tm.get("target_field"):
                findings.append({"eslabon": name, "code": "translation_missing",
                                "detail": "translation_map missing source_field or target_field"})

        # Check paraphrase_intent if present
        pi = dsk.get("paraphrase_intent")
        if pi is not None:
            if pi.get("confirmed_by") not in ("operator", "agent"):
                findings.append({"eslabon": name, "code": "intent_unconfirmed",
                                "detail": f"paraphrase_intent.confirmed_by={pi.get('confirmed_by')!r} invalid"})
            elif pi.get("confirmed_by") == "agent":
                findings.append({"eslabon": name, "code": "intent_unconfirmed",
                                "detail": "paraphrase_intent.confirmed_by=agent (not operator)"})

    # Determine verdict from findings
    if not findings:
        verdict = "pass"
    else:
        # First non-pass finding determines verdict
        verdict = findings[0]["code"]
        if verdict not in VERDICTS:
            verdict = "aborted"

    return _result(contract, verdict, findings)


def _result(contract: dict, verdict: str, findings: list[dict]) -> dict[str, Any]:
    payload = json.dumps(contract, sort_keys=True)
    fp = "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_id": contract.get("contract_id", ""),
        "verdict": verdict,
        "findings": findings,
        "fingerprint": fp,
        "deterministic": True,
        "llm_used": False,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: contract_program_v2.py <contract.json>", file=sys.stderr)
        return 1
    contract = json.load(open(argv[1]))
    result = evaluate_contract_v2(contract)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
