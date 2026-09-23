# Paired evaluation contract
Configure evals/config.json only after choosing and building a real product.
Each argv command starts one adapter process per case. It reads one JSON value from
stdin and writes one JSON value to stdout. Debug logs go to stderr. No markdown fences.
Use {python} in argv for the interpreter currently running the evaluator.

Add JSONL cases with unique IDs, explicit externally established expectations, and categories:

```json
{"id":"example-format-only","category":"normal","input":{"request":"..."},"expected":{"result.status":"feasible"}}
```

This example is FORMAT ONLY, not a useful benchmark or a runnable product case.
Expected keys are dot-separated object paths, optionally traversing list indexes.
The comparator uses exact, type-sensitive JSON equality. For numeric tolerance, complex
constraint verification, statistical scoring or semantic equivalence, implement an independent
trusted checker/quality command; do not force those tasks into approximate string comparison.
Adapters should expose actual results, not self-rated correctness. A expected `valid: true`
field is not independent verification unless the adapter wraps a separate trusted checker.

Both commands receive identical inputs. Freeze cases before tuning. Keep normal and difficult
cases, including ones expected to defeat our approach. The evaluator records pass/fail,
process error/timeout, output, process wall time and a cases SHA-256. It includes failed
cases in denominators and returns nonzero for proposed failures or baseline execution errors.
Baseline wrong answers count as comparison outcomes, not tool-execution errors.
A zero exit code does not imply a statistically significant improvement over the baseline.

Run `python3 scripts/evaluate.py`. Outputs go to reports/evaluation-<unique timestamp>.json
and .md. No results are invented for missing commands or empty case files.
Fresh per-case processes make timings cold-start timings, not sustained throughput or UI latency.
Command budgets are timeouts, not monetary enforcement; keep external APIs behind explicit
human-approved caps and count their calls/cost separately.
