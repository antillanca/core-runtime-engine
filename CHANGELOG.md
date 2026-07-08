# Changelog

## Unreleased

## v11.0.1

### Changed
- Hygiene release: genericized example fixtures, test fixtures, tooling
  literals, and documentation references; hardened
  `scripts/read_bounded_reference.py`; rewrote `scripts/verify_release.py`.
- v11.0.0 was withdrawn and superseded by v11.0.1. Use v11.0.1 for all
  new installs.

## v11.0.0

### Changed
- Clean rebuild by whitelist: CORE repositioned as a deterministic
  contract/schema/validator engine only. See
  `docs/CORE_REBUILD_FROM_ZERO.md` and `docs/releases/v11.0.0.md`.

### Removed
- CPT simulator legacy runtime (physics surrogate, DPO datasets,
  curriculum, world model) and the protocol-model/expert-router/GAIA
  certification apparatus, archived at the `legacy-final` tag.

## v10.5.1

### Added
- Final native runtime slice for public CORE v10 line
- Surrogate node descriptors and link-rule enforcement
- Workflow DAG validation
- Release-gate alignment for deterministic public runtime
- Public documentation and release index updates (`docs/releases/v10.5.0.md`)

### Changed
- Aligned Python package version (pyproject.toml) with CORE v10.5.0
- Aligned core_runtime.__version__ with CORE v10.5.0
- Unified versioning across documentation, package metadata, and runtime

### Design Constraints
- Deterministic execution remains mandatory
- Public release notes do not grant runtime authority
- Release gates fail closed
- Historical v9.x notes remain preserved under `docs/releases/`

## v9.2.0

### Added
- Added Multi-Chain Adapter Boundary (`schemas/chain_adapter.schema.json` with 20 rejection codes).
- Added `scripts/validate_chain_adapter.py` — deterministic, fingerprint-verified adapter validation.
- Added 8 chain adapter fixtures (4 valid, 4 rejected) in `examples/anchoring/chain_adapters/`.
- Added 37 tests in `tests/test_chain_adapter_validator.py` covering all rejection codes.
- Integrated V92_CHECKS (8 checks) into `scripts/verify_release.py` with target exclusions for v9.0/v9.1.
- Added `docs/V92_ROADMAP_SEED.md`, `docs/V92_READINESS_REVIEW.md`, `docs/releases/v9.2.0.md`.

## v9.1.0

### Added
- Added Deterministic Event Verifier (`schemas/anchoring_event.schema.json` with 22 rejection codes).
- Added `scripts/validate_anchoring_event.py` for standalone EIP-55 checksummed event validation.
- Added unified CLI `scripts/core_anchor.py` supporting `submit` and `verify` commands.
- Added synthetic fixtures and 65 tests in `tests/test_anchoring_event_validator.py`.
- Fixed `relative_to` path resolution crashes in `scripts/submit_anchoring.py`.

## v9.0.0

### Added
- Added Blockchain Anchoring (`schemas/anchoring_submission.schema.json` with 14 rejection codes).
- Added `scripts/validate_anchoring_submission.py` fail-closed off-chain eligibility validator.
- Added EVM minimal notarization contract `contracts/CoreAnchor.sol` (`notarizeHash` and `HashAnchored`).
- Added `scripts/submit_anchoring.py` for off-chain dry-run and web3-based broadcasts.
- Added 36 tests and 5 new anchoring release checks to `scripts/verify_release.py`.

## v8.5.0

### Added
- Stable Agent Boundary Freeze (`schemas/agent_boundary_freeze.schema.json`, `scripts/validate_agent_boundary_freeze.py`).
- Added freeze artifact `examples/freeze/freeze_v8x.json` sealing 32 schemas, 31 validators, and 239 fixtures.
- Added 19 deterministic tests in `tests/test_agent_boundary_freeze_validator.py`.

## v8.4.0

### Added
- Downstream Bridge Compliance contract (`schemas/downstream_bridge_adapter.schema.json`, `scripts/validate_downstream_bridge_adapter.py`).
- Added 2 accepted and 5 rejected fixtures under `examples/bridge_adapters/`.
- Added 26 tests in `tests/test_downstream_bridge_adapter_validator.py`.

## v8.3.0

### Added
- Replayable Agent Trace contract (`schemas/agent_decision_trace.schema.json`, `scripts/validate_agent_decision_trace.py`).
- Enforced chain integrity, non-decreasing timestamps, and contiguous step IDs.

## v8.2.0

### Added
- Tool Invocation Proposal contract (`schemas/tool_invocation_proposal.schema.json`, `scripts/validate_tool_invocation.py`).
- Enforced `forbids_autonomous_execution=true` and bounded timeouts/retries.

## v8.1.0

### Added
- Agent Plan Contract (`schemas/agent_plan.schema.json`, `schemas/agent_plan_step.schema.json`, `scripts/validate_agent_plan.py`).
- Enforced DAG cycle checks, contiguous step indices, and a hard maximum step limit of 64.

## v8.0.0

### Added
- Agent Runtime Boundary Contract (`schemas/agent_session.schema.json`, `schemas/agent_task.schema.json`, `schemas/agent_context_budget.schema.json`).
- Added `scripts/validate_agent_session.py`, `scripts/validate_agent_task.py`, and `scripts/validate_agent_context_budget.py`.

## v7.8.0

### Notes

- v7.5 Bounded Reference Index contract implementation (schemas, validator,
  reader, fixtures, tests, release gate integration).
- v7.4 Parametric Template Cache contract implementation (schemas, validator,
  fixtures, tests, release gate integration).
- v7.6 Human-Approved Execution Gate RFC expanded with learning boundary,
  execution evidence bundle, multi-expert advisory review, ambiguity
  resolution and skill promotion rules.
- v7.7 Human-Approved Execution Gate contract implementation (7 schemas,
  validator with 16 rejection codes, 11 fixtures, 27 tests, 5 release
  gate checks).
- Added Expert Conflict Pre-Resolution RFC for deterministic pre-human
  conflict reduction before escalation.
- v7.8 Expert Conflict Pre-Resolution contract implementation (5 schemas,
  validator with 13 rejection codes, 9 fixtures, 23 tests, 4 release
  gate checks).

### Added

- Added `schemas/expert_conflict_bundle.schema.json`,
  `schemas/pre_resolution_protocol.schema.json`,
  `schemas/pre_resolution_step.schema.json`,
  `schemas/pre_resolution_report.schema.json`,
  `schemas/human_escalation_decision.schema.json` for the expert conflict
  pre-resolution contract.
- Added `scripts/validate_expert_conflict_pre_resolution.py` with 13 rejection
  codes covering conflict bundle, protocol, step, report, and escalation
  decision validation.
- Added `examples/expert_conflict_pre_resolution/` with 9 synthetic fixtures
  (5 accepted, 4 rejected) and README.
- Added `tests/test_expert_conflict_pre_resolution_validator.py` with 23
  deterministic tests covering all artifact types and rejection scenarios.
- Added 4 expert conflict pre-resolution checks to `scripts/verify_release.py`
  release gate.
- Added `docs/V78_ROADMAP_SEED.md` and `docs/V78_READINESS_REVIEW.md`.

- Expanded `docs/RFC_HUMAN_APPROVED_EXECUTION_GATE.md` with:
  - Learning Boundary section (assistants do not self-modify; learning is
    accumulated approved procedures, evidence and versioned skills).
  - Execution Evidence Bundle component (frozen evidence from sandboxed
    execution required before skill promotion).
  - Ambiguity Resolution Record with `promotes_to_rule` and
    `promotes_to_skill` fields.
  - Explicit safety rules: no unvalidated code execution, no CORE public
    modification without Development Audit.
  - Non-goal: no assistant self-modification without human approval and
    CORE validation.
  - Two additional open questions (ambiguity-driven scope rules, advisory
    expert count per risk tier).

- Added `schemas/bounded_reference_index.schema.json`,
  `schemas/bounded_read_window.schema.json`,
  `schemas/processed_reference_cache.schema.json` for the bounded reference
  index contract.
- Added `scripts/validate_bounded_reference_index.py` with 16 rejection codes
  covering index structure, read windows, processed cache, and safety policies.
- Added `scripts/read_bounded_reference.py` deterministic reader that resolves
  ref_id, reads bounded window, fingerprints content, and stops at markers,
  max_bytes or EOF.
- Added `examples/bounded_reference_index/` with 7 synthetic fixtures (3 valid,
  4 rejected), sample_document.md with 3 indexed chapters, and README.
- Added `tests/test_bounded_reference_index.py` with 26 deterministic tests
  covering validator, reader, end policies, fingerprint stability, max_bytes
  truncation, explicit end markers, error cases, and byte-stability.
- Added 3 bounded reference index checks to `scripts/verify_release.py`
  release gate.
- Added `docs/V75_ROADMAP_SEED.md` and `docs/V75_READINESS_REVIEW.md`.

- Added `schemas/parametric_template.schema.json`,
  `schemas/variable_binding.schema.json`,
  `schemas/parametric_cache_entry.schema.json` for the parametric template
  cache contract.
- Added `scripts/validate_parametric_template.py` with 16 rejection codes
  covering template structure, variable binding, cache entry, and safety
  policies.
- Added `examples/parametric_templates/` with 6 synthetic fixtures (3 valid,
  3 invalid) and README.
- Added `tests/test_parametric_template_validator.py` with 23 deterministic
  tests covering valid fixtures, invalid fixtures, directory validation,
  byte-stability, and structural edge cases for all three artifact types.
- Added 6 parametric template checks to `scripts/verify_release.py` release
  gate.
- Added `docs/V74_ROADMAP_SEED.md` and `docs/V74_READINESS_REVIEW.md`.

### Changed

- Established `docs/NEXT_ROADMAP_WORK_PLAN.md` as a living tracker with
  explicit status markers.
- Added a conservative historical documentation archive under `docs/archive/`.
- Added flow examples to the operational certainty collapse and controlled
  retrieval RFCs.
- Added offline Protocol Model candidate package certification, more negative
  candidate-package fixtures and v6.1 readiness documentation.
- Added candidate-output diagnostics, the v6.2 roadmap seed and the v6.2
  readiness review.
- Added external candidate-output intake, the v6.3 roadmap seed and the v6.3
  readiness review.
- Added multi-candidate comparison fixtures, the v6.4 roadmap seed and the
  v6.4 readiness review.
- Added external Protocol Model submission intake and comparison fixtures, the
  v6.5 roadmap seed and the v6.5 readiness review.
- Added the Protocol Model certification dossier, the v6.6 roadmap seed and
  the v6.6 readiness review.
- Added the frozen domain vocabulary bundle, the v6.7 roadmap seed and the
  v6.7 readiness review.
- Added the frozen command-candidate bundle, the v6.8 roadmap seed and the
  v6.8 readiness review.
- Added the frozen compiled command-candidate bundle, the v6.9 roadmap seed
  and the v6.9 readiness review.
- Added the frozen Protocol Model preintegration package, the v7.0 roadmap
  seed and the v7.0 readiness review.
- Added the CORE verification substrate positioning document and removed
  private downstream project names from public integration documentation.
- Added the cross-repository workflow and execution dictionary for public CORE
  and private downstream integration work.
- Added v7.1 state watcher schema, business event schema, validation and
  derivation scripts, synthetic fixtures, deterministic tests, and readiness
  review.
- Added RFC_LAW_REGISTRY_AND_PATCHES.md (future: versioned law registry,
  deprecation, supersession, replay and patch accumulation).
- Added RFC_PROBABILISTIC_PROPOSAL_DETERMINISTIC_CERTIFICATION.md to define
  the boundary between probabilistic proposals and deterministic certification.
- Added V72_ROADMAP_SEED.md to define the next private-domain integration
  sprint without exposing private downstream details.
- Added RFC_PARAMETRIC_TEMPLATE_CACHE.md to define structural cache reuse for
  validated templates with variable bindings.
- Added RFC_BOUNDED_REFERENCE_INDEX.md to define indexed fixed-window document
  reads for low-token, fingerprinted agent context gathering.
- Added RFC_TEMPORAL_SURROGATE_PERTURBATION.md to define tri-axial surrogate
  perturbation experiments and wave-signature candidates.
- Added RFC_HUMAN_APPROVED_EXECUTION_GATE.md to define human-approved,
  advisory-reviewed sandbox execution and skill promotion.
- Added v7.2 private-domain integration fixtures (synthetic vocabulary,
  command candidates for accepted/rejected-private-data/rejected-unknown),
  validation script with 3-layer checks (structure, private-data rejection,
  effects/command-known), 20 deterministic tests, and readiness review.
- Added v7.3 classification candidate contract: JSON schema, RFC,
  synthetic fixtures (accepted, clarification_required, rejected_low_confidence,
  rejected_unsafe_pattern, invalid_confidence_mismatch,
  invalid_missing_vocabulary_id), deterministic validator with 14 rejection
  codes, 20 tests, release verification integration, and roadmap seed.

## v5.3.0

### Added

- Promoted Router Static Explainability to stable release status.
- Added `docs/releases/v5.3.0.md`.
- Added `docs/V53_RELEASE_CHECKLIST.md`.

### Changed

- Updated `docs/CORE_ROADMAP.md`, `docs/FUTURE_CAPABILITIES_ROADMAP.md`,
  `docs/VERSIONING_POLICY.md`, `README.md`, `docs/CORE_RELEASE_README.md`,
  `pyproject.toml`, and `core_runtime/__init__.py` to align with `v5.3.0`.
- Kept router static explainability artifacts and tests in the stable release
  line.

### Notes

- Stable release promotion only.
- No runtime changes.
- No scheduler changes.
- No routing runtime.
- No proposal execution.
- No tool execution.
- No command execution.
- No LLM/model integration.
- No batch runtime.

## v5.3.0-rc1

### Added

- Promoted Router Static Explainability to release candidate status.
- Added `docs/releases/v5.3.0-rc1.md`.
- Added `docs/V53_RELEASE_CANDIDATE_CHECKLIST.md`.
- Extended `StaticExplainer` with router-specific read-only queries for
  selection, rejection, decision tracing and evidence bundles.
- Added router explainability coverage in
  `tests/test_router_static_explainability.py`.

### Changed

- Updated `docs/CORE_ROADMAP.md`, `docs/FUTURE_CAPABILITIES_ROADMAP.md`,
  `docs/VERSIONING_POLICY.md`, `README.md`, `docs/CORE_RELEASE_README.md`,
  `pyproject.toml`, and `core_runtime/__init__.py` to align with
  `v5.3.0rc1`.
- Extended router audit derivation payloads to carry per-expert records so the
  static explainability layer can answer selection and rejection queries.

### Notes

- Release candidate packaging only.
- No runtime changes.
- No scheduler changes.
- No routing runtime.
- No proposal execution.
- No tool execution.
- No command execution.
- No LLM/model integration.
- No batch runtime.

## v5.2.0

### Added

- Promoted Router Audit Trail Derivation to stable release status.
- Added `docs/releases/v5.2.0.md`.
- Added `docs/V52_RELEASE_CHECKLIST.md`.

### Changed

- Updated `docs/CORE_ROADMAP.md`, `docs/FUTURE_CAPABILITIES_ROADMAP.md`,
  `docs/VERSIONING_POLICY.md`, `README.md`, `docs/CORE_RELEASE_README.md`,
  `pyproject.toml`, and `core_runtime/__init__.py` to align with `v5.2.0`.
- Kept the router audit trail derivation workflow gates in place for the
  stable release line.

### Notes

- Stable release promotion only.
- No runtime changes.
- No scheduler changes.
- No routing runtime.
- No proposal execution.
- No tool execution.
- No command execution.
- No LLM/model integration.
- No batch runtime.

## v5.2.0-rc1

### Added

- Promoted Router Audit Trail Derivation to release candidate status.
- Added `docs/releases/v5.2.0-rc1.md`.
- Added `docs/V52_RELEASE_CANDIDATE_CHECKLIST.md`.
- Added MuJoCo-inspired architecture notes in
  `docs/MUJOCO_INSPIRED_CORE_ARCHITECTURE_NOTES.md`.

### Changed

- Updated `docs/CORE_ROADMAP.md`, `docs/FUTURE_CAPABILITIES_ROADMAP.md`,
  `docs/VERSIONING_POLICY.md`, `README.md`, `docs/CORE_RELEASE_README.md`,
  `pyproject.toml`, and `core_runtime/__init__.py` to align with
  `v5.2.0-rc1`.
- Extended the release verification gates to include router audit trail
  derivation alongside router replay certification.

### Notes

- Release candidate packaging only.
- No runtime changes.
- No scheduler changes.
- No routing runtime.
- No proposal execution.
- No tool execution.
- No command execution.
- No LLM/model integration.
- No batch runtime.

## v5.1.0

### Added

- Promoted Router Replay Certification to stable release status.
- Added `docs/releases/v5.1.0.md`.
- Added `docs/V51_RELEASE_CHECKLIST.md`.

### Changed

- Updated `docs/CORE_ROADMAP.md`, `docs/FUTURE_CAPABILITIES_ROADMAP.md`,
  `docs/VERSIONING_POLICY.md`, `README.md`, `docs/CORE_RELEASE_README.md`,
  `pyproject.toml`, and `core_runtime/__init__.py` to align with `v5.1.0`.
- Kept the router replay certification workflow gates in place for the stable
  release line.

### Notes

- Stable release promotion only.
- No runtime changes.
- No scheduler changes.
- No routing runtime.
- No proposal execution.
- No tool execution.
- No command execution.
- No LLM/model integration.
- No batch runtime.

## v5.1.0-rc1

### Added

- Promoted the Router Replay Certification step to release candidate status.
- Added `docs/releases/v5.1.0-rc1.md`.
- Added `docs/V51_RELEASE_CANDIDATE_CHECKLIST.md`.
- Added `scripts/certify_router_replay.py` as the deterministic replay
  certification step for Expert Router fixtures.
- Added `tests/test_certify_router_replay_script.py` to cover single-fixture
  and batch replay certification.

### Changed

- Updated `docs/CORE_ROADMAP.md`, `docs/FUTURE_CAPABILITIES_ROADMAP.md`,
  `docs/VERSIONING_POLICY.md`, `README.md`, `docs/CORE_RELEASE_README.md`,
  `pyproject.toml`, and `core_runtime/__init__.py` to align with
  `v5.1.0-rc1`.
- Extended the release verification and replay-certification workflow gates to
  include router replay certification.

### Notes

- Documentation, fixtures and release alignment only.
- No runtime changes.
- No scheduler changes.
- No routing runtime.
- No proposal execution.
- No tool execution.
- No command execution.
- No LLM/model integration.
- No batch runtime.

## v5.0.0

### Added

- Promoted the Expert Router Foundation to stable release status.
- Added `docs/releases/v5.0.0.md`.
- Added `docs/V50_RELEASE_CHECKLIST.md`.
- Kept the Expert Router fixtures, structural validator, deterministic
  evaluator and deterministic batch report in the stable release line.

### Changed

- Updated `docs/CORE_ROADMAP.md`, `docs/FUTURE_CAPABILITIES_ROADMAP.md`,
  `docs/VERSIONING_POLICY.md`, `README.md`, `pyproject.toml`, and
  `core_runtime/__init__.py` to align with the v5.0.0 stable release.

### Notes

- Documentation, fixtures and release alignment only.
- No runtime changes.
- No scheduler changes.
- No routing runtime.
- No proposal execution.
- No tool execution.
- No command execution.
- No LLM/model integration.
- No batch runtime.

## v5.0.0-rc1

### Added

- Promoted the Expert Router Foundation to release candidate status.
- Added `docs/releases/v5.0.0-rc1.md`.
- Added `docs/V50_RELEASE_CANDIDATE_CHECKLIST.md`.
- Added `examples/expert_router/` as the fixture set for the v5.0.0-rc1
  Expert Router Foundation.
- Added `docs/RFC_EXPERT_ROUTER.md` to define deterministic routing decision
  contracts and offline eligibility selection.
- Added `docs/RFC_BLOCKCHAIN_ANCHORING.md` to document a future off-chain
  artifact anchoring model.
- Added `scripts/validate_expert_router.py` as the Sprint 2 structural
  validator for routing decision fixtures.
- Added `scripts/evaluate_expert_router.py` as the Sprint 3 deterministic
  evaluator for routing decision fixtures.
- Added `scripts/report_expert_router.py` as the Sprint 4 deterministic batch
  report for routing decision fixtures.

### Changed

- Updated `docs/CORE_ROADMAP.md`, `docs/FUTURE_CAPABILITIES_ROADMAP.md`,
  `docs/VERSIONING_POLICY.md`, `README.md`, `pyproject.toml`, and
  `core_runtime/__init__.py` to align with the v5.0.0-rc1 release candidate.
- Updated `docs/EXPERT_PROPOSAL_CONTRACT.md` and `docs/EXECUTION_PROFILES_RFC.md`
  to reference the router foundation.

### Notes

- Documentation, fixtures and release alignment only.
- No runtime changes.
- No scheduler changes.
- No routing runtime.
- No proposal execution.
- No tool execution.
- No command execution.
- No LLM/model integration.
- No batch runtime.

# v4.9.0

### Added

- Promoted the Audit Trail foundation to stable release status.
- Added `docs/releases/v4.9.0.md`.
- Added `docs/V49_AUDIT_TRAIL_STABLE_CHECKLIST.md`.
- Kept the derived audit trail foundation in the stable release line with
  separate audit fingerprints, canonical `logical_tick`, semantic
  `correlation_id` namespaces and read-only explainability.

### Notes

- Documentation and version alignment only.
- No runtime changes.
- No scheduler changes.
- No routing changes.
- No replay semantic changes.
- No KnowledgeBase internal changes.
- No profile execution.
- No proposal execution.
- No tool execution.
- No command execution.
- No expert router.
- No proposal router.
- No EventLog runtime authority.
- No StaticExplainer runtime authority.
- No Gaia integration.
- No WiFi sensing runtime integration.
- No LLM/model integration.
- No Audit Trail authority escalation.

## v4.9.0-rc1

### Added

- Introduced the Audit Trail Foundation as a derived, passive and
  deterministic layer over already-produced validation and report artifacts.
- Added `docs/releases/v4.9.0-rc1.md`.
- Added `docs/V49_AUDIT_TRAIL_RC_CHECKLIST.md`.
- Added `core_runtime/core/audit_event.py`, `core_runtime/core/audit_trail_index.py`
  and `scripts/derive_audit_trail.py` for separated audit schema, indexing and
  derivation.
- Extended `core_runtime/core/explainability.py` and `scripts/verify_release.py`
  to consume and verify derived audit trails read-only.

### Notes

- Release candidate freeze only.
- No runtime changes.
- No scheduler changes.
- No routing changes.
- No replay semantic changes.
- No KnowledgeBase internal changes.
- No profile execution.
- No proposal execution.
- No tool execution.
- No command execution.
- No EventLog mutation.
- No runtime authority changes.
- No LLM/model integration.

## v4.8.0

### Added

- Promoted the Execution Profiles foundation to stable release status.
- Added `docs/releases/v4.8.0.md`.
- Added `docs/V48_RELEASE_CHECKLIST.md`.
- Kept the static Execution Profile fixtures, structural validator,
  deterministic proposal/profile compatibility checker and deterministic
  compatibility matrix report in the stable release line.

### Notes

- Documentation and version alignment only.
- No runtime changes.
- No scheduler changes.
- No routing changes.
- No replay semantic changes.
- No KnowledgeBase internal changes.
- No profile execution.
- No proposal execution.
- No tool execution.
- No command execution.
- No expert router.
- No proposal router.
- No EventLog integration.
- No StaticExplainer integration.
- No CORE Protocol Model implementation.
- No LLM/model integration.
- No Execution Profiles runtime.

## v4.8.0-rc1

### Added

- Added `docs/EXECUTION_PROFILES_RFC.md`.
- Added static Execution Profile fixtures under `examples/execution_profiles/`.
- Added structural tests for Execution Profile fixtures.
- Added `scripts/validate_execution_profile.py` as a read-only structural validator for Execution Profile fixtures.
- Added tests for Execution Profile validation and stable JSON output.
- Added `scripts/check_profile_proposal_compatibility.py` as a deterministic read-only compatibility checker for Expert Proposals and Execution Profiles.
- Added tests for proposal/profile compatibility decisions and byte-stable output.
- Added `examples/compatibility_matrix_pairs.json` as the canonical proposal/profile compatibility matrix.
- Added `scripts/report_compatibility_matrix.py` as a deterministic read-only compatibility matrix report tool.
- Added tests for compatibility matrix reporting, byte-stability and failure handling.
- Added compatibility matrix verification to `scripts/verify_release.py`.

### Notes

- The validator does not execute profiles, tools or commands.
- The validator does not route proposals or experts.
- The checker does not execute profiles, proposals, tools or commands.
- The checker does not route experts or proposals.
- The matrix report does not execute profiles, proposals, tools or commands.
- The matrix report does not route experts or proposals.
- None of these scripts write EventLog entries.
- No runtime changes.
- No CORE Protocol Model implementation.

## Unreleased

### Notes

- No new release items yet.

## v4.7.0

### Added

- Promoted the Expert Proposal foundation to stable release status.
- Added `docs/releases/v4.7.0.md`.
- Added `docs/V47_RELEASE_CHECKLIST.md`.
- Kept the static Expert Proposal fixtures, structural validator,
  deterministic evaluator and batch report in the stable release line.

### Notes

- Documentation and version alignment only.
- No runtime changes.
- No scheduler changes.
- No routing changes.
- No replay semantic changes.
- No KnowledgeBase internal changes.
- No tool execution.
- No command execution.
- No expert router.
- No proposal router.
- No EventLog integration.
- No StaticExplainer integration.
- No CORE Protocol Model implementation.
- No LLM/model integration.
- No Execution Profiles.

## v4.7.0-rc1

### Added

- Added `scripts/verify_release.py` for local post-release verification.
- Added `docs/EXPERT_PROPOSAL_LIFECYCLE.md`.
- Added static Expert Proposal fixtures under `examples/expert_proposals/`.
- Added structural tests for the Expert Proposal fixture contract.
- Added `scripts/validate_expert_proposal.py` as a read-only structural validator.
- Added tests for Expert Proposal structural validation and stable JSON output.
- Added `scripts/evaluate_expert_proposal.py` as a deterministic read-only evaluator for Expert Proposal fixtures.
- Added tests for Expert Proposal evaluation and stable decision output.
- Added `scripts/report_expert_proposals.py` as a deterministic read-only batch report tool for Expert Proposal fixtures.
- Added tests for Expert Proposal batch reporting, deterministic output, and failure handling.

### Changed

- Clarified that CORE Protocol Model is a future client of the Expert Proposal
  Contract.
- Added domain expansion policy for future application domains.
- Documented the minimal `core.expert_proposal.v1` fixture schema.

### Notes

- No runtime changes.
- No proposal validator implementation.
- No expert router implementation.
- No LLM/model integration.
- No Execution Profiles yet.

## v4.6.0

### Added

- Promoted the synthetic audio, image, and WiFi CSI-like bridges to stable
  release status.
- Added `docs/releases/v4.6.0.md`.
- Added `docs/V46_RELEASE_CHECKLIST.md`.
- Stabilized the future capability consolidation docs and RC release notes.
- Kept workflow examples, validation tooling, and the examples index in the
  stable v4.6 line.

### Notes

- Documentation and version alignment only.
- No runtime changes.
- No scheduler changes.
- No routing changes.
- No replay semantic changes.
- No KnowledgeBase internal changes.
- No expert router.
- No expert proposal adapter.
- No CORE Protocol Model implementation.
- No live sensors.
- No RuView integration.
- No GPU/Kaggle dependency.
- No registry implementation.
- No LLM/model integration.

## v4.6.0-rc1

### Added

- Frozen the v4.6 synthetic bridge line for release candidate review.
- Added release candidate notes and RC checklist.
- Consolidated the future capability roadmap and application domain notes.
- Preserved the synthetic audio, image, and WiFi CSI bridge examples as the
  RC baseline.

### Notes

- Documentation and version alignment only.
- No runtime changes.
- No scheduler changes.
- No routing changes.
- No replay semantic changes.
- No KnowledgeBase internal changes.
- No expert router.
- No expert proposal adapter.
- No CORE Protocol Model implementation.
- No live sensors.
- No RuView integration.
- No GPU/Kaggle dependency.
- No registry implementation.
- No LLM/model integration.

## v4.5.0

### Added

- Promoted Fork and Extension Readiness to stable v4.5.0.
- Added fork quickstart documentation.
- Added stable release notes for v4.5.0.

### Notes

- No real adapters.
- No live sensors.
- No RuView integration.
- No GPU/Kaggle dependency.
- No fixture registry.
- No runtime, scheduler, routing, replay semantic, or KnowledgeBase internal changes.

## v4.5.1

### Added

- Added basic practical adapter examples.
- Added domain and privacy adapter examples.
- Added workflow examples.
- Added `scripts/run_all_examples.py`.
- Added `docs/EXAMPLES_INDEX.md`.
- Added stable release notes for v4.5.1.

### Notes

- No real adapters.
- No live sensors.
- No RuView integration.
- No GPU/Kaggle dependency.
- No fixture registry.
- No runtime, scheduler, routing, replay semantic, or KnowledgeBase internal changes.

## Unreleased

### Notes

- No new release items yet.

## v4.4.0-rc1

### Added

- Added release candidate notes for the Sensor Evidence contract.
- Aligned package version and documentation for `v4.4.0-rc1`.

### Notes

- No live sensors.
- No RuView integration.
- No GPU/Kaggle dependency.
- No runtime, scheduler, routing, replay semantic, or KnowledgeBase internal changes.

## v4.3.2

### Added

- Added development tooling dependencies for Ruff and Mypy.
- Added `requirements-dev.txt` for local quality tooling.
- Added `docs/KNOWN_ISSUES.md` to track non-blocking release issues.
- Documented Mypy as report-only for selected core modules.
- Native read-only explainability lookup paths with generic fallback preserved.
- Explainable replay fixture validation over frozen v4.2.0 artifacts.
- Release quality gate documentation.
- Sensor Evidence offline bootstrap for v4.4 planning.

### Changed

- Clarified the v4.3.2 quality gate: Ruff is hard gate, Mypy is report-only.
- Updated CI/tooling documentation so missing quality tools are no longer silent.
- Clarified roadmap and documentation boundaries.
- Added Ruff as the minimum static quality gate.
- Moved Kaggle/GPU planning outside the immediate v4.4/v4.5 roadmap.

### Notes

- No runtime, scheduler, routing, replay semantic, or KnowledgeBase internal changes.
- No live sensor integration.
- No RuView integration.
- No GPU/Kaggle dependency.

### Added

- Introduced the v4.3 static explainability draft API.
- Added `StaticExplainer` for read-only queries over completed CORE executions.
- Added serializable `ExplanationResult` records.
- Added an explainable replay fixture validation path over frozen v4.2.0 artifacts.
- Added a frozen explainability fixture under `tests/fixtures/explainability/v4_2_0_minimal/`.
- Added an explainable replay demo script.
- Added cross-platform replay audit guidance for frozen reference artifacts.
- Added roadmap documentation in `docs/CORE_ROADMAP.md`.
- Added Kaggle GPU planning boundary in `docs/KAGGLE_GPU_WORKFLOW.md`.
- Added native-adapter-oriented tests for static explainability.
- Documented the v4.3.x stabilization path before sensor integration.
- Added `docs/QUALITY_GATE.md` documenting the v4.3.2 release quality gate.
- Added Ruff as the minimum static quality tool before tagging.
- Added deterministic sensor evidence bootstrap primitives for v4.4 planning.
- Added a simulated scalar sensor fixture with deterministic fingerprint tests.
- Added documentation for v4.4 Sensor Evidence Schema Bootstrap acceptance criteria.
- Added `docs/CORE_VISION.md`.
- Added `docs/SENSOR_EVIDENCE_MODEL.md`.

### Changed

- Improved StaticExplainer lookup behavior to prefer native artifact APIs when available while preserving generic fallback behavior.
- Clarified missing versus unsupported explainability outcomes for opaque artifacts.
- Clarified documentation boundaries between CORE vision, roadmap, README, and quality gate.
- Moved Kaggle/GPU planning out of the active v4.4/v4.5 roadmap and into future v5.x+ notes.

### Documentation

- Added `docs/EXPLAINABILITY_STATIC_API.md`.
- Added `docs/CROSS_PLATFORM_REPLAY_AUDIT.md`.

### Notes

- Mypy remains a future/report-only quality target and is not yet a hard gate.
- Kaggle is documented only as a future external GPU workflow.
- No GPU dependency was added.
- No sensor implementation was added.
- No RuView integration was added.
- No runtime, scheduler, routing, replay, or KnowledgeBase internal changes.

## [4.1.0] - 2026-05-20

- Unified public runtime version to `4.1.0`.
- Hardened `KnowledgeBase` as append-only, idempotent, deeply immutable, and auditable.
- Stabilized deterministic replay certification with frozen reference datasets.
- Added canonical operational, audit, and schema fingerprint helpers.
- Added deterministic reference data under `tests/reference_data/v4.1.0/`.
- Added replay certification script and CI workflow for cross-platform replay validation.
- Prepared `ExecutionGraph` as a derived provenance layer, not a runtime authority.

## Notes

- Legacy `v3.x` references remain only where they describe historical plans, historical datasets, or compatibility tests for prior CORE artifacts.
