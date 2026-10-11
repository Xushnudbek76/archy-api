# Recordings

Recordings belong to a course and inherit its account ownership. There is no audio duration
limit or product file-size limit. Physical disk capacity still applies; admission checks for
space to store the chunks and assembled file. This check is not a reservation across uploads.

## HTTP contracts

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/v1/uploads?page=1` | Owner's unfinished uploads, 20 per page |
| POST | `/v1/uploads` | Admit an upload with a client UUID, courseId, title, fileName, sizeBytes and SHA-256 |
| GET | `/v1/uploads/{id}` | Current persisted offset, status and recording if accepted |
| PATCH | `/v1/uploads/{id}/chunks` | Binary chunk up to 4 MiB with `Upload-Offset` |
| POST | `/v1/uploads/{id}/complete` | Verify bytes and audio, then save a recording |
| POST | `/v1/uploads/{id}/cancel` | Discard an unfinished upload |
| GET | `/v1/recordings?page=1` | Owner's saved recordings, 20 per page |
| GET / HEAD | `/v1/recordings/{id}/audio` | Private playback with single byte-range support |

Session authentication protects every endpoint. Writes also require CSRF. Foreign IDs return
404. Repeated admission with identical metadata, repeated confirmed chunks and completion are
idempotent. Changed metadata or an unexpected offset returns 409. Reselecting the original file
allows the browser to verify its hash and resume from the server's confirmed offset.

PyAV checks the actual audio container and first decoded frame in a bounded subprocess.
Supported containers are MP3, M4A, WAV, FLAC, Ogg and WebM. Duration can be unknown; the API
returns null rather than rejecting it. This is an audio admission check, not a complete decode
of every frame. Unsupported media and checksum mismatches end the upload with a safe error.

## Private storage

`RECORDING_STORAGE_ROOT` defaults to `.local/media`. It must be a private directory on one
persistent server volume, outside public/static media paths. Only generated UUIDs determine
paths. Files use restrictive permissions; playback reads through owner-checked Django routes.
Chunks are saved atomically before their database offset advances. Assembly streams the checksum
with bounded memory. An interrupted completion reuses its existing assembled file, and saved
recordings are published before their database transaction commits.

Use a WSGI server for this version. Playback has a synchronous file iterator; ASGI deployment
needs an async streaming adapter before it is supported for long recordings. Next forwards the
stream and range headers without buffering the whole recording.

Back up both PostgreSQL and the storage volume. Restarting the application preserves uploads;
replacing the volume does not. Cancelled/completed upload parts are removed after commit.
Abandoned uploads and files left by failed database commits need an operational cleanup job
before public launch. There is currently no retention policy or automatic deletion.

`LocalRecordingStorage` owns disk operations, keeping a later object-storage migration focused.
Multiple backend replicas would need shared storage or a different storage implementation.
