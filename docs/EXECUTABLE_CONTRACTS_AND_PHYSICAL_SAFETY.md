# Executable contracts and physical safety assurance

## Purpose

A CORE contract is not complete merely because a JSON document contains all
required fields. A decision-capable contract must combine:

1. a closed or strictly projected data shape;
2. executable cross-field invariants;
3. evidence references whose integrity can be checked;
4. accepted and schema-valid semantic-negative probes;
5. a deterministic result fingerprint; and
6. an explicit authority boundary.

`scripts/evaluate_core_contract.py` applies this strict profile to the public
generic contract family. `scripts/audit_contract_executability.py` proves that
every registered generic contract accepts a coherent probe and rejects an
incoherent probe that still satisfies its published JSON Schema.

## Closed contract programs

`ContractProgram.v1` is a small, replayable instruction contract for bounded
validation. It accepts only declared instructions: load a caller-supplied
sealed input, assert a scalar condition, make a bounded derivation, stage a
transition candidate, emit a declared result, and halt. Its schema is closed
at every object boundary and every program carries a canonical fingerprint.

The program itself cannot grant effects. Its effect policy requires external
effects, network access, filesystem access, and state application to remain
`false`. `execute_contract_program()` receives inputs directly from its caller;
it does not read files, clocks, environment variables, random sources, or the
network. A staged transition is returned as a candidate only and is discarded
on any blocked, insufficient-data, or rejected result.

This is intentionally a validation and replay foundation, not an automation
authorization mechanism. A separate system must evaluate any resulting
transition under its own explicit authority and safety rules.

The distinction matters. Schema validation answers "can this document be
parsed as this contract?" Executable evaluation answers "do these values form
a coherent decision under the declared rules?"

## Epistemic boundary

CORE is not a source of universal truth. It can report only one of these
bounded knowledge classes:

- `observed`: evidence was recorded inside a declared reference class;
- `inferred`: a declared procedure derived a result from bounded evidence;
- `demonstrated_within_model`: a verifier established a proposition under
  explicit axioms, inputs, assumptions, and model limits.

A formal demonstration does not automatically prove that an empirical model
fully represents the physical world. Records, benchmarks, and observed
extremes establish current observed bounds, not absolute limits.

Averages alone are insufficient for safety. They can conceal rare failures
and boundary cases. `PhysicalSafetyAssuranceCase.v1` therefore requires the
sample basis, known extremes, their provenance, explicit limitations, and an
out-of-distribution policy of `fail_closed`. Unknown extremes remain unknown.
CORE must not interpolate them into safety claims.

The following claims are prohibited:

- unhackable;
- zero risk;
- guaranteed safe in every circumstance;
- universal truth derived from finite observations; and
- deployment authorization inferred from a passing CORE evaluation.

## Epistemic dignity

A person does not lose the right to understand, challenge, refuse, or stop a
system because they lack specialist credentials. A physical safety case must
bind evidence for:

- a plain-language disclosure;
- the limitations of available evidence;
- a contestability path;
- a local stop mechanism that requires no technical expertise; and
- a challenge policy that answers with evidence or says `unknown` explicitly.

An automated system cannot assign itself moral authority. A refusal or
challenge cannot silently weaken a safety barrier. Human approval also cannot
override a deterministic safety rejection.

## Physical authority boundary

The required control path is:

```text
LLM proposal
  -> deterministic CORE policy evaluation
  -> isolated safety controller
  -> independent physical energy isolation or mechanical limit
  -> actuator
```

The LLM is `advisory_only`. General-purpose compute has no direct actuation
path. CORE validates artifacts and produces reproducible decisions, but does
not authorize execution or deployment. A catastrophic hazard needs at least
two non-bypassable barriers in distinct enforcement domains, including an
isolated safety controller and physical isolation or a mechanical limit.

## Required tests

Every declared hazard must cover all of these scenarios:

- LLM prompt injection;
- network compromise;
- general-purpose compute compromise;
- sensor fault;
- communication loss;
- power loss;
- update tampering;
- replay attack;
- emergency stop; and
- input outside the observed distribution.

One failed or inconclusive test rejects the case. Any observed hazardous
actuation rejects the case. The expected and observed safe states must match
exactly.

## Assurance levels

The evaluator computes the level from evidence; the artifact cannot grant it
to itself:

| Level | Meaning |
|---|---|
| `simulation_only` | All mandatory scenarios were exercised in simulation. Useful for discovering hazards, never deployment evidence. |
| `evidence_ready` | Every mandatory scenario has non-simulation evidence such as bench or hardware-in-loop testing. |
| `independent_evidence_ready` | Every mandatory scenario has independent-assessment evidence with independent-assessor provenance. |
| `rejected` | Structure, integrity, coverage, barriers, evidence, or authority rules failed. |

None of these levels is a legal product-safety certificate. Independent
conformity assessment under applicable sector standards remains external to
CORE.

## Lifecycle invalidation

The safety case binds the exact release, deployment, safety policy, secure
boot evidence, signed-update evidence, credential policy, SBOM, and
vulnerability process. A change to a bound component invalidates the prior
assurance case. A new evaluation is required; a historical result cannot be
silently carried forward.

## Critical traceability

The assurance case requires an immutable external ledger for events that
change legal, irreversible, security, or safety understanding. At minimum it
records:

- safety policy changes;
- rejected hazardous commands;
- safety interlock activations;
- unexpected physical outcomes; and
- assurance invalidation.

Emergency stops and security-boundary breaches are also supported. Ordinary
telemetry is explicitly excluded so the ledger does not bury consequential
events in routine noise.

## Legacy compatibility

Some published generic `v1` schemas intentionally remain open for historical
replay compatibility. Rewriting those frozen schemas would change their
meaning. Strict executable evaluation closes their declared object shapes at
runtime and applies semantic invariants without changing historical bytes.
New contracts, including `PhysicalSafetyAssuranceCase.v1`, are closed with
`additionalProperties: false` at every declared object boundary.

## Commands

```bash
python scripts/evaluate_core_contract.py artifact.json
python scripts/audit_contract_executability.py
python -m pytest -q tests/test_executable_contracts.py \
  tests/test_physical_safety_assurance.py
```

All outputs are deterministic validation envelopes. They always state
`execution_authorized: false`; physical actuation belongs to a separately
engineered and independently assessed safety system.

## Reference baselines

The profile is designed to complement, not replace, established guidance:

- [NIST IR 8259A](https://csrc.nist.gov/pubs/ir/8259/a/final) for baseline IoT
  device cybersecurity capabilities;
- [NIST SP 800-218](https://csrc.nist.gov/pubs/sp/800/218/final) for secure
  software development practices;
- [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) for
  bounded AI risk management;
- [ISO 13849-1:2023](https://www.iso.org/standard/73481.html) for
  safety-related control-system design; and
- [IEC 61508](https://www.iec.ch/functional-safety) for functional safety.

Applicable legal and sector-specific requirements must be selected by the
responsible organization and independent assessor for the actual product and
deployment.
