# Agent Plan Fixtures (v8.1)

Synthetic artifacts for the Agent Plan Contract validation.

## Accepted Plans

| File | Type | Description |
|------|------|-------------|
| `accepted_linear_plan.json` | agent_plan | 3-step linear plan: read, propose, escalate |
| `accepted_dag_plan.json` | agent_plan | 3-step DAG: two reads feeding into a proposal |
| `accepted_step_proposal.json` | agent_plan_step | Standalone step with tool proposal reference |
| `accepted_dependency_sequential.json` | agent_plan_dependency | Sequential dependency edge between steps |
| `accepted_result_completed.json` | agent_plan_result | Completed plan result with 3 step outcomes |

## Rejected Plans

| File | Type | Expected Rejection Codes |
|------|------|--------------------------|
| `rejected_autonomous_plan.json` | agent_plan | `plan_approval_not_required`, `step_approval_not_required`, `step_autonomous_execution_allowed` |
| `rejected_circular_plan.json` | agent_plan | `circular_dependency` |
| `rejected_parallel_side_effects.json` | agent_plan | `plan_parallel_execution_with_side_effects` |
| `rejected_private_path_plan.json` | agent_plan | `private_path_detected` |
| `rejected_invalid_depends_on.json` | agent_plan | `invalid_depends_on` |
| `rejected_self_dependency.json` | agent_plan_dependency | `self_dependency` |

## Validation

```bash
python scripts/validate_agent_plan.py examples/agent_plans/
pytest -q tests/test_agent_plan_validator.py
```
