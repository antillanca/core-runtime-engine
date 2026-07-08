# Execution Profile Fixtures

This directory contains static Execution Profile fixtures for CORE v4.8
planning.

These files are declarative examples only.

CORE does not execute these profiles in this sprint.

They do not represent runtime behavior, scheduling behavior or routing
behavior.

## Fixtures

| Fixture | Profile | Purpose |
|---|---|---|
| `minimal_profile.json` | `minimal` | Structural checks only |
| `standard_profile.json` | `standard` | Validation + evaluation + report |
| `certified_profile.json` | `certified` | Requires certified evidence |
| `explainable_profile.json` | `explainable` | Requires explanation-ready artifacts |
| `audit_profile.json` | `audit` | Requires maximum provenance and replay-ready reporting |

## Safety boundary

These profiles are static data.

They do not:

- execute tools;
- execute commands;
- route experts;
- mutate runtime state;
- write EventLog entries;
- call StaticExplainer;
- change scheduler behavior.

## Contract

All fixtures use:

```text
profile_schema = core.execution_profile.v1
```

Required fields:

* `profile_schema`
* `profile_id`
* `profile_name`
* `description`
* `requirements`
* `safety`
* `expected_use`
* `notes`

## Validate profile

```bash
python scripts/validate_execution_profile.py examples/execution_profiles/audit_profile.json
```

The validator is read-only and does not execute profiles, tools or commands.

## Check proposal compatibility

```bash
python scripts/check_profile_proposal_compatibility.py \
  --proposal examples/expert_proposals/accepted_proposal.json \
  --profile examples/execution_profiles/certified_profile.json
```

The checker is read-only and does not execute profiles, proposals, tools or
commands.

## Compatibility matrix

```bash
python scripts/report_compatibility_matrix.py --allow-expected-incompatible
```

The matrix report uses `examples/compatibility_matrix_pairs.json` and remains
read-only.

## Non-goals

This directory does not implement:

* profile validation;
* profile execution;
* expert routing;
* proposal routing;
* EventLog integration;
* StaticExplainer integration;
* CORE Protocol Model;
* LLM integration;
* runtime mutation.
