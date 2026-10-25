# Private documents

Documents belong to the signed-in account. A document can have an optional course folder,
recording reference, PDF, or both a PDF and a recording. Existing recordings receive document
rows through migration 0005; newly accepted recordings receive one in the same transaction.
Automatic document IDs match recording IDs, making materialization idempotent. Explicit study
documents may reuse any owned recording. Archiving a document hides its detail and PDF without
deleting the document, source recording, or file.

The `/v1/documents` collection supports create and fixed 20-item pages. The optional `q` query
is a case-insensitive literal title substring, limited to 100 characters; `courseId` selects a
folder. Unknown or repeated query parameters are rejected. Detail includes extracted `text`;
list, create, PATCH and archive responses contain metadata. Successful PDF upload returns detail.
PATCH accepts a nonempty subset of `title`,
`courseId`, and `recordingId`, with null clearing either reference. Foreign references and
foreign documents return 404.

Upload a raw `application/pdf` body to `POST /v1/documents/{id}/pdf`, with a URL-encoded UTF-8
`X-File-Name` ending in `.pdf`. Normal session, Origin, and CSRF requirements apply. Files are
limited to 20 MiB, 200 pages, and 500,000 extracted characters. Encrypted, malformed and
scanned-only PDFs are rejected. No OCR or AI summarization is performed. Complex PDFs may
also exceed the bounded processing budget and are rejected without being saved. A document
with a PDF rejects replacements with 409; create another document to upload another version.

Two uploads per API process may receive or extract PDFs concurrently. Authentication and
ownership checks finish before receiving bytes, and sessions close before receipt or
extraction. Extraction runs in a child process with a 15-second timeout, a 384 MiB observed
memory limit and bounded output. Temporary input uses an automatically cleaned private
0700 directory and 0600 UUID file. This also avoids feeding large input through the shared
subprocess helper's polling stdin path. Parsing errors expose only safe public messages.

Final PDFs use UUID names under `RECORDING_STORAGE_ROOT/documents`, with private permissions,
exclusive creation and directory descriptors that reject symlinks. Never expose this directory
through a public static-file server. GET and HEAD `/v1/documents/{id}/pdf` authorize each access;
responses use `application/pdf`, `private, no-store`, `nosniff` and a sandbox CSP. Downloads hold
no database session while streaming. Include the documents directory in private media backups,
and deploy the additive migration before the API routes. API JSON never includes storage paths.
