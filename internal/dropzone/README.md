# Retained Go dropzone handoff

A file creation event does not mean recording has finished. The importer now waits
for an explicit completion marker. Close the audio file, calculate its byte length
and SHA-256, then atomically rename a temporary JSON file to `<audio>.ready`:

```json
{"bytes": 32044, "sha256": "<64 lowercase hexadecimal characters>", "handoff_id": "7c71e88b-9ce4-4f36-8e14-920f89a339dd"}
```

For `meeting.wav`, publish `meeting.wav.ready`. The importer validates the exact
copied bytes before creating a job. Missing/invalid markers and changed files stay
untouched. After acceptance it removes the matching marker, **retains the original
audio**, and exposes the imported job even when the transcription queue is full.
Clean up producer files explicitly after verifying their archive. A deterministic
job ID from the source path, content and optional `handoff_id` makes replaying the
same marker idempotent, including a crash before marker acknowledgement. The verified
archive and its directory are synced before database acceptance. Existing unattended
producers must adopt this close/hash/rename handoff.

Keep `handoff_id` unchanged when retrying a handoff. To intentionally import the
same file again, issue a **new UUID** in canonical `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
form; the all-zero UUID is invalid. Markers without this optional field retain
their original path/content identity. If that identity was deleted, replaying it
acknowledges and removes the marker without copying audio or restoring the deleted
job. A new `handoff_id` permits an intentional new import while preserving the old
deletion record. Invalid IDs or incomplete recordings retain their marker and source.
