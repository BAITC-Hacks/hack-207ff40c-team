# Coverage of the supplied Samruk-Kazyna case

This matrix replaces the earlier event rubric. Source and weights:
[CHALLENGE.md](CHALLENGE.md). **Implemented is not the same as verified on real
multilingual recordings.** Current acceptance evidence is listed in
[SUBMISSION_NOTES.md](SUBMISSION_NOTES.md).

| Requirement | Implementation | Evidence / remaining boundary |
| --- | --- | --- |
| Russian speech recognition | Local multilingual Whisper adapter and explicit `ru` mode | Adapter contracts tested; current audio accuracy unmeasured |
| Kazakh speech recognition | Same adapter, `kk` mode, Unicode throughout | Current Kazakh recordings not run |
| Mixed RU/KZ speech | `kk_ru` uses multilingual recognition with automatic language detection | Code-switching quality unmeasured; no guarantee from a language selector |
| Speaker separation | Local Sherpa ONNX segmentation and embedding, bounded turn alignment | Synthetic turn/overlap tests; real diarization quality unmeasured; local assets required |
| Assignments tied to people | Extracted owner plus evidence/voice ID; secretary can name voices and confirm/correct owner | Real browser and API correction tests; names are human mappings, not voice biometrics |
| Tasks, owners, deadlines | Local structured extraction, same-task deadline checks, full chronology in verifier; secretary can add a missed task from immutable source passages | Frozen adversarial transport fixtures and real browser recovery from an empty extraction; model judgment accuracy still requires evaluation |
| Summary | Derived from reviewed/source-supported findings; refreshed after edits | Tests reject stale/rejected facts in summary; completeness is not guaranteed |
| PDF/DOCX export | Both, plus CSV/JSON/ICS, Unicode and source/review labels | Actual browser downloads and independent document-content checks passed |
| Audio/video file input | MP3/WAV/M4A/WebM/CAF/OGG/FLAC/MP4/MKV, local ffmpeg audio extraction | Upload contracts tested; this environment did not execute ffmpeg codecs |
| Teams/Zoom/Meet participant | Existing separate appliance browser/controller, host admission limits | Controller tests retained; live meeting joins not revalidated in this workspace |
| Privacy / local deployment | Loopback-only standalone host, distinct tokens; mutual TLS for LAN worker; no cloud inference fallback | Authorization, TLS and routing tests; browser path checked; full WAN-disconnect inference untested |
| Participant notice | Recording/import UI instructions; appliance joins visibly as recording participant | Human organizer must notify participants; no claim of automatic consent enforcement |
| Upcoming/overdue reminders | ICS task export only | Automatic scheduled notifications are not implemented; ICS is not claimed to send reminders |
| Task status dashboard / SED / voice biometrics | Outside current improvements | Not represented as completed features |

## Judging priorities

- Functionality and case fit: 25 points. Main path is import → local processing →
  source review → corrected minutes and exports; model acceptance remains open.
- Technical implementation: 25. Existing local inference architecture, strict
  provenance separation, durable revision publication and recovery.
- README and reproducibility: 25. One-machine launch, pinned core packages,
  model-provisioning sources, executable checks and visible incomplete setup.
- Value and applicability: 15. Secretary can resolve ambiguous owners/deadlines
  and distribute a consistent reviewed version. No measured labor-saving claim.
- Development potential/originality: 10. Contribution is the source-linked,
  correctable task workflow under local-data constraints. Existing algorithms and
  earlier application are attributed; global novelty is not claimed.

## Required next acceptance on provisioned hardware

Use fixed consented/synthetic multi-speaker Russian, Kazakh and mixed recordings
with a human transcript, speaker roster and expected tasks. Include corrected
owners/dates, unassigned tasks, overlapping voices, conditional/cancelled tasks
and no-task meetings. Report WER per language, diarization errors and owner/date
precision/recall with failures retained. Inspect downloaded PDF/DOCX. Repeat with
external networking disconnected and record actual model hashes, memory and
runtime. The present synthetic browser/transport checks cannot establish these
results or production readiness.
