# Expert Conflict Pre-Resolution Examples

## Accepted Fixtures

| File | Artifact |
|------|----------|
| accepted_conflict_bundle.json | Valid expert conflict bundle |
| accepted_pre_resolution_protocol.json | Valid pre-resolution protocol |
| accepted_pre_resolution_step.json | Valid pre-resolution step result |
| accepted_pre_resolution_report.json | Valid pre-resolution report |
| accepted_human_escalation_decision.json | Valid human escalation decision |

## Rejected Fixtures

| File | Rejection Code |
|------|---------------|
| rejected_llm_authority_resolution.json | `llm_authority_resolution_rejected` |
| rejected_missing_preserved_claims.json | `missing_preserved_claims` |
| rejected_human_required_bypassed.json | `human_required_bypassed` |
| rejected_unbounded_context_resolution.json | `unbounded_context_resolution_rejected` |

## Validation Rules

- Pre-resolution can organize disagreement; it cannot authorize execution.
- Original expert claims must be preserved.
- LLM consensus is not authority.
- Human approval cannot be bypassed when profile/risk requires it.
- Unbounded context reads cannot resolve conflicts.
- Pre-resolution reports cannot execute actions.
- CORE rejection cannot be overridden by protocol.
