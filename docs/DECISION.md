# Provisional project comparison

Prepared 2026-09-23. Mode: PREPARE. The official challenge, rubric, prework permissions, team size and event duration are unknown. These are exactly three hypothetical directions, not interpretations of the official challenge. No product experiments have run; all numeric targets below are proposed decision thresholds, not results. User pain and willingness to adopt remain hypotheses requiring interviews.

Read: `research/catalog.json` and the `nl2plan`, `riblt`, and `egwalker` cards in `research/SHORTLIST.md`. Other catalog entries were screened out of this comparison because live uncertainty estimation adds model access and labeling requirements, while calibration-based routing needs representative labeled data we do not have.

## First experiments and critical risks

Refreshed after the Codex-only harness checks on 2026-09-23. These are plans for a later authorized BUILD session, not experiments performed during preparation. Run only the selected direction's first experiment. The larger evaluations below follow only if that initial test passes.

| Provisional direction | First falsifiable experiment | Immediate rejection condition | Critical risk |
|---|---|---|---|
| Volunteer shift repair | In a 60-minute core spike, use six hand-checked cases with four volunteers and three slots: ordinary, ambiguous, invalid, boundary, infeasible and cancellation. Compare greedy and bounded search against independently enumerated valid assignments. | Any invalid accepted roster, false infeasibility claim, or inability to distinguish ambiguous input from infeasibility. Passing only justifies the larger benefit test below. | An accurate solver can enforce the wrong rules; existing scheduling tools may already meet the need. |
| Interrupted inventory sync | After toolchain approval, allow 60 minutes to test two 1,000-event sets with ten differing events, once uninterrupted and once interrupted halfway. Include payload and verification traffic; compare sorted hashes and an available-cursor change log. | Any false completion or lost event; no byte saving over sorted hashes rejects the small-difference premise for this workload. Missing Go or an unworkable author example ends the spike. | Reconciliation does not resolve concurrent inventory actions; integration may cost more than a simple log. |
| Offline incident notes | After dependency approval, allow 60 minutes to replay six tiny two-replica traces: independent inserts, same-position inserts, overlapping deletes, duplicate delivery, Unicode edits and restart. Check both text equality and expected event retention. | Any divergence, silent lost event, corrupt Unicode or failed restart. Passing does not establish a performance advantage over Yjs. | Reference integration and durable history may dominate the event; semantic contradictions remain after convergence. |

For subsequent performance evaluation, choose the primary outcome before running the test (load time for the notes candidate; memory is secondary), freeze fixtures before tuning, and report failures. Sixty minutes is a proposed spike cap, not an assumed event duration. If dependencies cannot be used under the eventual rules, reconsider the candidate rather than installing them now.

## Comparison and provisional preference

Provisional rubric from AGENTS.md: user value 25%, theme fit 20%, build feasibility 20%, measurable differentiation 20%, demo clarity 15%. Ratings are subjective, 1–5. Theme fit is unknown for all three, so the totals below exclude it (maximum 4.00); do not read these as organizer scores or evidence of impact.

| Direction | User value | Theme fit | Feasibility | Differentiation | Demo | Known subtotal / 4.00 | Main blocker |
|---|---:|---|---:|---:|---:|---:|---|
| 1. Volunteer shift repair | 4 | Unknown | 4 | 3 | 5 | 3.15 | Useful constraint modeling and distinction from existing schedulers |
| 2. Interrupted inventory sync | 4 | Unknown | 2 | 4 | 4 | 2.80 | Go absent; benefit may disappear against a change log |
| 3. Offline incident notes | 3 | Unknown | 3 | 3 | 5 | 2.70 | Editor integration and reference-code performance |

Provisional preference: direction 1, conditional on an applicable brief. Its bounded, structured-input core can be tested on the installed Python runtime without requiring an LLM. Direction 2 has stronger systems differentiation but requires a missing toolchain and careful accounting. Direction 3 has a clear demonstration but convergence is already a mature capability and reference-code integration is uncertain. Neither alternative is permanently rejected. `state.json.selected_research_id` stays null until actual selection after the brief.

Three close existing tools reviewed before this preference:

- [Google OR-Tools employee scheduling](https://developers.google.com/optimization/scheduling/employee_scheduling) already demonstrates constraint-based staffing. Solver-backed assignment is not our invention; this is the credible existing-method comparator.
- [Timefold Employee Shift Scheduling](https://docs.timefold.ai/employee-shift-scheduling/latest/introduction) addresses shift assignment and constraints. We must validate that a narrowly scoped volunteer repair workflow adds value rather than merely rebuilding scheduling software.
- [When2meet](https://www.when2meet.com/) provides availability coordination. It is a workflow comparator for gathering availability, not evidence that it solves our proposed skill and repair constraints.

Abandon the preference if the official brief does not fit, permitted time cannot cover independent validation, the bounded experiment fails, or a coordinator finds an existing tool equally effective for the proposed task. No global novelty claim is justified.

## 1. Volunteer shift repair

**Specific user and costly problem.** A community food-distribution coordinator staffing a Saturday pickup with eight volunteers and six role/shift slots. A cancellation forces spreadsheet edits across availability, required training and overlapping shifts. Hypothesized costs: coordinator rework and an uncovered pickup station. Measure minutes and uncovered slots before claiming savings.

**Research mechanism.** [NL2Plan](https://arxiv.org/html/2405.04215v2) separates description/model construction from formal planning. Adapt that separation to a human-reviewed, typed constraint form and a bounded search over assignments. The initial structured-input implementation would be inspired by the paper, not a reproduction of natural-language-to-PDDL generation.

**Our contribution.** A narrow cancellation-repair workflow: show each encoded rule in plain language, retain the original roster where possible, identify conflicting requirements, obtain explicit human approval for a changed constraint, and export the repaired roster with a validation report. Do not silently relax hard constraints or imply solver validity proves the requirements are correct.

**Contract and data.** Input: synthetic volunteer IDs, availability, skill flags, slots, required skills, maximum assignments and prior roster in JSON. Output: validated assignments and changed-slot count, or invalid/unsupported/infeasible/timeout with reasons. For tiny cases, infeasibility requires exhaustive checking; a timeout is not a proof. After BUILD authorization, author 12 development and 24 frozen holdout cases (four each normal, ambiguous, invalid, boundary, infeasible, cancellation/recovery). No external data access is needed to create these synthetic fixtures; no real volunteer records are available or needed. A coordinator's later review would test realism separately.

**Small disproof experiment.** On at most eight volunteers and six slots, compare a most-constrained-slot-first greedy method with bounded exact search, using a separate exhaustive oracle/checker. Give both the same inputs and two-second per-case cap. Reject the core if it outputs any invalid roster, falsely calls a feasible task infeasible, solves fewer than 90% of feasible holdout tasks within the cap, or provides no improvement on repair count or feasible-task completion over greedy. Report all failures and timeout cases. Separately, test the explanation workflow with a coordinator: if correcting one deliberately wrong encoded rule is unclear, the human-review premise fails even if the solver passes.

**Baseline and measurable outcome.** Greedy is the simple baseline; OR-Tools CP-SAT with the same constraints and lexicographic objective (cover required slots, then minimize changes) is the credible existing method, only if installation is later permitted and compatible. Measure hard violations, feasible tasks solved / all feasible tasks, optimality gap on solved cases, changed assignments and latency. No solver-superiority claim without that comparator. A later counterbalanced usability pilot against a spreadsheet/template would target 30% lower median repair time without additional rule errors; the tiny pilot would not establish market impact.

**Risks and fallback.** Data: synthetic realism and incomplete rules. Licensing: [author code](https://github.com/mrlab-ai/NL2Plan) is marked GPL-3.0; no code copied and no exact commit selected. Review obligations before reuse. Compute: tiny enumeration grows exponentially; Python 3.14 package compatibility for CP-SAT is untested. Integration: original stack recommends Docker, is untested on macOS, and needs LLM access; none is assumed here. Budget is zero. Fall back to editable structured input and a small exact-search scope; label absent natural-language extraction. If scheduling adds no value beyond the baseline, stop this direction.

**90-second demonstration, planned.** 0–15s: show synthetic roster and cancellation. 15–30s: show a greedy repair leaving a qualified slot uncovered. 30–55s: inspect constraints and compute a validated minimal-change repair. 55–75s: load a held-out infeasible case, show its conflicting rules, explicitly approve one change and recompute. 75–90s: export the roster and show measured counts and the limitation that omitted rules are not checked. All displayed results must be real computation; any fixture input is labeled synthetic.

## 2. Interrupted inventory sync

**Specific user and costly problem.** A two-branch community tool-lending library manager reconnecting laptops after an outage. Repeated full inventory exports on a weak link delay reconciliation and leave staff unsure which updates arrived. Hypothesized costs: transfer time and manual verification; this does not assume a measured bandwidth problem at an actual organization.

**Research mechanism.** [Practical Rateless Set Reconciliation](https://arxiv.org/abs/2402.02668) discovers set differences through a stream of coded symbols without needing the difference size beforehand. The [author implementation](https://github.com/yangl1996/riblt) uses Go and is marked MIT. Reconcile immutable event/version hashes, then transfer missing payloads and verify equality.

**Our contribution.** A resumable inventory-event transfer workflow with complete byte accounting, explicit completion evidence and unresolved business conflicts surfaced for staff review. Set reconciliation is not conflict resolution. An event union alone does not determine whether two simultaneous loans of one tool are valid.

**Contract and data.** Input: two synthetic append-only event sets with unique IDs, version ancestry, deterministic encoding and tombstone events, plus a simulated network profile. Output: equal verified event-set digests, missing payload transfers, resumable session state and a separate list of conflicting inventory actions. Generate synthetic records without external data only after BUILD authorization; no private inventory data or downloaded dataset needed. Keep tombstones for the entire experiment and define garbage collection as out of scope.

**Small disproof experiment.** After permission for dependencies and a Go toolchain, smoke-test the author example. Then freeze 18 workload cells: 1,000/10,000 records × 0.1%/1%/10% differences × uninterrupted/drop at 25%/drop at 75%; repeat each with five seeds, equal 256-byte event payloads and the same 64-kbit/s, 100-ms RTT link. Include empty/identical sets, duplicate delivery, malformed symbols, deletions and concurrent same-item edits as correctness cases. Reject on any lost event, undetected unequal completion, unbounded decode retry, or failure to recover. Reject the bandwidth premise if total traffic at ≤1% differences is not at least 30% lower than sorted hashes. If an available change log wins, narrow the claim to lost-cursor/no-shared-history recovery or abandon it.

**Baseline and measurable outcome.** Full snapshot and sorted-hash-list reconciliation, plus an append-only change log with acknowledged cursor when history is available. Same records, serialization, compression setting and interruption schedule for all. Count protocol headers, retries, hashes, reconciliation symbols, payloads and final verification in on-wire bytes; measure time to verified convergence, CPU time, peak memory and recovery success / all runs. A Merkle-based comparator is required before broad sync-efficiency claims. Report crossover by difference size, not just the favorable example.

**Risks and fallback.** Data: synthetic event patterns may flatter the algorithm. Licensing: MIT observed, exact commit/notices still need pinning. Compute: Go is absent; no installation is allowed during preparation. Integration: payload fetching, deterministic hashing, bounded decoder behavior, persistence and restart semantics remain untested. The raw go.mod lookup failed in this review; dependency versions remain unverified. Large divergence may make snapshots cheaper. A fallback sorted-hash synchronizer can demonstrate the workflow but must be labeled as dropping the research mechanism; it cannot count as proof of RIBLT's benefit.

**90-second demonstration, planned.** 0–15s: show two synthetic inventories with a small unknown divergence. 15–35s: start snapshot and proposed transfers under the same visibly simulated link. 35–55s: interrupt and reconnect, showing cumulative real byte counters. 55–75s: verify final event-set equality and display one concurrent-loan conflict requiring review. 75–90s: show a held-out high-divergence result where the benefit shrinks or disappears. Convergence is not presented as business-level correctness.

## 3. Offline incident notes

**Specific user and costly problem.** Two venue operations stewards recording non-sensitive equipment incidents on disconnected laptops. Replacing one report with the latest file loses another steward's additions; manual merging delays the next shift's handoff. No real incident records are used.

**Research mechanism.** [Eg-walker](https://arxiv.org/abs/2409.14252) uses an event graph for collaborative text histories and divergent-branch merging. The [author repository](https://github.com/josephg/egwalker-paper) includes a TypeScript reference distinct from the optimized benchmark implementation.

**Our contribution.** A two-steward note workflow showing what each person contributed, reconnection status, explicit review of contradictory statements and an export containing the merged text and history. Converged strings can still disagree semantically; we would not claim automated truth or contradiction resolution.

**Contract and data.** Input: synthetic plain-text notes and two causally valid insert/delete histories with unique event IDs. Output: identical merged text at both replicas, durable history and clear review state. Generate 12 development traces and 24 frozen holdout traces covering six categories: ordinary edits, concurrent same-position edits, duplicate/invalid delivery, Unicode boundaries, long divergence, and reconnect/restart. Data is authorable without downloads; real-world incident semantics remain unvalidated.

**Small disproof experiment.** After BUILD permission, test the reference with tiny traces before UI integration. Reject on any replica divergence or silent event loss after replay/restart. Then compare 100, 1,000 and 10,000-operation histories against Yjs on identical text-level edits, including concurrent deletes and Unicode, with equivalent persistence/encoding boundaries. A retained insertion need not remain visible if legitimately deleted: compare event history and expected merged semantics, not a naive count of visible words. Reject performance differentiation unless it yields at least 20% improvement in measured load time without merge latency exceeding 500 ms at 10,000 operations; report run variance. If correctness passes but performance does not, assess workflow value separately without claiming the paper's speedups.

**Baseline and measurable outcome.** Established Yjs collaborative text is the credible comparator; last-write-wins is only an illustrative failure baseline. Measure replica equality / all traces, accounted-for operations, restart success, serialized history bytes, load/merge latency and memory using the same runtime/workloads. Any user benefit needs a separate comparison of handoff review time and missed facts with ordinary file merging.

**Risks and fallback.** Data: synthetic editing lacks realistic long histories. Licensing: the [reference package manifest](https://raw.githubusercontent.com/josephg/egwalker-paper/master/eg-walker-reference/package.json) declares BSD-2-Clause; this is not blanket permission for the repository. Exact component notices, dependencies, commit and Yjs license must be checked before reuse. Compute: Node is present, but TypeScript dependencies and browser bundling are untested; Rust is absent. Integration: Unicode positions, undo, cursor mapping and persistence can dominate the event. Fall back to a plain-text two-pane editor; if the research component fails, Yjs-only is a workflow fallback with no Eg-walker claim.

**90-second demonstration, planned.** 0–15s: two synthetic copies of a venue note. 15–35s: disconnect and edit both, showing the last-write-wins loss example. 35–55s: reconnect and compute a shared text/history. 55–75s: replay a held-out overlapping-delete trace and restart one replica to show recovery. 75–90s: display equal text, actual timings and a contradictory pair of statements that still needs human review.

## Evidence boundaries and next gate

Sources above were read on 2026-09-23. Catalog license observations are leads, not pinned dependency approvals. No upstream repository was cloned or executed, no model/data/dependency was installed, and no product benchmark was run. Exact commits remain unselected. Planned fixtures are not created and evaluation adapters remain unconfigured. The existing historical catalog note about a failed RIBLT clone is not a failure observed on this Mac.

The next action is to obtain the official challenge and rules, then revisit these three candidates against them. Only explicit human authorization can activate BUILD. Preparation ends with this report.
