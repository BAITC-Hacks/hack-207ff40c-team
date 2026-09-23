# Selected direction: improve the existing Meeting Station

The actual Samruk-Kazyna meeting-minutes case arrived on 2026-09-23. The user
explicitly selected their earlier project, asked to clone and improve it, and
confirmed five hours and submission-only delivery. This supersedes the three
pre-brief provisional options. Source: `brief.json` and
[the recorded case](CHALLENGE.md).

- **Person:** a meeting secretary recording Russian, Kazakh and mixed discussion;
  managers subsequently depend on the resulting owners and deadlines.
- **Before → after:** an automatically generated report can contain an anonymous
  voice or stale owner/date with no correction workflow. The secretary can now
  name the voice, check its source, correct/confirm/reject the assignment, recover
  an omitted task from its transcript passage and distribute a consistent saved
  revision with an audit history.
- **Evidence:** the organizer-provided problem is user-supplied case evidence;
  no end-user interviews or measured labor saving are claimed. Source inspection
  of baseline `849f222` found a substantial local pipeline but no canonical human
  review API/UI, no DOCX export and no standalone UI launch without appliance/Go.
- **Closest alternative:** the team's same earlier application and manual Word
  editing. Reuse it; avoid spending the event rebuilding ASR or changing stacks.
- **Contribution:** reviewable, revisioned minutes; stronger chronological verifier
  context; consistent Unicode exports; single-machine reproducibility. Published
  Whisper/Sherpa/Qwen methods and earlier application are attributed.
- **First test:** supplied synthetic report with a corrected owner/date; identify
  voices, save a review, restart/reload and inspect actual PDF/DOCX/structured
  exports. Reject the change if it invents identity, loses citations, lets a stale
  save overwrite another user or serves a mixture of export revisions.
- **Smallest delivery path:** existing React + station + worker, local models only,
  SQLite/files, bounded inference and one complete import/review/export workflow.
- **Critical boundary:** current hardware has no provisioned speech/diarization/LLM
  assets. Transport/UI checks cannot prove Russian/Kazakh/code-switch accuracy.
  Provide precise provisioning and acceptance instructions, retain missing-model
  warnings, and make no production-ready or 100x performance claim.

Rubric: 25 functionality, 25 technical implementation, 25 README/reproducibility,
15 applicability, 10 originality. This prioritizes a reliable required workflow
and a reproducible submission over optional dashboards, ECM or research churn.
No live demo is required by the user's clarification.
