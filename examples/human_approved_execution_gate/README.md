# Human-Approved Execution Gate Fixtures

Synthetic fixtures for the CORE execution gate validation contract.

## Accepted Fixtures

These fixtures demonstrate valid artifacts that pass all validation checks:

| File | Type | Description |
|------|------|-------------|
| `accepted_execution_proposal.json` | execution_proposal | Read-only docs check proposal |
| `accepted_advisory_review.json` | advisory_review | Advisory review with approve_with_conditions |
| `accepted_multi_expert_review_bundle.json` | multi_expert_review_bundle | 3-expert partial agreement bundle |
| `accepted_human_approval_record.json` | human_approval_record | Human approval for sandbox execution |
| `accepted_sandbox_execution_record.json` | sandbox_execution_record | Successful sandbox execution |
| `accepted_skill_promotion_candidate.json` | skill_promotion_candidate | Skill promotion with disabled default |
| `accepted_ambiguity_resolution_record.json` | ambiguity_resolution_record | Resolved scope interpretation ambiguity |

## Rejected Fixtures

These fixtures demonstrate artifacts that fail validation:

| File | Rejection Code | Reason |
|------|----------------|--------|
| `rejected_llm_authority.json` | `llm_authority_rejected` | Advisory review claims execution authority |
| `rejected_missing_human_approval.json` | `missing_human_approval` | Proposal skips human approval |
| `rejected_scope_expansion.json` | `scope_expansion_detected` | Declared scope escapes boundaries |
| `rejected_skill_auto_activation.json` | `skill_auto_activation_rejected` | Skill candidate has activation_default=enabled |
