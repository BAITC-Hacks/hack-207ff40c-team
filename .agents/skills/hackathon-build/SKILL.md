---
name: hackathon-build
description: Implement the chosen project incrementally with a baseline-first core experiment; BUILD mode only.
---

Confirm BUILD mode and explicit human authorization. Read the selected decision and handoff.
Define an input/output contract and independent correctness checker first. Keep one complete
user workflow. Run a small core-method spike before adding UI. Abandon or narrow the approach
when the method fails, the required data is unavailable, or integration consumes the time budget.
Implement baseline and proposed adapters over the same fixed cases. Add meaningful real product
test/build/smoke commands to checks.json. Configure and run the paired evaluator.
Use a simple local UI with clear provenance, errors and an honest replay mode. Preserve lockfiles.
Never replace actual computation with cached outputs in a demo marked live.
Update HANDOFF, EXPERIMENT and ATTRIBUTION with real command outputs and limitations.
