# Study tools

Documents expose owner-checked source passages at `/v1/documents/{id}/sources`.
New PDFs preserve page text; older PDFs retain an aggregate passage with no invented page
number. Transcript sources preserve recording-relative timestamps. Source IDs depend on
content and location, and saved generated content records its source revision.

`GET /v1/documents/{id}/study-notes` reads saved notes without a provider call. POST with
`language: en|ko` generates and replaces the document's current notes. Generation includes
all sources within a 64 KB serialized UTF-8 source bound, split into at most eight 8 KB
batches. Larger material returns `study_source_limit`; it is not silently sampled.

POST `/v1/documents/{id}/quizzes` accepts `language`, `questionType` (`multiple_choice`,
`true_false`, `mixed`) and `questionCount` (5, 10, 15). Quiz generation includes all source
material within a 24 KB serialized bound. Generated structure and source IDs are validated
before saving. Multiple choice has four options; true/false has two. Public quiz responses
omit answer keys, explanations and source IDs until an attempt is submitted.

POST `/v1/quizzes/{id}/attempts` supplies one option index per question. The server grades
complete, unique answers and stores an immutable result. Identical submissions return the
same attempt. GET reads the latest 100 attempts; distinct submissions are capped at 100.
POST `/v1/quizzes/{id}/retry` with `attemptId` creates an idempotent quiz containing only
that attempt's mistakes, preserving question IDs and making no provider call.

All endpoints recheck ownership and active document state. Notes and quizzes reject a
source revision changed during generation. Provider work has a 24-second deadline and two
concurrent slots per API process; no database session stays open during external work.
The existing private `AI_BACKEND` / `GROQ_API_KEY` configuration controls generation.
Disabled AI returns an explicit error. Fixtures are synthetic and never allowed in production.

Apply reviewed migrations through `0013_tutor_usage` before activating the combined study
and tutor release; readiness queries every mapped table. Take the private schema backup first.
Use the disposable loopback test database for verification, never hosted data. Groq quotas
and actual Korean/English answer quality require separate live verification after configuration.
