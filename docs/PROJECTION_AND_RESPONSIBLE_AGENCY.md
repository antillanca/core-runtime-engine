# Projections, evidence sources, and responsible agency

CORE does not treat one observation as reality itself. An observation is a
projection produced by a source, a viewpoint, an instrument, and a moment.
The familiar visual analogy is useful: each eye receives a two-dimensional
projection; depth is reconstructed by reconciling perspectives, movement,
memory, and prior structure. The reconstruction can still be wrong.

The same discipline applies to rule evaluation:

1. Preserve each projection and its provenance.
2. Do not silently merge disagreement.
3. Require the rule's declared steps to emit typed results.
4. Reconstruct a conclusion only with an explicit deterministic procedure.
5. Keep uncertainty, missing views, and veto conditions visible.
6. Replay the same inputs to verify the same result.

`FrozenRuleSet.v1` therefore requires `evidence_is_projection: true`. This is
not a claim that every problem needs two sensors. It is a prohibition against
presenting one bounded view as complete ground truth.

## Evidence is broader than a human response

Current CORE contracts distinguish evidence production from accountable
authorization. A rule step may accept any declared combination of:

- `human`: an observation or response produced directly by a person;
- `nonhuman_biological`: an animal, plant, or other living-system signal;
- `software`: a bounded software or sensor output;
- `human_directed_software`: software operated with focused human direction;
- `mixed_ensemble`: several biological and/or software sources reconciled by
  an explicit procedure.

These categories describe provenance, not moral rank or legal personhood. An
animal's behavior can be relevant evidence. Software can calculate or detect.
A mixed group can be more informative than one observer. None of those facts
automatically grants authority to approve an irreversible action.

## Responsibility is a separate boundary

An approval is attributable to an `authorized_signer_set`. The signer may be
an individual wallet, a cooperative multisignature wallet, or another
accountable governance arrangement. Software may exercise only delegation
already bounded by a frozen rule. A biological signal or autonomous software
output remains evidence unless an accountable signer explicitly accepted a
different legal and operational arrangement.

This is why new contracts use `responsible_review` instead of assuming that
every useful response is a conventional human-only review. “Responsible” does
not remove people from the boundary: it names the party that can be audited,
can explain the mandate, and bears responsibility for the signature.

Historical schemas retain field names such as `human_approval_required` for
backward replay compatibility. Those frozen names must not be rewritten in
place. For new integrations, read them as a minimum responsible-person veto,
not as a claim that only humans can produce evidence or useful computation.

For catastrophic, irreversible, or poorly understood actions, automated
delegation never weakens an existing responsible-approval or veto requirement.
Uncertainty fails closed.

## Truth, demonstration, and observed limits

CORE never promotes an observation, average, consensus, record, or model
output into universal truth. It distinguishes:

- what was observed inside a declared reference class;
- what was inferred by a declared procedure; and
- what was demonstrated inside explicit axioms and a bounded model.

A demonstration is authoritative only for its stated proposition, assumptions,
inputs, verifier, and model. It does not prove that the model exhausts the
physical world. Empirical evidence remains a projection even when it is
repeatable.

Averages are especially weak at safety boundaries because they can erase tail
risk. CORE assurance artifacts preserve sample size, distribution context,
known extremes, provenance, and unobserved limitations. A record-breaking
observation updates the known envelope; it does not establish an impossible
limit beyond that record. Inputs outside the observed envelope are `unknown`
and fail closed when they can affect irreversible or catastrophic outcomes.

## Dignity to question

Technical expertise is not a prerequisite for standing. A person affected by
an automated system retains the right to receive a plain-language account,
inspect the evidence boundary, challenge the conclusion, refuse the action,
and use a local stop control. The system must answer a challenge with bounded
evidence or an explicit `unknown`; changing the subject is not a substitute
for an answer.

See [Executable contracts and physical safety assurance](EXECUTABLE_CONTRACTS_AND_PHYSICAL_SAFETY.md)
for the executable contract and its non-authority guarantees.
