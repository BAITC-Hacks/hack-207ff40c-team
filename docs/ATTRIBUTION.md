# Source and reuse record

## README identity and visual evidence

The participant supplied the MEET-BOX wordmark, Samruk-Kazyna logo, enclosure
concept render and rotating enclosure GIF on 2026-09-23. Their unmodified files
and original filenames are recorded in [README visual provenance](assets/readme/README.md).
Samruk-Kazyna identifies the challenge owner; the enclosure artwork represents a
concept. The four interface screenshots show the current application against
explicitly synthetic acceptance data, with real local requests and no model
inference. They are separate from the enclosure illustrations and speech-quality
evidence. No new artwork license or third-party endorsement is claimed.

The September 23 README refresh adds three original SVG illustrations for the
product introduction, local architecture and appliance security. They use no
external assets or runtime dependencies. Design references and the distinction
between illustrations and real screenshots are in the visual provenance record.

## Existing application

Cloned on 2026-09-23 from
[Eraly-ml/meeting-intelligence](https://github.com/Eraly-ml/meeting-intelligence),
baseline commit `849f2224f93209feb9ce408f4ebd898026a9c97d`.
The participant identifies it as their previous hackathon work. Its local
station/worker, React interface, inference adapters, evidence extraction,
appliance capture, security controls and existing tests predate this improvement.
The root [MIT license](../LICENSE), copyright 2025 Scriberr, is retained.
Original Scriberr components and previous modifications are not claimed as new.

## Current contribution

- Revisioned secretary review, explicit speaker-name mapping, corrected
  assignments/deadlines and recovery of omitted tasks from cited passages;
  original transcript words and citation IDs retained.
- Full chronological context and all factual fields in the semantic review
  request, with explicit unavailable status when verification cannot complete.
- Unicode DOCX generation using Python standard-library OOXML/ZIP, plus coherent
  export bundles and stable per-job calendar identities.
- Standalone loopback hosting and dependency/model setup instructions, preserving
  existing API authorization and separate worker credentials.
- Regression and real browser checks of these paths using synthetic data.

No new ASR, diarization or language-model algorithm is claimed. No measured
100x improvement, real-user time saving, production-readiness certification or
global novelty claim is made.

## Dependencies and model assets

The foundation repairs add no model algorithm or borrowed implementation.
Go 1.24.4 and the modules already pinned in `go.mod`/`go.sum` were provisioned
locally for compilation and race checks; their binaries/cache remain outside Git.
The retained Voxtral adapter now checks the exact processor/tokenizer API versions
documented with primary source links in its [adapter notes](../internal/transcription/adapters/py/README.md).
Those optional ML packages were inspected, not installed or run with weights.

Python package versions used for core checks are in
[requirements/validation.lock](../requirements/validation.lock); frontend versions
and integrity hashes are in [package-lock.json](../web/frontend/package-lock.json).
Playwright 1.63.0 was added for development checks; its browser binary is kept
outside Git. [Official Playwright library guidance](https://playwright.dev/docs/library)
informed browser testing. DOCX export adds no runtime dependency.

Model software, weight sources, licenses, checked revisions/digests and unresolved
pins are recorded in [MODEL_SETUP.md](MODEL_SETUP.md). These sources were inspected;
no speech, diarization or language-model weights were downloaded or executed in
this workspace. No model/font weights are bundled in the source submission.
Retain each component's applicable license and notices during provisioning.
The small Playwright-provided ffmpeg download belongs to browser testing; it is
not a provisioned or tested ASR decoder.

Test recordings were not supplied by the participant. Current acceptance fixtures
are visibly synthetic text/structured output. No customer recordings, credentials
or private meeting content were used. Reviewer names in fixtures are synthetic.
The inherited repository included an AMI-labelled English corpus excerpt named
`tests/data/AMI-Corpus-IB4002.Mix-Headset-clip.wav`; it was not used by these checks
and is preserved only in the ignored local migration backup. The [AMI project source page](https://groups.inf.ed.ac.uk/ami/corpus/)
describes its public recordings and attribution license; the inherited excerpt's
exact provenance was not independently established here.

## Repository consolidation

The product source from checkpoint `fa15a850dd62cc87be94656e88196e022d4684f5`
was moved into this existing harness repository on 2026-09-23. Module source paths
remain unchanged relative to the application root. The prior Git history is
preserved in a local bundle; the root repository's own Git history remains intact.
Historical release/site workflows are retained under `docs/history/workflows/`.
The active workflow checks the canonical application and harness together.
