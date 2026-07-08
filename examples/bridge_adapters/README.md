# Bridge Adapter Fixtures

| File | Expected | Key rejection |
|------|----------|---------------|
| accepted_strict_bridge.json | PASS | — |
| accepted_emergency_bridge.json | PASS | — |
| rejected_autonomous_execution.json | FAIL | autonomous_execution_allowed |
| rejected_private_namespace_leak.json | FAIL | private_namespace_leak_not_forbidden |
| rejected_unknown_schema_ref.json | FAIL | unknown_core_schema_referenced |
| rejected_fail_closed_false.json | FAIL | fail_closed_not_set |
| rejected_missing_verification_method.json | FAIL | verification_method_not_declared |
