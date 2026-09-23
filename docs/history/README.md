# Retained application history

The canonical application is the root React frontend, Python station and Python
worker described in [ARCHITECTURE.md](../ARCHITECTURE.md). Existing source paths
remain in place so that earlier integrations can be improved later.

| Existing area | Role / reference |
| --- | --- |
| `cmd/`, `internal/`, `pkg/`, Go/Docker files | Inherited Scriberr host and CLI; [previous README](../PREVIOUS_README.md) |
| `deploy/`, station capture/controller code | Earlier Radxa/Caddy/browser deployment; [runbook](../RUNBOOK.md), [appliance architecture](../APPLIANCE_ARCHITECTURE.md) |
| `backend/`, `engine/`, `macos/` | Optional native client and model paths; [client architecture](../MEETINGBOX_ARCHITECTURE.md) |
| `web/project-site/`, static site material in `docs/` | Inherited project website, separate from the application |
| [Makefile.scriberr](Makefile.scriberr) | Original Go/site development targets, preserved for reference; paths assume invocation from the repository root |
| [workflows/](workflows/) | Original Go CI, Pages deployment and release definitions, archived outside GitHub's active workflow directory |

Only `.github/workflows/submission-checks.yml` is active for the canonical checks.
The archived release workflow disabled its tests and the website workflow would
publish on a push; neither represents this submission's verification or delivery.

The original product Git history, inactive worktrees, old binaries, unused corpus
audio and previous ZIP are preserved locally under
`.local/repository-migration-20260923/`. They are excluded from commits. The imported
product checkpoint was `fa15a850dd62cc87be94656e88196e022d4684f5`; the participant's
upstream baseline and license are recorded in [ATTRIBUTION.md](../ATTRIBUTION.md).
