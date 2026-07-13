"""Safety checks - conservative scans for private path leakage and executable proposals."""

from __future__ import annotations

import json
import re
from pathlib import Path

from core_runtime.tooling.diagnostics import DiagnosticCollection


# Known private paths/labs that should not leak into public examples
PRIVATE_PATH_MARKERS = [
    "private_product_name",
    "private_customer_name",
    "/home/real-user/",
    "/home/user/private",
    "private/",
    ".env",
]

# Patterns that indicate rejected fixtures (should be skipped)
REJECTED_PATTERNS = [
    "rejected",
    "REJECTED",
    "malicious",
    "invalid",
    "not_accepted",
]

# Known private adapter IDs
PRIVATE_ADAPTERS = [
    "bridge_private_product",
]

TEMPLATE_LEFTOVER_PATTERNS = (
    re.compile(r"\bTODO\b"),
    re.compile(r"\bFIXME\b"),
    re.compile(r"\bXXX\b"),
    re.compile(r"\bHACK\b"),
    re.compile(r"\bREPLACE_ME\b"),
    re.compile(r"\bTEMPLATE_VALUE\b"),
    re.compile(r"\{\{\s*[^}]+\s*\}\}"),
    re.compile(r"<[A-Z0-9][A-Z0-9_\-]*>"),
    re.compile(r"template placeholder", re.IGNORECASE),
)


class SafetyChecks:
    """Conservative safety scans for public examples."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def check_private_path_leakage(self, diagnostics: DiagnosticCollection) -> None:
        """Scan examples for private path leakage."""
        examples_dir = self.repo_root / "examples"
        if not examples_dir.is_dir():
            return

        checked = 0
        for json_file in examples_dir.rglob("*.json"):
            rel = json_file.relative_to(self.repo_root)

            # Skip rejected fixtures
            if self._is_rejected_fixture(json_file, rel):
                continue

            try:
                text = json_file.read_text(encoding="utf-8")
            except OSError:
                continue

            for marker in PRIVATE_PATH_MARKERS:
                if marker in text:
                    diagnostics.add_warning(
                        code="core.safety.private_path_leak",
                        message="Possible private path leakage: '{0}' found in {1}".format(marker, rel),
                        path=str(rel),
                        details="Marker: {0}".format(marker),
                    )

            checked += 1
            if checked > 200:  # Limit to avoid very long runs
                break

    def _is_rejected_fixture(self, json_file: Path, rel_path: Path) -> bool:
        """Check if a fixture is explicitly rejected."""
        # Check path patterns
        rel_str = str(rel_path)
        for pattern in REJECTED_PATTERNS:
            if pattern.lower() in rel_str.lower():
                return True

        # Check content for REJECTED markers
        try:
            text = json_file.read_text(encoding="utf-8")
            if "REJECTED" in text or "rejected" in text.lower():
                return True
            # Check for adapter_id with private prefix
            data = json.loads(text)
            adapter_id = data.get("adapter_id", "")
            for private in PRIVATE_ADAPTERS:
                if private in adapter_id:
                    return True
        except (json.JSONDecodeError, OSError):
            pass

        return False

    def check_proposal_execution_safety(self, diagnostics: DiagnosticCollection) -> None:
        """Check that command-like proposals are not treated as executable."""
        examples_dir = self.repo_root / "examples"
        if not examples_dir.is_dir():
            return

        # Check agent plans and sessions for executable intent
        for subdir in ["agent_plans", "agent_sessions", "agent_traces"]:
            subdir_path = examples_dir / subdir
            if not subdir_path.is_dir():
                continue

            for json_file in subdir_path.rglob("*.json"):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue

                # Look for intent fields that suggest execution
                intent = data.get("intent", "")
                if isinstance(intent, str):
                    executable_keywords = ["execute", "run", "deploy", "install", "delete", "remove", "modify", "write", "ssh", "curl", "wget"]
                    for keyword in executable_keywords:
                        if keyword in intent.lower():
                            rel = json_file.relative_to(self.repo_root)
                            diagnostics.add_warning(
                                code="core.safety.proposal_executable_intent",
                                message="Agent fixture may contain executable intent: {0}".format(keyword),
                                path=str(rel),
                                details="Intent field: {0}".format(intent[:200]),
                            )
                            break

    def check_todo_templates(self, diagnostics: DiagnosticCollection) -> None:
        """Check for explicit TODO/FIXME/template-placeholder leftovers in key files."""
        # Only check a few key files, not entire codebase
        key_files = [
            "scripts/verify_release.py",
            "scripts/bump_version.py",
            "scripts/check_version_consistency.py",
            "docs/VERSIONING_POLICY.md",
            "docs/QUALITY_GATE.md",
        ]

        for rel_path in key_files:
            full_path = self.repo_root / rel_path
            if not full_path.exists():
                continue

            try:
                text = full_path.read_text(encoding="utf-8")
            except OSError:
                continue

            for pattern in TEMPLATE_LEFTOVER_PATTERNS:
                if pattern.search(text):
                    diagnostics.add_warning(
                        code="core.safety.template_leftover",
                        message="Template marker '{0}' found in {1}".format(pattern.pattern, rel_path),
                        path=rel_path,
                        details="Pattern: {0}".format(pattern.pattern),
                    )
