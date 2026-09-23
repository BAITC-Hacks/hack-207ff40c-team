# Start here

This is preparation tooling, not a completed hackathon product.
No API key, paid service, model download, or extra Python package is needed to run it.
Python 3.10+ is required. A logged-in coding CLI is needed only to use an agent.

## Tonight / before the brief
Keep state.json in prepare mode. Do not infer event rules or a hardware ban.
Run `python3 scripts/harness.py doctor`, `python3 scripts/harness.py check`, and
`python3 -m unittest discover -s tests -v` from this directory.
A structural check passing means the HARNESS is intact, not the product is correct.

Paste into your installed Codex session:

Read AGENTS.md and START_HERE.md. Stay in PREPARE mode. Run the harness checks,
inspect the available local toolchain without installing anything, and read the research
catalog. Put three provisional directions, their critical risks and their first falsifiable
experiments in docs/DECISION.md. Do not invent the official brief, implement submission
code, download dependencies/models, or enable paid APIs. Update docs/HANDOFF.md.
Stop after the preparation report.

## When the official challenge is announced
Fill challenge_text and rules_source in brief.json with the real instructions, along
with any known rubric, mandatory technology and API budget. Preserve the quoted source.
Only the human should run the next command, after confirming development may begin:

`python3 scripts/harness.py activate --confirm-rules --confirm-start`

Paste into the CLI:

Read the updated brief.json and state.json. Use the hackathon-select skill. Compare three
brief-specific candidates and choose one. Build the smallest measurable core experiment
before any dashboard. Then implement one complete user workflow, real product checks,
baseline/proposed evaluation adapters and a 90-second demonstration. Respect the approved
budget and scope. Record failures and attribution. Do not weaken tests to claim success.

## Useful commands
- `python3 scripts/harness.py doctor`: inspect tool availability, not credentials.
- `python3 scripts/harness.py check`: validate this harness and Codex skills.
- `python3 scripts/harness.py status`: show current state and official brief.
- `python3 scripts/harness.py snapshot`: write a current file-hash manifest, excluding generated/vendor/private files.
- `python3 scripts/harness.py verify`: run configured product tests, build and smoke checks. Empty config fails.
- `python3 scripts/evaluate.py`: run paired baseline/proposed cases. Empty config fails.

On Windows substitute `py -3` for `python3`. Use `codex.cmd` when PowerShell blocks codex.ps1;
otherwise use your normal `codex` command. Do not change execution policy globally.
Agent prompts are guidance. Activation flags do not prevent arbitrary file edits or enforce
an organizer's rules. Ordinary CLI permissions remain the actual execution boundary.
