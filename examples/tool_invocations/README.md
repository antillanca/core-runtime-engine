# Tool Invocation Proposal Fixtures (v8.2)

Synthetic artifacts for the Tool Invocation Proposal Contract validation.

## Accepted

| File | Tool | Category | Risk |
|------|------|----------|------|
| `accepted_read_tool.json` | data_reader 1.0.0 | read_only | none |
| `accepted_notification_tool.json` | notification_sender 2.1.0 | notification | low |

## Rejected

| File | Rejection Reason |
|------|------------------|
| `rejected_autonomous_write.json` | forbids_autonomous_execution=false + requires_human_approval=false for high-risk write |
| `rejected_risky_no_approval.json` | requires_human_approval=false for medium-risk external call |
| `rejected_nested_arguments.json` | Argument 'config' has nested object value |
| `rejected_private_path.json` | Absolute private path in argument |
| `rejected_invalid_safety.json` | timeout_seconds=99999 and max_retries=10 out of range |
