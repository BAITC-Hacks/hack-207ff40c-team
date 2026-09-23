# Start here — Meeting Station

The application and Codex harness now share this repository root. Start with the
[README](README.md) for the product and [architecture](docs/ARCHITECTURE.md) for
component ownership. The actual Samruk-Kazyna case is recorded in `brief.json`;
`state.json` is already BUILD after the user's implementation request. The
activation-step deviation is recorded in [DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Continue this project

Read `AGENTS.md`, `brief.json`, `state.json` and `docs/HANDOFF.md`. Use the existing
React frontend, station API and local worker. [LOCAL_SETUP.md](docs/LOCAL_SETUP.md)
contains setup; [DEVELOPMENT.md](docs/DEVELOPMENT.md) describes the workflow.
From this directory:

```sh
make help
python3 scripts/harness.py doctor
make check
make verify
```

`make check` uses only the standard-library harness. `make verify` also needs the
installed application/test dependencies and test Chromium. It builds the frontend
and runs actual interface/export checks with labeled synthetic output; speech-model
accuracy is a separate acceptance task on provisioned hardware. No paid API or
cloud meeting-content inference is authorized.

## Future challenge / mode changes

For a new challenge, record the real text/source and rules rather than inferring
them. PREPARE permits research, inspection and authorized harness work only.
When explicit development authorization is available, the human runs the activation
command below unless that exact step has been explicitly delegated:

`python3 scripts/harness.py activate --confirm-rules --confirm-start`

Preserve the user's chosen direction. Use one decision card, test the deciding
assumption and complete one useful path. This delivery is submission-only; no
live demo is requested. Retain attribution, real check results and technical limits.

## Optional agents

Project .codex/ contains three read-only specialists: novelty_scout (user need/change),
feasibility_scout (smallest build), independent_reviewer (outcome and correctness).
They are available on demand; the primary integrates. Load changes in a new trusted
session; existing sessions can use the same task contracts. See docs/SPRINT.md for pacing.

Optional Ultra launch with a supporting selected model:
`codex -c 'model_reasoning_effort="ultra"'`
Specialists default to high effort. Model, account, sandbox and service tier stay unchanged.
Use the normal session if Ultra is unavailable. No global setup is required.

`harness.py status` shows brief/state. In BUILD, configure checks.json and run
`harness.py verify`; use `scripts/evaluate.py` for paired JSON adapter evaluations.
Windows: use `py -3` and `codex.cmd` as needed.
