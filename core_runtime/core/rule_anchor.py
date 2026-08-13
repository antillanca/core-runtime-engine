"""Deterministic primitives for frozen-rule approval and blockchain anchoring.

CORE validates rule artifacts and signatures off-chain.  The blockchain
contract only timestamps a Merkle root and its manifest fingerprint.  No
private rule content, blinding nonce, wallet secret, or runtime authority is
placed on-chain.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from importlib.resources import files
from typing import Any

from jsonschema import Draft7Validator

from core_runtime.core.canonicalization import canonical_json_dumps


SCHEMA_ROOT = files("core_runtime").joinpath("data", "schemas", "core")
CONTRACT_ROOT = files("core_runtime").joinpath("data", "contracts")

FROZEN_RULE_SET_SCHEMA = "core.frozen_rule_set.v1"
APPROVAL_REQUEST_SCHEMA = "core.rule_approval_request.v1"
APPROVAL_SCHEMA = "core.rule_approval.v1"
ANCHOR_BATCH_SCHEMA = "core.rule_anchor_batch.v1"
UNSIGNED_TRANSACTION_SCHEMA = "core.unsigned_rule_anchor_transaction.v1"
UNSIGNED_DEPLOYMENT_SCHEMA = "core.unsigned_rule_anchor_deployment.v1"
CHAIN_EVIDENCE_SCHEMA = "core.rule_anchor_chain_evidence.v1"

FINGERPRINT_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
SIGNATURE_RE = re.compile(r"^0x[a-fA-F0-9]{130}$")

PRIVATE_COMMITMENT_DOMAIN = b"CORE_PRIVATE_RULE_COMMITMENT_V1\x00"
MERKLE_LEAF_DOMAIN = b"\x00CORE_RULE_ANCHOR_LEAF_V1\x00"
MERKLE_NODE_DOMAIN = b"\x01CORE_RULE_ANCHOR_NODE_V1\x00"
APPROVAL_MESSAGE_HEADER = "CORE FrozenRuleSet Approval v1"

# Keccak-256("anchorRuleBatch(bytes32,bytes32,uint32,uint8)")[:4].
# The full signature and selector are independently checked in tests/CI.
ANCHOR_RULE_BATCH_SELECTOR = "6919e458"

# secp256k1 group order, used to reject malleable high-s signatures.
SECP256K1_N = int(
    "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141",
    16,
)

FORBIDDEN_WALLET_SECRET_KEYS = frozenset(
    {
        "private_key",
        "private-key",
        "seed",
        "seed_phrase",
        "mnemonic",
        "password",
        "signing_key",
        "raw_transaction",
    }
)
UNSIGNED_DEPLOYMENT_WARNINGS = (
    "Review and sign this deployment only in an external wallet.",
    "After confirmation, verify deployed runtime bytecode before creating approvals.",
    "CORE never requests or stores wallet secrets and never broadcasts.",
)


def error(code: str, message: str, field: str | None = None, **extra: Any) -> dict[str, Any]:
    """Return a stable validator error envelope entry."""

    result: dict[str, Any] = {"code": code, "message": message}
    if field is not None:
        result["field"] = field
    result.update(extra)
    return result


def sha256_fingerprint_bytes(payload: bytes) -> str:
    """Return a prefixed SHA-256 fingerprint."""

    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def canonical_fingerprint(payload: Any) -> str:
    """Fingerprint canonical UTF-8 JSON using SHA-256."""

    return sha256_fingerprint_bytes(canonical_json_dumps(payload).encode("utf-8"))


def artifact_fingerprint(payload: Mapping[str, Any], field: str = "fingerprint") -> str:
    """Fingerprint an artifact while excluding its declared fingerprint."""

    return canonical_fingerprint({key: value for key, value in payload.items() if key != field})


def load_verified_rule_anchor_build() -> tuple[dict[str, Any], str]:
    """Load frozen contract artifacts and verify every declared build digest."""

    build = json.loads((CONTRACT_ROOT / "CoreRuleAnchor.build.json").read_text(encoding="utf-8"))
    source = (CONTRACT_ROOT / "CoreRuleAnchor.sol").read_bytes()
    abi = json.loads((CONTRACT_ROOT / "CoreRuleAnchor.abi.json").read_text(encoding="utf-8"))
    creation_hex = (CONTRACT_ROOT / "CoreRuleAnchor.bin").read_text(encoding="utf-8").strip()
    runtime_hex = (CONTRACT_ROOT / "CoreRuleAnchor.runtime.bin").read_text(encoding="utf-8").strip()
    checks = {
        "source_sha256": sha256_fingerprint_bytes(source),
        "abi_canonical_sha256": canonical_fingerprint(abi),
        "creation_bytecode_sha256": sha256_fingerprint_bytes(bytes.fromhex(creation_hex)),
        "runtime_bytecode_sha256": sha256_fingerprint_bytes(bytes.fromhex(runtime_hex)),
    }
    for field, computed in checks.items():
        if build.get(field) != computed:
            raise ValueError(f"frozen contract build mismatch: {field}")
    return build, creation_hex


def _wallet_secret_errors(payload: Any, artifact_label: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []

    def scan(value: Any, field: str = "$") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_field = f"{field}.{key}"
                if str(key).lower() in FORBIDDEN_WALLET_SECRET_KEYS:
                    errors.append(
                        error(
                            "wallet_secret_forbidden",
                            f"{artifact_label} artifacts cannot contain wallet secrets.",
                            child_field,
                        )
                    )
                scan(child, child_field)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                scan(child, f"{field}[{index}]")

    scan(payload)
    return errors


def fingerprint_bytes(value: str) -> bytes:
    """Decode a canonical ``sha256:<hex>`` fingerprint."""

    if not FINGERPRINT_RE.fullmatch(value):
        raise ValueError("fingerprint must match sha256:<64 lowercase hex characters>")
    return bytes.fromhex(value.removeprefix("sha256:"))


def bytes32_hex(value: str) -> str:
    """Convert a SHA-256 fingerprint to an EVM bytes32 hex value."""

    return "0x" + fingerprint_bytes(value).hex()


def _schema_errors(payload: Any, schema_filename: str) -> list[dict[str, Any]]:
    schema_path = SCHEMA_ROOT / schema_filename
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema)
    errors: list[dict[str, Any]] = []
    for item in sorted(validator.iter_errors(payload), key=lambda entry: list(entry.absolute_path)):
        field = ".".join(str(part) for part in item.absolute_path) or "$"
        errors.append(error("schema_validation_error", item.message, field))
    return errors


def _valid_timezone_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _normalized_addresses(values: Iterable[str]) -> list[str]:
    return [value.lower() for value in values]


def validate_frozen_rule_set_payload(payload: Any) -> list[dict[str, Any]]:
    """Validate a public frozen rule set or a private commitment envelope."""

    errors = _schema_errors(payload, "frozen_rule_set.v1.json")
    if not isinstance(payload, dict):
        return errors

    frozen_at = payload.get("frozen_at")
    if frozen_at is not None and not _valid_timezone_timestamp(frozen_at):
        errors.append(
            error(
                "invalid_frozen_at",
                "frozen_at must be an ISO 8601 timestamp with an explicit timezone.",
                "frozen_at",
            )
        )

    governance = payload.get("governance")
    if isinstance(governance, dict):
        signers = governance.get("authorized_signers")
        threshold = governance.get("approval_threshold")
        if isinstance(signers, list) and all(isinstance(item, str) for item in signers):
            normalized = _normalized_addresses(signers)
            if len(set(normalized)) != len(normalized):
                errors.append(
                    error(
                        "duplicate_authorized_signer",
                        "authorized_signers must be unique ignoring address case.",
                        "governance.authorized_signers",
                    )
                )
            if isinstance(threshold, int) and not isinstance(threshold, bool) and threshold > len(signers):
                errors.append(
                    error(
                        "approval_threshold_unreachable",
                        "approval_threshold cannot exceed the number of authorized signers.",
                        "governance.approval_threshold",
                    )
                )

    content = payload.get("content")
    rule_class = payload.get("rule_class")
    visibility = payload.get("visibility")
    if isinstance(content, dict):
        mode = content.get("mode")
        if rule_class == "general" and (visibility != "public" or mode != "public"):
            errors.append(
                error(
                    "general_rule_must_be_public",
                    "General rules must publish their complete frozen content.",
                    "visibility",
                )
            )
        if rule_class == "personal" and (
            visibility != "private_commitment" or mode != "private_commitment"
        ):
            errors.append(
                error(
                    "personal_rule_must_be_private_commitment",
                    "Personal rules must expose only a blinded commitment.",
                    "visibility",
                )
            )

        if mode == "public":
            rules = content.get("rules")
            if isinstance(rules, list):
                rule_ids = [item.get("rule_id") for item in rules if isinstance(item, dict)]
                if len(rule_ids) != len(set(rule_ids)):
                    errors.append(
                        error(
                            "duplicate_rule_id",
                            "Public rule_id values must be unique within a frozen rule set.",
                            "content.rules",
                        )
                    )
                for index, rule in enumerate(rules):
                    if not isinstance(rule, dict):
                        continue
                    if rule.get("domain") != payload.get("domain"):
                        errors.append(
                            error(
                                "rule_domain_mismatch",
                                "Every public rule domain must equal the rule-set domain.",
                                f"content.rules.{index}.domain",
                            )
                        )
                    steps = rule.get("steps")
                    if isinstance(steps, list):
                        step_ids = [step.get("step_id") for step in steps if isinstance(step, dict)]
                        if len(step_ids) != len(set(step_ids)):
                            errors.append(
                                error(
                                    "duplicate_step_id",
                                    "step_id values must be unique within each rule.",
                                    f"content.rules.{index}.steps",
                                )
                            )

        if mode == "private_commitment":
            commitment = content.get("commitment")
            if commitment == "sha256:" + ("0" * 64):
                errors.append(
                    error(
                        "zero_private_commitment",
                        "A private commitment cannot be the all-zero digest.",
                        "content.commitment",
                    )
                )

    declared = payload.get("fingerprint")
    if isinstance(declared, str) and FINGERPRINT_RE.fullmatch(declared):
        expected = artifact_fingerprint(payload)
        if declared != expected:
            errors.append(
                error(
                    "fingerprint_mismatch",
                    "Frozen rule-set fingerprint does not match canonical content.",
                    "fingerprint",
                    declared=declared,
                    computed=expected,
                )
            )

    return errors


def private_content_fingerprint(private_payload: Any) -> str:
    """Fingerprint private content without publishing that digest."""

    return canonical_fingerprint(private_payload)


def private_rule_commitment(private_payload: Any, blinding_nonce: bytes) -> str:
    """Create a domain-separated commitment hiding low-entropy private rules."""

    if len(blinding_nonce) != 32:
        raise ValueError("blinding_nonce must contain exactly 32 bytes")
    content_digest = fingerprint_bytes(private_content_fingerprint(private_payload))
    return sha256_fingerprint_bytes(PRIVATE_COMMITMENT_DOMAIN + content_digest + blinding_nonce)


def verify_private_rule_opening(
    private_payload: Any,
    blinding_nonce_hex: str,
    expected_commitment: str,
) -> bool:
    """Verify a private commitment opening locally."""

    if not re.fullmatch(r"[a-f0-9]{64}", blinding_nonce_hex):
        return False
    if not FINGERPRINT_RE.fullmatch(expected_commitment):
        return False
    return private_rule_commitment(private_payload, bytes.fromhex(blinding_nonce_hex)) == expected_commitment


def approval_message(rule_set_fingerprint: str, chain_id: int, verifying_contract: str) -> str:
    """Build the exact human-readable EIP-191 approval message."""

    fingerprint_bytes(rule_set_fingerprint)
    if not isinstance(chain_id, int) or isinstance(chain_id, bool) or chain_id <= 0:
        raise ValueError("chain_id must be a positive integer")
    if not ADDRESS_RE.fullmatch(verifying_contract):
        raise ValueError("verifying_contract must be an EVM address")
    return "\n".join(
        (
            APPROVAL_MESSAGE_HEADER,
            f"rule_set_fingerprint: {rule_set_fingerprint}",
            f"chain_id: {chain_id}",
            f"verifying_contract: {verifying_contract.lower()}",
            "decision: approve_frozen_rule_set",
        )
    )


def build_approval_request(
    rule_set_fingerprint: str,
    chain_id: int,
    verifying_contract: str,
    signer: str,
) -> dict[str, Any]:
    """Build an externally signable, domain-bound approval request."""

    if not ADDRESS_RE.fullmatch(signer):
        raise ValueError("signer must be an EVM address")
    request: dict[str, Any] = {
        "schema_version": APPROVAL_REQUEST_SCHEMA,
        "type": "rule_approval_request",
        "rule_set_fingerprint": rule_set_fingerprint,
        "chain_id": chain_id,
        "verifying_contract": verifying_contract.lower(),
        "signer": signer.lower(),
        "signature_scheme": "eip191_secp256k1",
        "decision": "approve_frozen_rule_set",
        "message": approval_message(rule_set_fingerprint, chain_id, verifying_contract),
    }
    request["fingerprint"] = artifact_fingerprint(request)
    return request


def validate_approval_request_payload(payload: Any) -> list[dict[str, Any]]:
    """Validate an unsigned approval request."""

    errors = _schema_errors(payload, "rule_approval_request.v1.json")
    if not isinstance(payload, dict):
        return errors

    try:
        expected_message = approval_message(
            payload.get("rule_set_fingerprint", ""),
            payload.get("chain_id", 0),
            payload.get("verifying_contract", ""),
        )
    except (TypeError, ValueError):
        expected_message = None

    if expected_message is not None and payload.get("message") != expected_message:
        errors.append(
            error(
                "approval_message_mismatch",
                "Approval message does not match its rule, chain, and contract binding.",
                "message",
            )
        )

    declared = payload.get("fingerprint")
    if isinstance(declared, str) and FINGERPRINT_RE.fullmatch(declared):
        expected = artifact_fingerprint(payload)
        if declared != expected:
            errors.append(
                error(
                    "fingerprint_mismatch",
                    "Approval-request fingerprint does not match canonical content.",
                    "fingerprint",
                    declared=declared,
                    computed=expected,
                )
            )
    return errors


def _validate_canonical_signature(signature: str) -> list[dict[str, Any]]:
    if not SIGNATURE_RE.fullmatch(signature):
        return [
            error(
                "invalid_signature_format",
                "signature must be a 65-byte 0x-prefixed hexadecimal ECDSA signature.",
                "signature",
            )
        ]
    raw = bytes.fromhex(signature[2:])
    r_value = int.from_bytes(raw[0:32], "big")
    s_value = int.from_bytes(raw[32:64], "big")
    recovery_id = raw[64]
    errors: list[dict[str, Any]] = []
    if r_value <= 0 or r_value >= SECP256K1_N:
        errors.append(error("invalid_signature_r", "signature r is outside secp256k1 range.", "signature"))
    if s_value <= 0 or s_value > SECP256K1_N // 2:
        errors.append(
            error(
                "noncanonical_signature_s",
                "signature must use canonical low-s form.",
                "signature",
            )
        )
    if recovery_id not in {0, 1, 27, 28}:
        errors.append(
            error(
                "invalid_signature_recovery_id",
                "signature recovery id must be 0, 1, 27, or 28.",
                "signature",
            )
        )
    return errors


def recover_eip191_signer(message: str, signature: str) -> str:
    """Recover the signer address; fail closed when the crypto extra is absent."""

    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct
    except ImportError as exc:  # pragma: no cover - exercised in dependency-minimal installs
        raise RuntimeError("anchoring crypto backend unavailable; install CORE's anchoring extra") from exc

    recovered = Account.recover_message(encode_defunct(text=message), signature=signature)
    return str(recovered).lower()


def validate_rule_approval_payload(payload: Any) -> list[dict[str, Any]]:
    """Validate and cryptographically recover a frozen-rule approval."""

    errors = _schema_errors(payload, "rule_approval.v1.json")
    if not isinstance(payload, dict):
        return errors

    signature = payload.get("signature")
    if isinstance(signature, str):
        errors.extend(_validate_canonical_signature(signature))

    try:
        expected_message = approval_message(
            payload.get("rule_set_fingerprint", ""),
            payload.get("chain_id", 0),
            payload.get("verifying_contract", ""),
        )
    except (TypeError, ValueError):
        expected_message = None

    if expected_message is not None and payload.get("message") != expected_message:
        errors.append(
            error(
                "approval_message_mismatch",
                "Approval message does not match its rule, chain, and contract binding.",
                "message",
            )
        )

    if expected_message is not None and isinstance(signature, str) and not _validate_canonical_signature(signature):
        try:
            recovered = recover_eip191_signer(expected_message, signature)
        except RuntimeError as exc:
            errors.append(error("signature_verification_failed", str(exc), "signature"))
        except Exception:
            errors.append(
                error(
                    "signature_verification_failed",
                    "ECDSA recovery rejected the supplied signature.",
                    "signature",
                )
            )
        else:
            declared_signer = payload.get("signer")
            if isinstance(declared_signer, str) and recovered != declared_signer.lower():
                errors.append(
                    error(
                        "signature_signer_mismatch",
                        "Recovered signature address does not match signer.",
                        "signer",
                        recovered=recovered,
                    )
                )

    request_fingerprint = payload.get("approval_request_fingerprint")
    if isinstance(request_fingerprint, str) and FINGERPRINT_RE.fullmatch(request_fingerprint):
        request = {
            "schema_version": APPROVAL_REQUEST_SCHEMA,
            "type": "rule_approval_request",
            "rule_set_fingerprint": payload.get("rule_set_fingerprint"),
            "chain_id": payload.get("chain_id"),
            "verifying_contract": payload.get("verifying_contract"),
            "signer": payload.get("signer"),
            "signature_scheme": payload.get("signature_scheme"),
            "decision": payload.get("decision"),
            "message": payload.get("message"),
        }
        expected_request_fingerprint = artifact_fingerprint(request)
        if request_fingerprint != expected_request_fingerprint:
            errors.append(
                error(
                    "approval_request_fingerprint_mismatch",
                    "approval_request_fingerprint does not match the signed request.",
                    "approval_request_fingerprint",
                    declared=request_fingerprint,
                    computed=expected_request_fingerprint,
                )
            )

    declared = payload.get("fingerprint")
    if isinstance(declared, str) and FINGERPRINT_RE.fullmatch(declared):
        expected = artifact_fingerprint(payload)
        if declared != expected:
            errors.append(
                error(
                    "fingerprint_mismatch",
                    "Rule-approval fingerprint does not match canonical content.",
                    "fingerprint",
                    declared=declared,
                    computed=expected,
                )
            )
    return errors


def finalize_approval_request(request: Mapping[str, Any], signature: str) -> dict[str, Any]:
    """Attach an externally produced signature to a validated request."""

    request_errors = validate_approval_request_payload(dict(request))
    if request_errors:
        raise ValueError(f"invalid approval request: {request_errors[0]['code']}")
    approval: dict[str, Any] = {
        "schema_version": APPROVAL_SCHEMA,
        "type": "rule_approval",
        "approval_request_fingerprint": request["fingerprint"],
        "rule_set_fingerprint": request["rule_set_fingerprint"],
        "chain_id": request["chain_id"],
        "verifying_contract": request["verifying_contract"],
        "signer": request["signer"],
        "signature_scheme": request["signature_scheme"],
        "decision": request["decision"],
        "message": request["message"],
        "signature": signature,
    }
    approval["fingerprint"] = artifact_fingerprint(approval)
    approval_errors = validate_rule_approval_payload(approval)
    if approval_errors:
        raise ValueError(f"invalid approval signature: {approval_errors[0]['code']}")
    return approval


def _leaf_payload(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "rule_set_fingerprint": entry["rule_set_fingerprint"],
        "rule_class": entry["rule_class"],
        "visibility": entry["visibility"],
        "approval_fingerprints": entry["approval_fingerprints"],
    }


def rule_anchor_leaf_hash(entry: Mapping[str, Any]) -> str:
    """Hash one rule-batch entry with explicit leaf domain separation."""

    canonical = canonical_json_dumps(_leaf_payload(entry)).encode("utf-8")
    return sha256_fingerprint_bytes(MERKLE_LEAF_DOMAIN + canonical)


def rule_anchor_parent_hash(left: str, right: str) -> str:
    """Hash two Merkle children with explicit internal-node separation."""

    return sha256_fingerprint_bytes(
        MERKLE_NODE_DOMAIN + fingerprint_bytes(left) + fingerprint_bytes(right)
    )


def _merkle_root_and_proofs(leaf_hashes: Sequence[str]) -> tuple[str, list[list[dict[str, str]]]]:
    if not leaf_hashes:
        raise ValueError("at least one Merkle leaf is required")

    proofs: list[list[dict[str, str]]] = [[] for _ in leaf_hashes]
    level: list[tuple[str, list[int]]] = [
        (leaf_hash, [index]) for index, leaf_hash in enumerate(leaf_hashes)
    ]

    while len(level) > 1:
        next_level: list[tuple[str, list[int]]] = []
        for index in range(0, len(level), 2):
            left_hash, left_indices = level[index]
            if index + 1 < len(level):
                right_hash, right_indices = level[index + 1]
                for leaf_index in left_indices:
                    proofs[leaf_index].append({"position": "right", "hash": right_hash})
                for leaf_index in right_indices:
                    proofs[leaf_index].append({"position": "left", "hash": left_hash})
                combined_indices = left_indices + right_indices
            else:
                right_hash = left_hash
                for leaf_index in left_indices:
                    proofs[leaf_index].append({"position": "right", "hash": right_hash})
                combined_indices = left_indices
            next_level.append(
                (rule_anchor_parent_hash(left_hash, right_hash), combined_indices)
            )
        level = next_level

    return level[0][0], proofs


def verify_rule_anchor_proof(entry: Mapping[str, Any], merkle_root: str) -> bool:
    """Verify one manifest entry against its declared Merkle root."""

    current = rule_anchor_leaf_hash(entry)
    if current != entry.get("leaf_hash"):
        return False
    proof = entry.get("proof")
    if not isinstance(proof, list):
        return False
    for node in proof:
        if not isinstance(node, dict):
            return False
        sibling = node.get("hash")
        position = node.get("position")
        if not isinstance(sibling, str) or not FINGERPRINT_RE.fullmatch(sibling):
            return False
        if position == "left":
            current = rule_anchor_parent_hash(sibling, current)
        elif position == "right":
            current = rule_anchor_parent_hash(current, sibling)
        else:
            return False
    return current == merkle_root


def build_rule_anchor_batch(
    rule_sets: Sequence[Mapping[str, Any]],
    approvals: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic Merkle batch after validating approvals."""

    if not rule_sets:
        raise ValueError("at least one frozen rule set is required")

    indexed_rules: dict[str, Mapping[str, Any]] = {}
    for rule_set in rule_sets:
        validation_errors = validate_frozen_rule_set_payload(dict(rule_set))
        if validation_errors:
            raise ValueError(f"invalid frozen rule set: {validation_errors[0]['code']}")
        fingerprint = str(rule_set["fingerprint"])
        if fingerprint in indexed_rules:
            raise ValueError("duplicate frozen rule-set fingerprint")
        indexed_rules[fingerprint] = rule_set

    indexed_approvals: dict[str, list[Mapping[str, Any]]] = {}
    seen_approval_fingerprints: set[str] = set()
    for approval in approvals:
        validation_errors = validate_rule_approval_payload(dict(approval))
        if validation_errors:
            raise ValueError(f"invalid rule approval: {validation_errors[0]['code']}")
        approval_fingerprint = str(approval["fingerprint"])
        if approval_fingerprint in seen_approval_fingerprints:
            raise ValueError("duplicate rule-approval fingerprint")
        seen_approval_fingerprints.add(approval_fingerprint)
        rule_fingerprint = str(approval["rule_set_fingerprint"])
        if rule_fingerprint not in indexed_rules:
            raise ValueError("approval references a rule set outside this batch")
        indexed_approvals.setdefault(rule_fingerprint, []).append(approval)

    entries: list[dict[str, Any]] = []
    chain_contract_pairs: set[tuple[int, str]] = set()
    for rule_fingerprint in sorted(indexed_rules):
        rule_set = indexed_rules[rule_fingerprint]
        governance = rule_set["governance"]
        authorized = {
            str(address).lower() for address in governance["authorized_signers"]
        }
        rule_approvals = indexed_approvals.get(rule_fingerprint, [])
        unique_approved_signers: set[str] = set()
        for approval in rule_approvals:
            signer = str(approval["signer"]).lower()
            if signer not in authorized:
                raise ValueError("approval signer is not authorized by the frozen rule set")
            if signer in unique_approved_signers:
                raise ValueError("multiple approvals from the same signer are not allowed")
            unique_approved_signers.add(signer)
            chain_contract_pairs.add(
                (int(approval["chain_id"]), str(approval["verifying_contract"]).lower())
            )
        if len(unique_approved_signers) < int(governance["approval_threshold"]):
            raise ValueError("frozen rule set does not meet its approval threshold")

        entry = {
            "rule_set_fingerprint": rule_fingerprint,
            "rule_class": rule_set["rule_class"],
            "visibility": rule_set["visibility"],
            "approval_fingerprints": sorted(
                str(approval["fingerprint"]) for approval in rule_approvals
            ),
        }
        entry["leaf_hash"] = rule_anchor_leaf_hash(entry)
        entries.append(entry)

    if len(chain_contract_pairs) != 1:
        raise ValueError("all approvals in a batch must bind to one chain and contract")
    chain_id, verifying_contract = next(iter(chain_contract_pairs))

    merkle_root, proofs = _merkle_root_and_proofs(
        [str(entry["leaf_hash"]) for entry in entries]
    )
    for entry, proof in zip(entries, proofs, strict=True):
        entry["proof"] = proof

    visibility_mask = 0
    if any(entry["visibility"] == "public" for entry in entries):
        visibility_mask |= 1
    if any(entry["visibility"] == "private_commitment" for entry in entries):
        visibility_mask |= 2

    batch: dict[str, Any] = {
        "schema_version": ANCHOR_BATCH_SCHEMA,
        "type": "rule_anchor_batch",
        "batch_id": f"rule-anchor-batch:{merkle_root[7:31]}",
        "hash_algorithm": "sha256",
        "merkle_scheme": "core.sha256_merkle.v1",
        "chain_id": chain_id,
        "verifying_contract": verifying_contract,
        "rule_set_count": len(entries),
        "visibility_mask": visibility_mask,
        "entries": entries,
        "merkle_root": merkle_root,
    }
    batch["manifest_fingerprint"] = artifact_fingerprint(batch, "manifest_fingerprint")
    return batch


def validate_rule_anchor_batch_payload(payload: Any) -> list[dict[str, Any]]:
    """Validate a batch manifest, every leaf, and every Merkle proof."""

    errors = _schema_errors(payload, "rule_anchor_batch.v1.json")
    if not isinstance(payload, dict):
        return errors

    entries = payload.get("entries")
    root = payload.get("merkle_root")
    if isinstance(entries, list):
        fingerprints = [
            entry.get("rule_set_fingerprint")
            for entry in entries
            if isinstance(entry, dict)
        ]
        if len(fingerprints) != len(set(fingerprints)):
            errors.append(
                error(
                    "duplicate_rule_set_fingerprint",
                    "Batch entries must reference unique rule sets.",
                    "entries",
                )
            )
        if fingerprints != sorted(fingerprints):
            errors.append(
                error(
                    "noncanonical_entry_order",
                    "Batch entries must be sorted by rule_set_fingerprint.",
                    "entries",
                )
            )
        if payload.get("rule_set_count") != len(entries):
            errors.append(
                error(
                    "rule_set_count_mismatch",
                    "rule_set_count must equal the number of entries.",
                    "rule_set_count",
                )
            )

        expected_mask = 0
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            approval_fingerprints = entry.get("approval_fingerprints")
            if isinstance(approval_fingerprints, list):
                if approval_fingerprints != sorted(approval_fingerprints):
                    errors.append(
                        error(
                            "noncanonical_approval_order",
                            "approval_fingerprints must be sorted.",
                            f"entries.{index}.approval_fingerprints",
                        )
                    )
                if len(approval_fingerprints) != len(set(approval_fingerprints)):
                    errors.append(
                        error(
                            "duplicate_approval_fingerprint",
                            "approval_fingerprints must be unique per entry.",
                            f"entries.{index}.approval_fingerprints",
                        )
                    )
            if entry.get("visibility") == "public":
                expected_mask |= 1
            if entry.get("visibility") == "private_commitment":
                expected_mask |= 2
            if isinstance(root, str) and FINGERPRINT_RE.fullmatch(root):
                try:
                    proof_valid = verify_rule_anchor_proof(entry, root)
                except (KeyError, TypeError, ValueError):
                    proof_valid = False
                if not proof_valid:
                    errors.append(
                        error(
                            "invalid_merkle_proof",
                            "Entry leaf or proof does not resolve to merkle_root.",
                            f"entries.{index}.proof",
                        )
                    )
        if payload.get("visibility_mask") != expected_mask:
            errors.append(
                error(
                    "visibility_mask_mismatch",
                    "visibility_mask does not match batch entry visibility.",
                    "visibility_mask",
                )
            )

    if isinstance(root, str) and FINGERPRINT_RE.fullmatch(root):
        expected_batch_id = f"rule-anchor-batch:{root[7:31]}"
        if payload.get("batch_id") != expected_batch_id:
            errors.append(
                error(
                    "batch_id_mismatch",
                    "batch_id must be derived from the Merkle root.",
                    "batch_id",
                )
            )

    declared = payload.get("manifest_fingerprint")
    if isinstance(declared, str) and FINGERPRINT_RE.fullmatch(declared):
        expected = artifact_fingerprint(payload, "manifest_fingerprint")
        if declared != expected:
            errors.append(
                error(
                    "manifest_fingerprint_mismatch",
                    "Batch manifest fingerprint does not match canonical content.",
                    "manifest_fingerprint",
                    declared=declared,
                    computed=expected,
                )
            )
    return errors


def encode_anchor_rule_batch_calldata(batch: Mapping[str, Any]) -> str:
    """ABI-encode ``anchorRuleBatch`` without requiring a wallet library."""

    errors = validate_rule_anchor_batch_payload(dict(batch))
    if errors:
        raise ValueError(f"invalid rule anchor batch: {errors[0]['code']}")

    count = int(batch["rule_set_count"])
    mask = int(batch["visibility_mask"])
    if count > (2**32 - 1):
        raise ValueError("rule_set_count exceeds uint32")
    if mask > 255:
        raise ValueError("visibility_mask exceeds uint8")
    encoded = "".join(
        (
            ANCHOR_RULE_BATCH_SELECTOR,
            fingerprint_bytes(str(batch["merkle_root"])).hex(),
            fingerprint_bytes(str(batch["manifest_fingerprint"])).hex(),
            count.to_bytes(32, "big").hex(),
            mask.to_bytes(32, "big").hex(),
        )
    )
    return "0x" + encoded


def build_unsigned_rule_anchor_request(
    batch: Mapping[str, Any],
    submitter: str,
    *,
    nonce: int | None = None,
    gas_limit: int | None = None,
    max_fee_per_gas_wei: int | None = None,
    max_priority_fee_per_gas_wei: int | None = None,
    gas_price_wei: int | None = None,
    reserve_batches: int = 4,
    safety_multiplier_bps: int = 12_500,
    observed_balance_wei: int | None = None,
    contract_code_verified: bool | None = None,
) -> dict[str, Any]:
    """Build an unsigned transaction and native-gas reserve calculation."""

    if not ADDRESS_RE.fullmatch(submitter):
        raise ValueError("submitter must be an EVM address")
    if reserve_batches < 1:
        raise ValueError("reserve_batches must be at least 1")
    if safety_multiplier_bps < 10_000:
        raise ValueError("safety_multiplier_bps cannot be below 10000")
    if gas_price_wei is not None and max_fee_per_gas_wei is not None:
        raise ValueError("legacy gas_price_wei and EIP-1559 max fee are mutually exclusive")

    errors = validate_rule_anchor_batch_payload(dict(batch))
    if errors:
        raise ValueError(f"invalid rule anchor batch: {errors[0]['code']}")

    fee_per_gas = max_fee_per_gas_wei if max_fee_per_gas_wei is not None else gas_price_wei
    per_batch_max_cost: int | None = None
    required_balance: int | None = None
    shortfall: int | None = None
    sufficient: bool | None = None
    max_cost_per_rule: int | None = None
    if gas_limit is not None and fee_per_gas is not None:
        raw_batch_cost = gas_limit * fee_per_gas
        per_batch_max_cost = (raw_batch_cost * safety_multiplier_bps + 9_999) // 10_000
        required_balance = per_batch_max_cost * reserve_batches
        count = int(batch["rule_set_count"])
        max_cost_per_rule = (per_batch_max_cost + count - 1) // count
        if observed_balance_wei is not None:
            sufficient = observed_balance_wei >= required_balance
            shortfall = max(0, required_balance - observed_balance_wei)

    if sufficient is False:
        readiness = "insufficient_balance"
    elif contract_code_verified is not True:
        readiness = "contract_unverified"
    elif sufficient is True:
        readiness = "ready"
    elif gas_limit is None or fee_per_gas is None:
        readiness = "offline_unpriced"
    else:
        readiness = "balance_unobserved"

    request: dict[str, Any] = {
        "schema_version": UNSIGNED_TRANSACTION_SCHEMA,
        "type": "unsigned_rule_anchor_transaction",
        "signing_mode": "external_wallet_only",
        "broadcast": False,
        "batch_manifest_fingerprint": batch["manifest_fingerprint"],
        "rule_set_count": batch["rule_set_count"],
        "transaction": {
            "from": submitter.lower(),
            "to": str(batch["verifying_contract"]).lower(),
            "chain_id": batch["chain_id"],
            "value_wei": 0,
            "data": encode_anchor_rule_batch_calldata(batch),
            "nonce": nonce,
            "gas_limit": gas_limit,
            "max_fee_per_gas_wei": max_fee_per_gas_wei,
            "max_priority_fee_per_gas_wei": max_priority_fee_per_gas_wei,
            "gas_price_wei": gas_price_wei,
        },
        "gas_reserve": {
            "unit": "native_wei",
            "reserve_batches": reserve_batches,
            "safety_multiplier_bps": safety_multiplier_bps,
            "per_batch_max_cost_wei": per_batch_max_cost,
            "max_cost_per_rule_wei": max_cost_per_rule,
            "required_balance_wei": required_balance,
            "observed_balance_wei": observed_balance_wei,
            "shortfall_wei": shortfall,
            "sufficient": sufficient,
        },
        "contract_code_verified": contract_code_verified,
        "readiness": readiness,
        "warnings": [
            "This artifact is unsigned and must be reviewed and signed by an external wallet.",
            "CORE never requests, receives, stores, or transmits wallet secrets.",
            "Gas reserve is advisory and denominated only in the network native asset.",
        ],
    }
    request["fingerprint"] = artifact_fingerprint(request)
    schema_errors = _schema_errors(request, "unsigned_rule_anchor_transaction.v1.json")
    if schema_errors:
        raise ValueError(f"unsigned transaction schema error: {schema_errors[0]['message']}")
    return request


def validate_unsigned_rule_anchor_request_payload(payload: Any) -> list[dict[str, Any]]:
    """Validate an unsigned transaction and recompute every derived value."""

    errors = _schema_errors(payload, "unsigned_rule_anchor_transaction.v1.json")
    if not isinstance(payload, dict):
        return errors

    transaction = payload.get("transaction")
    reserve = payload.get("gas_reserve")
    if not isinstance(transaction, dict) or not isinstance(reserve, dict):
        return errors

    errors.extend(_wallet_secret_errors(payload, "Unsigned transaction"))

    max_fee = transaction.get("max_fee_per_gas_wei")
    priority_fee = transaction.get("max_priority_fee_per_gas_wei")
    gas_price = transaction.get("gas_price_wei")
    if max_fee is not None and gas_price is not None:
        errors.append(
            error(
                "mutually_exclusive_fee_modes",
                "EIP-1559 max fee and legacy gas price cannot both be set.",
                "transaction",
            )
        )
    if (
        isinstance(max_fee, int)
        and not isinstance(max_fee, bool)
        and isinstance(priority_fee, int)
        and not isinstance(priority_fee, bool)
        and priority_fee > max_fee
    ):
        errors.append(
            error(
                "priority_fee_exceeds_max_fee",
                "max_priority_fee_per_gas_wei cannot exceed max_fee_per_gas_wei.",
                "transaction.max_priority_fee_per_gas_wei",
            )
        )

    data = transaction.get("data")
    manifest = payload.get("batch_manifest_fingerprint")
    rule_count = payload.get("rule_set_count")
    if isinstance(data, str) and re.fullmatch(r"0x[a-f0-9]{264}", data):
        selector = data[2:10]
        encoded_manifest = data[74:138]
        encoded_count = int(data[138:202], 16)
        if selector != ANCHOR_RULE_BATCH_SELECTOR:
            errors.append(
                error(
                    "calldata_selector_mismatch",
                    "Transaction data does not call anchorRuleBatch.",
                    "transaction.data",
                )
            )
        if isinstance(manifest, str) and encoded_manifest != manifest.removeprefix("sha256:"):
            errors.append(
                error(
                    "calldata_manifest_mismatch",
                    "Calldata manifest hash does not match batch_manifest_fingerprint.",
                    "transaction.data",
                )
            )
        if isinstance(rule_count, int) and not isinstance(rule_count, bool) and encoded_count != rule_count:
            errors.append(
                error(
                    "calldata_rule_count_mismatch",
                    "Calldata rule count does not match rule_set_count.",
                    "transaction.data",
                )
            )

    gas_limit = transaction.get("gas_limit")
    fee_per_gas = max_fee if max_fee is not None else gas_price
    reserve_batches = reserve.get("reserve_batches")
    multiplier = reserve.get("safety_multiplier_bps")
    observed_balance = reserve.get("observed_balance_wei")
    expected_per_batch: int | None = None
    expected_per_rule: int | None = None
    expected_required: int | None = None
    expected_shortfall: int | None = None
    expected_sufficient: bool | None = None
    if all(
        isinstance(value, int) and not isinstance(value, bool)
        for value in (gas_limit, fee_per_gas, reserve_batches, multiplier, rule_count)
    ):
        raw_batch_cost = gas_limit * fee_per_gas
        expected_per_batch = (raw_batch_cost * multiplier + 9_999) // 10_000
        expected_per_rule = (expected_per_batch + rule_count - 1) // rule_count
        expected_required = expected_per_batch * reserve_batches
        if isinstance(observed_balance, int) and not isinstance(observed_balance, bool):
            expected_sufficient = observed_balance >= expected_required
            expected_shortfall = max(0, expected_required - observed_balance)

    derived = {
        "per_batch_max_cost_wei": expected_per_batch,
        "max_cost_per_rule_wei": expected_per_rule,
        "required_balance_wei": expected_required,
        "shortfall_wei": expected_shortfall,
        "sufficient": expected_sufficient,
    }
    for key, expected in derived.items():
        if reserve.get(key) != expected:
            errors.append(
                error(
                    "gas_reserve_mismatch",
                    f"{key} does not match deterministic gas-reserve calculation.",
                    f"gas_reserve.{key}",
                    declared=reserve.get(key),
                    computed=expected,
                )
            )

    if expected_sufficient is False:
        expected_readiness = "insufficient_balance"
    elif payload.get("contract_code_verified") is not True:
        expected_readiness = "contract_unverified"
    elif expected_sufficient is True:
        expected_readiness = "ready"
    elif gas_limit is None or fee_per_gas is None:
        expected_readiness = "offline_unpriced"
    else:
        expected_readiness = "balance_unobserved"
    if payload.get("readiness") != expected_readiness:
        errors.append(
            error(
                "readiness_mismatch",
                "readiness does not match verified contract code, price, and reserve evidence.",
                "readiness",
                declared=payload.get("readiness"),
                computed=expected_readiness,
            )
        )

    declared_fingerprint = payload.get("fingerprint")
    if isinstance(declared_fingerprint, str) and FINGERPRINT_RE.fullmatch(declared_fingerprint):
        computed_fingerprint = artifact_fingerprint(payload)
        if declared_fingerprint != computed_fingerprint:
            errors.append(
                error(
                    "fingerprint_mismatch",
                    "Unsigned transaction fingerprint does not match canonical content.",
                    "fingerprint",
                    declared=declared_fingerprint,
                    computed=computed_fingerprint,
                )
            )
    return errors


def validate_unsigned_rule_anchor_deployment_payload(payload: Any) -> list[dict[str, Any]]:
    """Validate an unsigned deployment and recompute all locally provable fields."""

    errors = _schema_errors(payload, "unsigned_rule_anchor_deployment.v1.json")
    if not isinstance(payload, dict):
        return errors

    errors.extend(_wallet_secret_errors(payload, "Unsigned deployment"))
    transaction = payload.get("transaction")
    reserve = payload.get("gas_reserve")
    if not isinstance(transaction, dict) or not isinstance(reserve, dict):
        return errors

    deployer = transaction.get("from")
    if isinstance(deployer, str) and ADDRESS_RE.fullmatch(deployer) and deployer != deployer.lower():
        errors.append(
            error(
                "noncanonical_deployer_address",
                "transaction.from must use canonical lowercase hexadecimal.",
                "transaction.from",
            )
        )

    try:
        build, creation_hex = load_verified_rule_anchor_build()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(
            error(
                "frozen_contract_build_unverified",
                "Frozen CoreRuleAnchor build artifacts could not be verified.",
                "contract_build_fingerprint",
                reason=exc.__class__.__name__,
            )
        )
    else:
        expected_build_fingerprint = canonical_fingerprint(build)
        if payload.get("contract_build_fingerprint") != expected_build_fingerprint:
            errors.append(
                error(
                    "contract_build_fingerprint_mismatch",
                    "contract_build_fingerprint does not identify the verified frozen build.",
                    "contract_build_fingerprint",
                    declared=payload.get("contract_build_fingerprint"),
                    computed=expected_build_fingerprint,
                )
            )
        expected_runtime = build.get("runtime_bytecode_sha256")
        if payload.get("expected_runtime_bytecode_sha256") != expected_runtime:
            errors.append(
                error(
                    "runtime_bytecode_fingerprint_mismatch",
                    "Expected runtime bytecode does not match the verified frozen build.",
                    "expected_runtime_bytecode_sha256",
                    declared=payload.get("expected_runtime_bytecode_sha256"),
                    computed=expected_runtime,
                )
            )
        if transaction.get("data") != "0x" + creation_hex:
            errors.append(
                error(
                    "deployment_bytecode_mismatch",
                    "transaction.data does not contain the verified creation bytecode.",
                    "transaction.data",
                )
            )

    max_fee = transaction.get("max_fee_per_gas_wei")
    priority_fee = transaction.get("max_priority_fee_per_gas_wei")
    gas_price = transaction.get("gas_price_wei")
    if max_fee is not None and gas_price is not None:
        errors.append(
            error(
                "mutually_exclusive_fee_modes",
                "EIP-1559 max fee and legacy gas price cannot both be set.",
                "transaction",
            )
        )
    if priority_fee is not None and max_fee is None:
        errors.append(
            error(
                "priority_fee_without_max_fee",
                "max_priority_fee_per_gas_wei requires max_fee_per_gas_wei.",
                "transaction.max_priority_fee_per_gas_wei",
            )
        )
    if (
        isinstance(max_fee, int)
        and not isinstance(max_fee, bool)
        and isinstance(priority_fee, int)
        and not isinstance(priority_fee, bool)
        and priority_fee > max_fee
    ):
        errors.append(
            error(
                "priority_fee_exceeds_max_fee",
                "max_priority_fee_per_gas_wei cannot exceed max_fee_per_gas_wei.",
                "transaction.max_priority_fee_per_gas_wei",
            )
        )

    gas_limit = transaction.get("gas_limit")
    fee_per_gas = max_fee if max_fee is not None else gas_price
    post_reserve = reserve.get("post_deployment_reserve_wei")
    observed_balance = reserve.get("observed_balance_wei")
    expected_cost: int | None = None
    expected_required: int | None = None
    expected_shortfall: int | None = None
    expected_sufficient: bool | None = None
    if all(
        isinstance(value, int) and not isinstance(value, bool)
        for value in (gas_limit, fee_per_gas, post_reserve)
    ):
        expected_cost = gas_limit * fee_per_gas
        expected_required = expected_cost + post_reserve
        if isinstance(observed_balance, int) and not isinstance(observed_balance, bool):
            expected_sufficient = observed_balance >= expected_required
            expected_shortfall = max(0, expected_required - observed_balance)

    derived = {
        "deployment_max_cost_wei": expected_cost,
        "required_balance_wei": expected_required,
        "shortfall_wei": expected_shortfall,
        "sufficient": expected_sufficient,
    }
    for key, expected in derived.items():
        if reserve.get(key) != expected:
            errors.append(
                error(
                    "gas_reserve_mismatch",
                    f"{key} does not match deterministic deployment-reserve calculation.",
                    f"gas_reserve.{key}",
                    declared=reserve.get(key),
                    computed=expected,
                )
            )

    if expected_sufficient is True:
        expected_readiness = "ready"
    elif expected_sufficient is False:
        expected_readiness = "insufficient_balance"
    elif expected_cost is None:
        expected_readiness = "offline_unpriced"
    else:
        expected_readiness = "balance_unobserved"
    if payload.get("readiness") != expected_readiness:
        errors.append(
            error(
                "readiness_mismatch",
                "readiness does not match the recomputed price and balance evidence.",
                "readiness",
                declared=payload.get("readiness"),
                computed=expected_readiness,
            )
        )

    warnings = payload.get("warnings")
    if isinstance(warnings, list):
        missing_warnings = sorted(set(UNSIGNED_DEPLOYMENT_WARNINGS) - set(warnings))
        if missing_warnings:
            errors.append(
                error(
                    "required_safety_warning_missing",
                    "Unsigned deployment omits a required external-wallet safety warning.",
                    "warnings",
                    missing=missing_warnings,
                )
            )

    declared_fingerprint = payload.get("fingerprint")
    if isinstance(declared_fingerprint, str) and FINGERPRINT_RE.fullmatch(declared_fingerprint):
        computed_fingerprint = artifact_fingerprint(payload)
        if declared_fingerprint != computed_fingerprint:
            errors.append(
                error(
                    "fingerprint_mismatch",
                    "Unsigned deployment fingerprint does not match canonical content.",
                    "fingerprint",
                    declared=declared_fingerprint,
                    computed=computed_fingerprint,
                )
            )
    return errors


def validate_rule_anchor_chain_evidence_payload(payload: Any) -> list[dict[str, Any]]:
    """Validate persisted evidence from read-only on-chain verification."""

    errors = _schema_errors(payload, "rule_anchor_chain_evidence.v1.json")
    if not isinstance(payload, dict):
        return errors
    confirmations = payload.get("confirmations")
    required = payload.get("required_confirmations")
    if (
        isinstance(confirmations, int)
        and not isinstance(confirmations, bool)
        and isinstance(required, int)
        and not isinstance(required, bool)
        and confirmations < required
    ):
        errors.append(
            error(
                "insufficient_confirmations",
                "Persisted chain evidence must meet required_confirmations.",
                "confirmations",
            )
        )
    declared = payload.get("fingerprint")
    if isinstance(declared, str) and FINGERPRINT_RE.fullmatch(declared):
        expected = artifact_fingerprint(payload)
        if declared != expected:
            errors.append(
                error(
                    "fingerprint_mismatch",
                    "Chain-evidence fingerprint does not match canonical content.",
                    "fingerprint",
                    declared=declared,
                    computed=expected,
                )
            )
    return errors
