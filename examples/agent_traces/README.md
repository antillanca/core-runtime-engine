# Agent Decision Trace Fixtures (v8.3)

Synthetic artifacts for the Agent Decision Trace Contract validation.

## Accepted

| File | Entries | Governance | Description |
|------|---------|------------|-------------|
| `accepted_linear_trace.json` | 3 | 0 | Linear observation→proposal→approval |
| `accepted_governance_rejection_trace.json` | 2 | 1 | Governance violation correctly flagged |

## Rejected

| File | Expected Rejection Code |
|------|------------------------|
| `rejected_non_contiguous_ids.json` | non_contiguous_entry_ids |
| `rejected_review_not_set.json` | requires_review_not_set |
| `rejected_immutability_false.json` | immutability_guarantee_not_true |
| `rejected_non_monotonic_timestamps.json` | non_monotonic_timestamps |
| `rejected_summary_count_mismatch.json` | trace_summary_entry_count_mismatch |
