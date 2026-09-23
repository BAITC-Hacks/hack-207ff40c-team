# README visuals

The four supplied artworks were organized here on 2026-09-23 without changing
their bytes. Their original filenames were:

| Repository file | Supplied file | Description |
| --- | --- | --- |
| `meet-box-wordmark.png` | `Дизайн без названия (1).png` | Participant-supplied MEET-BOX wordmark. |
| `samruk-kazyna-logo.jpg` | `thumb.jpg` | Case-owner identity, supplied by the participant. |
| `station-enclosure-concept.png` | `samruk_radxa_enclosure.png` | Concept render of the proposed station enclosure. |
| `station-turntable.gif` | `turntable.gif` | Animated enclosure visualization. |

The case-owner logo identifies the challenge. The enclosure images are design
concepts, not hardware test evidence, validated CAD or manufacturing drawings.
No new license for the supplied branding/artwork is inferred from the source-code
license; retain the applicable owners' rights and source attribution.

`01-import.png`, `02-transcript.png`, `03-review.png` and
`04-reviewed-minutes.png` are screenshots of the current application, captured
with the installed Playwright/Chromium against real loopback station/worker
services. The review image is a browser element screenshot of the complete review
panel. Other images capture the page. They were not generated or retouched.

Data comes from the explicitly synthetic `scripts/check-ui.py` acceptance seed.
The capture navigated the import/transcript/review interfaces, corrected the
assignee and date, saved review revision 1 and reloaded the persisted result.
The fixture intentionally includes an incorrect draft owner/deadline to exercise
correction. No audio recognition or language-model generation occurred; missing
model notices remain visible. No API responses were replaced, no existing user
archive was opened, and no external browser requests were made.

The [capture receipt](capture-receipt.json) records the steps, timestamp and scope.
Full product verification is recorded separately under `docs/verification/`.
