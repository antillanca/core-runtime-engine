# CORE Versioning Policy

## Semantic Versioning

CORE follows strict semantic versioning (MAJOR.MINOR.PATCH).

- **Current**: v11.2.0
- **MAJOR**: breaking changes to public schemas, validator CLI contracts,
  or frozen fingerprint/canonicalization semantics.
- **MINOR**: new schemas, new validator scripts, new CLI subcommands
  (additive, non-breaking).
- **PATCH**: bug fixes, performance improvements, documentation.

## v11.0.0 — clean rebuild

v11 is a whitelist rebuild of the engine: only public schemas, validators,
tooling CLI surfaces and generic downstream-adapter entrypoints were carried
forward. The full historical repository
(CPT simulator, protocol-model candidate certification, expert router,
GAIA pipeline, and the v8.x-pinned governance freeze) is preserved at the
`legacy-final` tag and in `_archive/core-runtime-engine-legacy/` in the
workspace. See
[CORE_REBUILD_FROM_ZERO.md](CORE_REBUILD_FROM_ZERO.md) for the full
rationale and whitelist/blacklist.

Versioning resets to v11.0.0 rather than continuing the v10.x line because
the surface changed too much for a patch/minor bump to be meaningful.

## v11.0.1 — public-surface hygiene release

v11.0.1 supersedes the withdrawn v11.0.0 release. It keeps the v11 public
surface and rebuild rationale, while tightening public/private boundary
hygiene and release verification.

## v11.1.0 — frozen-rule anchoring

v11.1.0 adds generic frozen rule sets, blinded personal commitments,
externally signed approvals, deterministic SHA-256 Merkle batching, unsigned
EVM transaction preparation, gas-reserve checks, read-only chain evidence, and
the minimal non-custodial `CoreRuleAnchor` contract. It does not change CORE
into a runtime, wallet, financial authority, or source of domain truth.
