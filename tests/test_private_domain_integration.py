"""Tests for private-domain integration command candidate validation.

Covers:
  - Structural validation (schema, required fields, output_kind, label)
  - Private data rejection (embedded financial/customer fields)
  - Forbidden effects rejection (write, delete, etc.)
  - Unknown command rejection (command not in vocabulary)
  - External vocabulary resolution (external: prefix)
  - Byte-stable deterministic output
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "validate_private_domain_candidate.py"
VOCAB_DIR = PROJECT_ROOT / "examples" / "private_domain_integration" / "vocabularies"
CANDIDATES_DIR = PROJECT_ROOT / "examples" / "private_domain_integration" / "command_candidates"


def _run(candidate: Path, extra_args: list[str] | None = None) -> tuple[int, dict]:
    cmd = [sys.executable, str(SCRIPT), str(candidate), "--vocab-dir", str(VOCAB_DIR)]
    if extra_args:
        cmd.extend(extra_args)
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    result = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return proc.returncode, result


class TestAcceptedCandidate:
    """Valid command candidate referencing an external vocabulary."""

    def test_verdict_accepted(self):
        code, result = _run(CANDIDATES_DIR / "accepted.json")
        assert result["verdict"] == "accepted"
        assert code == 0

    def test_no_errors(self):
        _, result = _run(CANDIDATES_DIR / "accepted.json")
        assert result["errors"] == []

    def test_no_warnings_when_vocab_resolved(self):
        _, result = _run(CANDIDATES_DIR / "accepted.json")
        # Vocabulary should be resolved, so no unresolved warning
        unresolved = [w for w in result.get("warnings", [])
                      if w["code"] == "external_vocabulary_unresolved"]
        assert unresolved == []

    def test_byte_stable(self):
        """Two runs produce identical output."""
        _, r1 = _run(CANDIDATES_DIR / "accepted.json")
        _, r2 = _run(CANDIDATES_DIR / "accepted.json")
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


class TestRejectedPrivateData:
    """Candidate embedding private business data must be rejected."""

    def test_verdict_rejected(self):
        code, result = _run(CANDIDATES_DIR / "rejected_private_data.json")
        assert result["verdict"] == "rejected"
        assert code == 1

    def test_private_data_errors(self):
        _, result = _run(CANDIDATES_DIR / "rejected_private_data.json")
        private_errors = [e for e in result["errors"]
                          if e["code"] == "private_business_data_embedded"]
        assert len(private_errors) >= 1

    def test_margin_data_field_detected(self):
        _, result = _run(CANDIDATES_DIR / "rejected_private_data.json")
        fields = {e.get("field") for e in result["errors"]
                  if e["code"] == "private_business_data_embedded"}
        assert "margin_data" in fields

    def test_byte_stable(self):
        _, r1 = _run(CANDIDATES_DIR / "rejected_private_data.json")
        _, r2 = _run(CANDIDATES_DIR / "rejected_private_data.json")
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


class TestRejectedUnknownCommand:
    """Candidate referencing an unknown command must be rejected."""

    def test_verdict_rejected(self):
        code, result = _run(CANDIDATES_DIR / "rejected_unknown_command.json")
        assert result["verdict"] == "rejected"
        assert code == 1

    def test_unknown_command_error(self):
        _, result = _run(CANDIDATES_DIR / "rejected_unknown_command.json")
        unknown_errors = [e for e in result["errors"]
                          if e["code"] == "unknown_command"]
        assert len(unknown_errors) == 1
        assert unknown_errors[0]["command"] == "delete_all_records"

    def test_forbidden_effects_error(self):
        _, result = _run(CANDIDATES_DIR / "rejected_unknown_command.json")
        effect_errors = [e for e in result["errors"]
                         if e["code"] == "forbidden_effects"]
        assert len(effect_errors) == 1
        assert "delete" in effect_errors[0]["effects"]
        assert "write" in effect_errors[0]["effects"]

    def test_known_commands_listed(self):
        _, result = _run(CANDIDATES_DIR / "rejected_unknown_command.json")
        unknown_errors = [e for e in result["errors"]
                          if e["code"] == "unknown_command"]
        assert "sales_summary" in unknown_errors[0]["known_commands"]
        assert "sales_trend" in unknown_errors[0]["known_commands"]


class TestStructuralValidation:
    """Structural checks on malformed candidates."""

    def test_missing_schema(self, tmp_path: Path):
        candidate = tmp_path / "no_schema.json"
        candidate.write_text(json.dumps({
            "vocabulary_id": "external:foo.commands.v1",
            "domain_id": "foo",
            "command": "bar",
            "output_kind": "command_candidate",
            "label": "accepted_candidate",
        }))
        code, result = _run(candidate)
        assert result["verdict"] == "rejected"
        schema_errors = [e for e in result["errors"] if e["code"] == "invalid_schema"]
        assert len(schema_errors) == 1

    def test_missing_required_field(self, tmp_path: Path):
        candidate = tmp_path / "no_command.json"
        candidate.write_text(json.dumps({
            "schema": "core.command_candidate.v1",
            "vocabulary_id": "external:foo.commands.v1",
            "domain_id": "foo",
            "output_kind": "command_candidate",
            "label": "accepted_candidate",
        }))
        code, result = _run(candidate)
        assert result["verdict"] == "rejected"
        field_errors = [e for e in result["errors"]
                        if e["code"] == "missing_required_field"]
        assert any(e["field"] == "command" for e in field_errors)

    def test_invalid_output_kind(self, tmp_path: Path):
        candidate = tmp_path / "bad_kind.json"
        candidate.write_text(json.dumps({
            "schema": "core.command_candidate.v1",
            "vocabulary_id": "external:foo.commands.v1",
            "domain_id": "foo",
            "command": "bar",
            "output_kind": "arbitrary_execution",
            "label": "accepted_candidate",
        }))
        code, result = _run(candidate)
        kind_errors = [e for e in result["errors"] if e["code"] == "invalid_output_kind"]
        assert len(kind_errors) == 1


class TestExternalVocabularyPrefix:
    """Tests for the external: vocabulary prefix convention."""

    def test_external_prefix_accepted_in_structure(self, tmp_path: Path):
        candidate = tmp_path / "ext_vocab.json"
        candidate.write_text(json.dumps({
            "schema": "core.command_candidate.v1",
            "vocabulary_id": "external:custom_domain.commands.v1",
            "domain_id": "custom_domain",
            "command": "custom_cmd",
            "output_kind": "command_candidate",
            "label": "accepted_candidate",
            "effects": ["read_only"],
        }))
        # No vocab dir provided -> unresolved warning but no structural error
        code, result = _run(candidate, extra_args=[])
        # structural errors should not include vocabulary_id
        vocab_errors = [e for e in result["errors"]
                        if "vocabulary_id" in e.get("field", "")]
        assert vocab_errors == []

    def test_unresolved_external_vocab_warns(self, tmp_path: Path):
        candidate = tmp_path / "ext_unresolved.json"
        candidate.write_text(json.dumps({
            "schema": "core.command_candidate.v1",
            "vocabulary_id": "external:nonexistent.commands.v1",
            "domain_id": "nonexistent",
            "command": "ghost",
            "output_kind": "command_candidate",
            "label": "accepted_candidate",
            "effects": ["read_only"],
        }))
        # Provide an empty vocab dir
        empty_dir = tmp_path / "vocabs"
        empty_dir.mkdir()
        code, result = _run(candidate, extra_args=["--vocab-dir", str(empty_dir)])
        unresolved = [w for w in result.get("warnings", [])
                      if w["code"] == "external_vocabulary_unresolved"]
        assert len(unresolved) == 1


class TestLeakCheck:
    """Verify no private downstream names appear in fixtures."""

    FORBIDDEN = ["private_product_name", "private_customer_name", "/home/real-user", "secret_domain"]

    def test_no_private_names_in_fixtures(self):
        for path in VOCAB_DIR.rglob("*.json"):
            content = path.read_text().lower()
            for forbidden in self.FORBIDDEN:
                assert forbidden not in content, f"Leak in {path}: '{forbidden}'"

    def test_no_private_names_in_candidates(self):
        for path in CANDIDATES_DIR.rglob("*.json"):
            content = path.read_text().lower()
            for forbidden in self.FORBIDDEN:
                assert forbidden not in content, f"Leak in {path}: '{forbidden}'"

    def test_no_private_names_in_script(self):
        content = SCRIPT.read_text().lower()
        for forbidden in self.FORBIDDEN:
            assert forbidden not in content, f"Leak in script: '{forbidden}'"
