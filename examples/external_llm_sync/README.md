# External LLM Sync Bundle Examples

Synthetic, domain-neutral fixtures for the `core.external_llm_sync_bundle.v1` schema.

All fingerprints use placeholder SHA-256 values (`sha256:aabb..`) for illustration. Real bundles must use actual SHA-256 fingerprints of the referenced content.

## Files

| File | Status | Safety Violation | Notes |
|------|--------|------------------|-------|
| `accepted_sync_bundle.json` | accepted | none | Clean bundle with no missing facts |
| `rejected_private_data.json` | rejected | `private_data_included=true` | Private data must never be included |
| `rejected_unbounded_context.json` | rejected | `unbounded_context_used=true` | All context must be budgeted |
| `clarification_missing_fact.json` | clarification_needed | none | Missing facts prevent acceptance |

## Semantic Rules

1. `authority` must be `advisory_only` -- external LLMs never authorize execution.
2. `private_data_included` must be `false` -- no private user or system data.
3. `unbounded_context_used` must be `false` -- all context is budgeted.
4. `tool_execution_requested` must be `false` -- LLMs propose, CORE disposes.
5. If `missing_facts` is non-empty, `status` must not be `accepted`.
