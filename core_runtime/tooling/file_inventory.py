"""File inventory - check presence of required files."""

from __future__ import annotations

from pathlib import Path

from core_runtime.tooling.diagnostics import DiagnosticCollection


# Required files for CORE tooling
REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    "pyproject.toml",
    "CHANGELOG.md",
    "core_runtime/__version__.py",
    "core_runtime/__init__.py",
    "docs/VERSIONING_POLICY.md",
    "docs/CORE_RELEASE_README.md",
    "docs/REPRODUCIBILITY.md",
    "docs/QUALITY_GATE.md",
    "docs/releases/README.md",
    "scripts/verify_release.py",
    "scripts/check_version_consistency.py",
    "scripts/bump_version.py",
    "scripts/generate_requirements_lock.py",
    "contracts/CoreRuleAnchor.abi.json",
    "contracts/CoreRuleAnchor.bin",
    "contracts/CoreRuleAnchor.build.json",
    "contracts/CoreRuleAnchor.runtime.bin",
    "contracts/CoreRuleAnchor.sol",
    "core_runtime/core/contract_evaluator.py",
    "core_runtime/core/contract_executability.py",
    "core_runtime/core/rule_anchor.py",
    "schemas/core/frozen_release_manifest.v1.json",
    "schemas/core/frozen_release_manifest.v2.json",
    "schemas/core/frozen_release_manifest.v3.json",
    "schemas/core/dsk.v3.json",
    "schemas/core/frozen_release_manifest.v7.json",
    "schemas/core/frozen_release_manifest.v8.json",
    "schemas/core/frozen_release_manifest.v9.json",
    "schemas/core/frozen_rule_set.v1.json",
    "schemas/core/physical_safety_assurance_case.v1.json",
    "schemas/core/rule_anchor_chain_evidence.v1.json",
    "schemas/core/rule_approval.v1.json",
    "schemas/core/rule_approval_request.v1.json",
    "schemas/core/rule_anchor_batch.v1.json",
    "schemas/core/unsigned_rule_anchor_deployment.v1.json",
    "schemas/core/unsigned_rule_anchor_transaction.v1.json",
    "scripts/audit_contract_executability.py",
    "scripts/build_frozen_release_manifest.py",
    "scripts/build_frozen_release_manifest_v11_2.py",
    "scripts/build_frozen_release_manifest_v11_2_frozen.py",
    "scripts/build_frozen_release_manifest_v11_5.py",
    "scripts/validate_frozen_rule_set.py",
    "scripts/validate_frozen_release_manifest.py",
    "scripts/validate_frozen_release_manifest_v11_2.py",
    "scripts/validate_frozen_release_manifest_v11_2_frozen.py",
    "scripts/validate_dsk_v3.py",
    "scripts/validate_frozen_release_manifest_v11_5.py",
    "scripts/validate_frozen_release_manifest_v11_5_1.py",
    "scripts/build_frozen_release_manifest_v11_5_1.py",
    "scripts/validate_frozen_release_manifest_v11_6.py",
    "scripts/build_frozen_release_manifest_v11_6.py",
    "scripts/pypi_preflight.py",
    "scripts/replay_certification.py",
    "scripts/expert_router_common.py",
    "scripts/validate_expert_router.py",
    "scripts/evaluate_expert_router.py",
    "scripts/report_expert_router.py",
    "scripts/certify_router_replay.py",
    "scripts/validate_rule_approval.py",
    "scripts/validate_rule_anchor_batch.py",
    "scripts/validate_unsigned_rule_anchor_deployment.py",
    "scripts/validate_unsigned_rule_anchor_transaction.py",
    "scripts/build_rule_anchor_batch.py",
    "scripts/compile_core_rule_anchor.py",
    "scripts/create_private_rule_commitment.py",
    "scripts/create_rule_approval_request.py",
    "scripts/evaluate_core_contract.py",
    "scripts/finalize_rule_approval.py",
    "scripts/prepare_core_rule_anchor_deployment.py",
    "scripts/prepare_rule_anchor_transaction.py",
    "scripts/verify_merkle_proof.py",
    "scripts/verify_rule_anchor_onchain.py",
    "docs/EXECUTABLE_CONTRACTS_AND_PHYSICAL_SAFETY.md",
    "docs/FROZEN_RULE_ANCHORING.md",
    "docs/PROJECTION_AND_RESPONSIBLE_AGENCY.md",
    "examples/frozen_release_manifest/accepted_v11_1_0.json",
    "examples/frozen_release_manifest/accepted_v11_2_0_candidate.json",
    "examples/frozen_release_manifest/accepted_v11_2_0.json",
    "examples/frozen_release_manifest/accepted_v11_5_0_candidate.json",
    "examples/frozen_release_manifest/accepted_v11_5_1_candidate.json",
    "examples/frozen_release_manifest/accepted_v11_6_0_candidate.json",
    "examples/expert_router/routing_fixtures/minimal_routing.json",
    "tests/test_frozen_release_manifest.py",
    "tests/test_frozen_release_manifest_v11_5_1.py",
    "tests/test_frozen_release_manifest_v11_6.py",
    "tests/test_pypi_preflight.py",
    "tests/test_replay_certification.py",
    "tests/test_expert_router_scripts.py",
    "tests/test_frozen_release_manifest_v11_2.py",
    "tests/test_frozen_release_manifest_v11_2_frozen.py",
    "requirements.lock",
    "requirements-dev.txt",
]

# Required directories
REQUIRED_DIRS = [
    "schemas",
    "examples",
    "tests",
    ".github/workflows",
]

# Optional files (created by this implementation)
OPTIONAL_FILES = [
    "docs/CORE_TOOLING.md",
]


class FileInventory:
    """Check presence of required files and directories."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def check_file(self, rel_path: str) -> bool:
        """Check if a file exists."""
        return (self.repo_root / rel_path).is_file()

    def check_dir(self, rel_path: str) -> bool:
        """Check if a directory exists."""
        return (self.repo_root / rel_path).is_dir()

    def check_all(self, diagnostics: DiagnosticCollection) -> dict[str, bool]:
        """Check all required files and directories."""
        results = {}

        # Check required files
        for rel_path in REQUIRED_FILES:
            exists = self.check_file(rel_path)
            results[rel_path] = exists
            if not exists:
                diagnostics.add_error(
                    code="core.file.missing",
                    message="Required file missing: {0}".format(rel_path),
                    path=rel_path,
                    expected="exists",
                    actual="missing",
                )

        # Check required directories
        for rel_path in REQUIRED_DIRS:
            exists = self.check_dir(rel_path)
            results[rel_path] = exists
            if not exists:
                diagnostics.add_error(
                    code="core.dir.missing",
                    message="Required directory missing: {0}".format(rel_path),
                    path=rel_path,
                    expected="exists",
                    actual="missing",
                )

        # Check optional files (just report, don't error)
        for rel_path in OPTIONAL_FILES:
            exists = self.check_file(rel_path)
            results[rel_path] = exists
            if not exists:
                diagnostics.add_info(
                    code="core.file.optional_missing",
                    message="Optional file not yet present: {0}".format(rel_path),
                    path=rel_path,
                    expected="optional",
                    actual="missing",
                )

        return results

    def check_release_note_exists(self, version: str, diagnostics: DiagnosticCollection) -> bool:
        """Check if release note for given version exists."""
        rel_path = "docs/releases/v{0}.md".format(version)
        exists = self.check_file(rel_path)
        if not exists:
            diagnostics.add_error(
                code="core.file.release_note_missing",
                message="Release note for v{0} not found".format(version),
                path=rel_path,
                expected="exists",
                actual="missing",
            )
        return exists
