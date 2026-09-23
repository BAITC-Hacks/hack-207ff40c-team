# Fixed review acceptance cases

Synthetic cases fixed 2026-09-23 before review acceptance runs. Baseline: upstream 849f222 has no review endpoint.

1. Map SPEAKER_00 to Айдана; raw cluster ID and transcript text remain unchanged.
2. Correct action owner Тимур and date 2026-09-28; mark human confirmation, not automated verification.
3. Repeat identical request after lost acknowledgement; revision and audit stay unchanged.
4. Another client saves an outdated revision; conflict, no overwrite.
5. Reuse request ID for different data; conflict, no overwrite.
6. Unknown speaker/action, duplicate item or whitespace task; reject with no partial changes.
7. Reject an action; regenerated summary and calendar exclude it, reports retain rejected evidence.
8. Export rendering fails; previous result and exports remain readable.
9. Restart worker; latest revision, audit and original result remain readable.
10. Station downloads interrupted; cached previous revision remains intact and identical retry can finish.
11. Unauthenticated edits rejected before body parsing.
12. Review DOCX/PDF/JSON/CSV/ICS all refer to the same saved revision.

These check software behavior on supplied synthetic outputs, not ASR or model accuracy.
