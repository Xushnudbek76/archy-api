# Lecture processing

New accepted uploads with a non-null duration-policy snapshot enqueue one processing job in the same PostgreSQL transaction as the recording. Existing recordings are not backfilled. Uncapped legacy uploads can still finish and play; their processing status is `unavailable`.

The API stores jobs; a separate worker prepares private audio, transcribes it with Groq `whisper-large-v3-turbo`, and summarizes with `openai/gpt-oss-120b`. Korean and English are supported. The predominant detected language determines the notes language. Unsupported languages fail processing while preserving the original audio.

## Enable the worker

The default provider is disabled outside tests. Set these values in the private backend `.env` after confirming the Groq account is on the Free plan:

```dotenv
AI_BACKEND=groq
GROQ_API_KEY=your-private-key
PROCESSING_WORKERS=1
DATABASE_CONNECTION_BUDGET=9
```

Restart the API after changing its configuration, then start the worker from the backend directory:

```sh
.venv-fastapi/bin/python -m scripts.run_worker
```

Keep API and worker on the same persistent private media volume. Run one processing worker, with two database connections and zero overflow. Budget validation includes all configured API processes: `UVICORN_WORKERS * 5 + PROCESSING_WORKERS * 2 + 2`. Review provider pool limits before increasing API processes. A local file lock prevents two worker commands using the same media root.

There is no automatic provider/model fallback or billing upgrade. Account billing is controlled by Groq, not this application. Account quotas remain authoritative; other applications using that account share them.

## Bounds and recovery

- Jobs snapshot their processing settings. Audio targets 300-second, 16 kHz mono FLAC segments. Every encoded file must fit the actual configured byte cap (default 8 MiB); oversized files are split and encoded again.
- Preparation runs in a child process: default 120 CPU seconds, 180 wall seconds, a monitored 768 MiB RSS ceiling, and a 64 MiB per-file limit. Decoded PCM is capped at 48 MiB. These processing bounds do not alter upload acceptance; raising upload duration limits later requires reviewing processing budgets too.
- Provider requests run in timed child processes with a default 180-second wall deadline and bounded output. The API key travels through private stdin, never command arguments. Original private audio never receives a public URL.
- Jobs have 600-second leases and 30-second heartbeats across preparation and provider work. Every saved result requires the current unexpired token. Database connections are closed during external work and quota waits.
- The deterministic audio manifest and each completed transcript chunk are persisted. Timestamp offsets are converted to recording-relative seconds. Assembled transcripts are also validated against the shared 200,000-character/10,000-segment limits; excessive output fails explicitly rather than being truncated. Summary parts and intermediate merges are persisted with source digests.
- Summary input is conservatively bounded by serialized UTF-8 bytes plus a framing reserve, including instructions and schema (default budget 4,000 tokens). Completion is capped at 1,500 tokens including reasoning, with low reasoning effort. Long input is split without dropping characters, then combined in bounded stages. Failed convergence reports `summary_budget`; it never publishes a truncated result.
- Summary requests are spaced at least 60 seconds apart. Provider gates persist across restarts and jobs. Response metadata can extend the wait. Unknown 429 responses defer for one hour; waits are clamped to 60 seconds–24 hours. Quota deferrals release the job lease and do not consume failure attempts. After 24 consecutive deferrals the job fails instead of looping forever.
- Pending operations have three failure attempts with bounded backoff. Saving a chunk/part resets its failure counter. Summary retries keep the transcript. Credential errors fail immediately.

A crash between receiving a provider response and committing it may repeat that call. Leases and fencing protect saved state; they cannot guarantee exactly-once external processing. Interrupted temporary directories are removed on startup, after work and every 30 seconds while idle once they have no active lease.

## Read contracts

Owner-scoped GET endpoints return private, uncached JSON:

- `/v1/recordings/{id}/processing`: status, language, result availability, safe error code, deferred flag and update timestamp.
- `/v1/recordings/{id}/transcript`: `available: false`, or saved text and timestamped segments with provider/model metadata.
- `/v1/recordings/{id}/notes`: `available: false`, or the saved overview, key concepts, examples, review questions and unclear passages.

Another owner receives 404. Reading results never enqueues or calls a model. Notes use strict JSON schema and Pydantic validation; this verifies structure, not factual accuracy. Transcript content is untrusted, excluded from logs and rendered as text.

The frontend panel loads on expansion. Polling backs off, pauses while hidden, aborts on collapse/unmount, and stops on completed, failed or unavailable states. Fixture outputs are explicitly labelled synthetic.

## Testing and rollout

`AI_BACKEND=fixture` is allowed for development/tests and rejected in production. Test mode refuses the real Groq backend. Automated provider tests use controlled transport responses; worker/browser checks use the disposable loopback `archy_api_test` database. Concurrency tests use committed rows and independent sessions with explicit cleanup.

Before deploying, take a private database snapshot, verify the additive `0004_processing` migration locally, apply it with migration credentials, and then start the new API/worker code. Readiness queries all mapped tables, so migration must precede code activation. Synthetic fixture checks establish workflow behavior; real Korean/English transcription and summary quality require separate verification with a free-tier key and real samples.
