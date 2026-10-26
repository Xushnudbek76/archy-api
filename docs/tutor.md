# Document tutor

POST `/v1/documents/{id}/conversations` creates a private conversation; GET lists the
latest 50. GET `/v1/conversations/{id}` reads completed user/assistant pairs. Every access
checks both owner and active document state. Conversations are capped at 50 per document
and 50 completed turns each.

POST `/v1/conversations/{id}/messages` accepts `message` (at most 2,000 characters),
`language` (`en` or `ko`) and a client-generated UUID `requestId`. It streams newline-delimited
JSON: `delta` with `text`, `sources` with `items`, `done` with `messageId`, or `error` with
a safe `code`. Only `done` confirms durable completion. Retrying the same completed request
replays its saved response; a different payload with the same ID is rejected.

Retrieval ranks English terms and Korean two/three-character sequences across source text.
At most six excerpts and a bounded recent history enter a serialized request of at most
24 KB. This is lexical retrieval, not a claim that the model reviewed the whole document.
The source cards show real selected passages supplied to the tutor; they do not prove
semantic entailment of every answer. With no matching passages, a deterministic localized
reply explains that no relevant source was found without making a provider call.

Groq uses the existing private provider configuration. Fixture responses are explicitly
labelled synthetic. Real provider SSE is parsed with bounded UTF-8 frames/output and a
30-second deadline. Database sessions close before provider waits and streamed writes.
Source revision and fencing checks run again before saving the completed pair. Failed or
cancelled partial responses never enter completed history.

Persisted controls limit the API to two active generations globally and ten requests per
owner per minute. Generation leases expire after 64 seconds. Cancellation during preparation,
response-header failure and generator shutdown release the reservation; leases also recover
after process death. Provider cooldowns persist from rate-limit responses. Request cleanup
is idempotent, and saved turns retain their source snapshots after later material edits.

Tests use controlled provider streams and a disposable PostgreSQL database. No live Groq
quality, free-tier throughput or hosted deployment is implied by fixture verification.
