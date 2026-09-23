# Hackathon working agreement

Read brief.json, state.json and docs/HANDOFF.md first. START_HERE.md explains setup.
The central question is: **Who needs this, and what changes for them because it exists?**

The selected application now lives directly in this repository root: `web/frontend/`,
`station/` and `mac-worker/`. Read `docs/ARCHITECTURE.md` for ownership and boundaries.
Use `checks.json` / `make verify` from this root; do not create a nested product clone.
The retained Go/appliance/native paths are mapped in `docs/history/README.md`.

## Intent and scope

Start with a specific person, situation and costly obstacle. State the before/after
change in their task or capability. Evidence can be observed, reported or a clearly
labeled hypothesis. Never invent demand, interviews, organizer rules or results.

For this project, prioritize a meaningful improvement over what that user can practically
do today. Familiar technology can enable innovation through access, cost or workflow.
Verify the barrier and our contribution. A new audience label, complicated stack or
obscure paper alone establishes no improvement. Attribute inherited work; substantiate
technical originality separately when claimed or required by the actual event rubric.

## Modes

PREPARE: research, tool inspection and authorized harness improvements only. No submission
code, product experiments, upstream execution, dependency/model/data downloads or paid APIs.
BUILD: requires the real brief and explicit human confirmation that development may begin.
Only the human runs `python3 scripts/harness.py activate --confirm-rules --confirm-start`
unless they explicitly instruct otherwise. Improving the harness does not activate BUILD.
Keep normal sandbox/approval settings; these instructions are not a security boundary.

## Decide, test, deliver

When choosing from scratch, compare three short options and choose one after the brief;
preserve an explicitly chosen direction. Use hackathon-select and one decision card in
`docs/DECISION.md`: person, before/after, evidence/closest alternative, our contribution,
first falsifiable test, smallest delivery path and critical risk. No separate form, weighted
score or competitor quota. Research only until it resolves the deciding uncertainty.
Load the catalog only when a mechanism is needed. Skills hold the detailed workflow.

In BUILD, test the riskiest assumption promptly, normally within 30 minutes. Compare the
proposed workflow with the closest usable current workflow on the same task; check
results independently. Narrow or stop if
correctness or the promised change fails. User access being unavailable means demand
remains a hypothesis; it need not prevent a clearly labeled technical prototype.

Build one input -> computation -> useful result/action -> export path. Reuse the stack
and familiar components. Add work only if it delivers or verifies the promised outcome.
Check critical dependencies/data/reuse permissions before relying on them. No unneeded
platforms, model training, infrastructure, refactors, tests or process artifacts.
The user has five hours; count actual elapsed time and protect checking/demo time.
`docs/SPRINT.md` is a flexible time guide, not a minute-by-minute approval gate.

## Work and evidence

One integrator owns shared edits. Use a specialist only for a decision-changing question
that can run independently; at most three children, no recursive teams. Default task:
5 minutes, 200 words, one recommendation. No automatic three-agent launch. Read-only roles
return reproduction steps; the integrator runs mutating checks. Parallel implementation
requires disjoint worktrees and explicit contracts. Keep the selected available model.

Keep a small fixed case set before tuning, record its hash, include failures, and compare
fairly with the closest usable alternative. Add component ablations only for causal method
claims. Report runtime/bytes/model costs only when actually measured; label modeled values.
Exercise the real interface and export before calling a path complete. Do not substitute
mock tests or paper benchmarks for that evidence. Preserve relevant limits and error cases.

Use primary sources, inspect reused code/licenses, pin what is used and retain notices in
`docs/ATTRIBUTION.md`. Keep secrets out of logs; no real private customer/patient data,
automatic publishing or paid calls without an approved budget. Label synthetic/replay data.

## Checks and handoff

Harness: `python3 scripts/harness.py doctor`, `python3 scripts/harness.py check`,
`python3 -m unittest discover -s tests -v`. These do not validate a future product.
BUILD: configure meaningful test/build/smoke commands in checks.json and run
`python3 scripts/harness.py verify`. Use scripts/evaluate.py for compatible paired
JSON adapters; it measures cold process time and has per-case, not whole-run, timeouts.
Budget the whole run and verify the preregistered case hash yourself.

Keep only the useful record: DECISION for the choice, EXPERIMENT for actual evidence,
ATTRIBUTION for reuse, DEMO for the before/after story, HANDOFF for current state,
changed files, last checks and next action. Update when information changes; do not
repeat reports or require a new sign-off for work already authorized.
