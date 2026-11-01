# Student workspace

Next.js keeps thin routes under `app`, feature UI under `libs/components`, typed contracts under `libs/types`, and HTTP transport under `api`. FastAPI owns persistence and domain rules. The original checkout remains a read-only design reference.

## Semesters and materials

`/v1/academics` stores owned semesters, timetables, a primary timetable, and a separate home selection. Viewing an alternate timetable does not replace the primary. Archived semesters and their study tools are read-only. Uploads admitted before archival may finish; existing courses without a timetable still work.

Courses support a professor, color, and up to 14 weekly slots. Dashboard dates use Asia/Seoul. Imports accept public Everytime share links through a fixed, bounded provider endpoint. Users review classes before an atomic, idempotent save. Private pages, screenshots and OCR are unavailable. Limits are 100 semesters/timetables and 50 classes per import.

Document pins and recording filters are owner-scoped. Standalone recording reuses the existing capture/upload implementation and opens its saved study document. The configured recording duration cap is unchanged.

## Preferences and closure

`/v1/preferences` stores school details, UI/summary language and note format. Korean/English navigation and settings use an explicit dictionary; material content is never translated by that dictionary. Three preset and up to ten custom note formats are supported. Jobs snapshot language and format instructions, including their provider token budget. Existing jobs/results keep their settings.

Closure requires a current password and `CLOSE`, revokes sessions, removes private study records, and anonymizes the account row. Renewing subscriptions and unresolved payments block closure. Cancellation prevents further renewals; encrypted payment credentials are cleared on closure, while non-personal transaction records remain. Social accounts can first set a password through the verified email reset flow.

Private media cleanup is queued in the same transaction. Cleanup refuses directory symlinks and unlinks only recorded UUID paths. Captured processing-job identifiers include interrupted decoded-audio directories; per-job file locks and lease validation prevent late recreation after closure. The processing worker retries cleanup; `python -m scripts.purge_accounts` is also available. After eight failures, inspect `preferences_media_purge` with the migration/admin role, resolve the filesystem problem, and deliberately reset `attempts` and `available_at`. Keep the task until its files are removed.

## Browser delivery

The manifest and original gem icons support installation. Controls appear when the browser offers a prompt; Safari guidance is always available. No service worker caches private responses. Protected pages, account/API routes and checkout results send private/no-store headers. Push delivery, OCR and live summaries remain unavailable until their providers and complete flows are verified.
