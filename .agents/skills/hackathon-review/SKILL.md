---
name: hackathon-review
description: Independently challenge implementation, novelty claims, evaluations and the final demo; use after a build chunk.
---

Review rather than flatter the builder. Check theme fit, constraints, data leakage, license
status, cost, security assumptions and any claim that exceeds the evidence. Inspect code and
exercise the user path. Run `python3 scripts/harness.py verify` and `python3 scripts/evaluate.py`
only after reviewing their configured commands. Report actual exit codes and raw report paths.
Test empty, malformed, boundary, conflicting and interrupted cases. Check that failed runs remain
in the denominator and that baseline implementation is not sabotaged. A polished screen is not
an end-to-end computation. Never waive a failing check just to mark the product ready.
Finish docs/DEMO.md and HANDOFF; separate proven behavior, prototype assumptions and future work.
