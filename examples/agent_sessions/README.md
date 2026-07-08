# Agent Sessions — Synthetic Fixtures

Public synthetic fixtures for the CORE v8.0 Agent Runtime Boundary contracts.

## Accepted Fixtures

| File | Description |
|------|-------------|
| `accepted_read_and_propose.json` | Valid agent session: bounded read + proposal |
| `accepted_escalation_to_human.json` | Valid agent session: escalation to human for high-risk task |
| `accepted_agent_task.json` | Valid agent task with intent, slots, safety |
| `accepted_agent_context_budget.json` | Valid context budget with read/write/tool constraints |
| `accepted_agent_decision_trace.json` | Valid decision trace with 5 steps |

## Rejected Fixtures

| File | Expected Rejection Code |
|------|------------------------|
| `rejected_unbounded_context.json` | `unbounded_context` |
| `rejected_tool_execution.json` | `tool_execution_without_approval` |
| `rejected_autonomous_execution.json` | `autonomous_execution_allowed` |
| `rejected_private_path.json` | `private_path_detected` |

All fixtures use synthetic data. No private paths, credentials, or domain-specific logic.
