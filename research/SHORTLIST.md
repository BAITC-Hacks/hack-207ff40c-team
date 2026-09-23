# Research shortlist

Checked 23 September 2026. Public specialist work, not secret or unpublished discoveries.
Product concepts below are proposed applications. They are not claims made by the papers.
No upstream repository was executed in this environment.

## nl2plan: NL2Plan: Robust LLM-Driven Planning from Minimal Text Descriptions

Date: 2024-05-07; revised 2025-10-01

Paper: https://arxiv.org/html/2405.04215v2

Author code: https://github.com/mrlab-ai/NL2Plan

Observed license: GPL-3.0

Status: adaptation candidate; original stack integration risk

Mechanism: Translate natural-language domain/problem descriptions into PDDL, then use a classical planner.

Possible build: A fixed-domain scheduling or resource-allocation assistant with editable constraints, a solver check, and explanations of infeasibility.

First experiment: Use typed JSON for one small domain and a constraint solver; do not reproduce the entire PDDL pipeline by default.

Baseline: Human-readable greedy assignment and, if budget allows, LLM-only output validated by the same checker.

Measure: constraint violations, feasible tasks solved, objective value on feasible tasks, latency.

Cautions: Solver guarantees only apply to the model actually encoded. The JSON/solver version is inspired by the paper, not a reproduction. Original repo recommends Docker/Linux/WSL and notes macOS untested. LLM access still required.

Local execution: not run

## riblt: Practical Rateless Set Reconciliation

Date: 2024-02-05; SIGCOMM August 2024

Paper: https://arxiv.org/abs/2402.02668

Author code: https://github.com/yangl1996/riblt

Observed license: MIT

Status: best non-LLM systems candidate; Go integration needed

Mechanism: Exchange coded symbols to discover the symmetric difference between two sets without first knowing its size.

Possible build: Offline inventory synchronization across two simulated branches over a throttled connection.

First experiment: Run the author example. Synchronize immutable versioned record hashes, then fetch missing payloads and verify full-set equality.

Baseline: Full snapshot transfer plus a sorted-hash-list difference baseline; add Merkle/log-based sync before broad efficiency claims.

Measure: total on-wire bytes including hashes and payloads, time until verified convergence, CPU time, recovery after interruption.

Cautions: Not a conflict-resolution algorithm, database, or secure transport. Mutations/deletions need a versioning and tombstone policy. A tiny app can have more overhead than a straightforward change log; measure crossover.

Local execution: not run: container could not resolve github.com for git clone

## egwalker: Collaborative Text Editing with Eg-walker: Better, Faster, Smaller

Date: 2024-09-21 preprint; EuroSys March 2025

Paper: https://arxiv.org/abs/2409.14252

Author code: https://github.com/josephg/egwalker-paper

Observed license: TypeScript reference package.json declares BSD-2-Clause; this is not a blanket license for all repository content. Retain/check the chosen component notices.

Status: usable TypeScript reference declared BSD-2-Clause; check integration and component notices first

Mechanism: Event-graph-based collaborative text editing that targets memory/loading and divergent-branch merging weaknesses.

Possible build: Offline-first incident notes: two users edit disconnected copies, reconnect, and see a converged text history.

First experiment: Use the TypeScript reference to test concurrent inserts/deletes on tiny traces; optimized benchmarks use a different implementation.

Baseline: Established collaborative-text library plus a clearly labeled last-write-wins failure example.

Measure: converged text equality, retained operations, load time, merge time, memory on comparable workloads.

Cautions: Reference-code speed is not evidence for optimized-paper performance. Convergent text can still have semantic contradictions; show them for review. Do not run the entire paper benchmark suite during the hackathon.

Local execution: not run

## bayesian-entropy: Hallucination Detection on a Budget: Efficient Bayesian Estimation of Semantic Entropy

Date: 2025-04-04; revised 2025-09-08

Paper: https://arxiv.org/abs/2504.03579

Author code: https://github.com/spotify-research/bayesian-semantic-entropy

Observed license: BSD-3-Clause-Clear

Status: laptop-friendly estimator experiments using precomputed outputs; live integration is extra work

Mechanism: Bayesian estimation of uncertainty over answer meanings, with adaptive allocation of additional answer samples.

Possible build: An evidence-triage interface that flags unstable answers and routes them to source review rather than asserting correctness.

First experiment: Reproduce a small precomputed estimator experiment, then use a tiny labeled domain dataset for live evaluation.

Baseline: Fixed sample-count semantic entropy at matched generation budget; single-answer/no-filter baseline.

Measure: AUROC on labeled errors, error versus coverage, samples per question, total latency and API cost.

Cautions: Consistent wrong answers can have low entropy. Existing laptop reproduction uses precomputed responses; fresh generation can require GPU/API resources. Inspect any pickle provenance before loading; never unpickle untrusted files. Prior fitting, semantic clustering, and test data must remain separated.

Local execution: not run

## evse: Evidential Semantic Entropy for LLM Uncertainty Quantification

Date: 2026-03

Paper: https://aclanthology.org/2026.eacl-long.334/

Author code: https://github.com/lucieK-J/EvidentialSemanticEntropy

Observed license: No license verified in reviewed repository root.

Status: newer specialist lead; not the default next-day code dependency

Mechanism: Represent uncertainty from both relationships among observed answer meanings and possible but unobserved meanings.

Possible build: A research comparison for uncertainty-aware evidence triage, not a claim to determine truth.

First experiment: Read the method and check a tiny worked example; copy code only after verifying reuse permission.

Baseline: Standard semantic entropy and the Bayesian estimator on the same labeled outputs.

Measure: AUROC on labeled errors, false-confidence rate, generation budget.

Cautions: Research code and model-generation requirements can consume the event. No verified license means code reuse remains unresolved. Method is not a universal hallucination detector.

Local execution: not run

## conformal: Conformal Risk Control; newer lead: Conformal Risk Control for Non-Monotonic Losses

Date: Original preprint 2022-08-04; ICLR 2024. Extension preprint 2026-02-23.

Paper: https://arxiv.org/abs/2208.02814

Author code: https://github.com/aangelopoulos/conformal-risk

Observed license: MIT for original repository; no extension implementation verified.

Status: original method usable if labeled calibration data already exists; new extension research-only

Mechanism: Choose a prediction-set parameter using calibration data to control expected bounded monotone loss under exchangeability; newer work relaxes monotonicity via algorithm-stability conditions.

Possible build: A service-request router that returns a small candidate set or asks a discriminating question when ambiguity remains.

First experiment: Keep training, calibration and test examples separate; calibrate the original monotone set-valued formulation.

Baseline: Uncalibrated top-1 and fixed-threshold prediction sets at comparable coverage or set size.

Measure: held-out target loss, mean prediction-set size, clarification rate, results under labeled distribution shift.

Cautions: This is not a per-person safety probability. Exchangeability, calibration size and loss assumptions matter. Do not imply the old code implements the 2026 extension. This field is established, not claimed to be globally unknown.

Local execution: not run
