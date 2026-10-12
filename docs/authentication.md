# Authentication

Accounts use normalized email addresses and Argon2id passwords. Passwords are 10–128 characters, preserve whitespace and Unicode, and reject numeric, common and account-similar values. The common-password list retains its Django license and attribution. Legacy PBKDF2 verification uses each stored iteration count; successful login upgrades the hash without changing account IDs.

Signup stores a pending attempt with its own password/profile. A confirmation token is bound to that attempt. Confirmation locks the account and token, installs that attempt and removes competing attempts. Confirmation links expire after 24 hours.

Sessions contain at least 32 random bytes. Only their SHA-256 digest is stored, with a seven-day expiry. Login rotates the current session; disabled accounts cannot authenticate. Logout revokes that session. Password reset links expire after one hour and are purpose-bound. A successful reset invalidates every outstanding reset link and revokes every account session in one transaction. Trusted password/email changes also invalidate outstanding reset links.

The session cookie is host-only, Path=/, HttpOnly and SameSite=Lax. Signed random CSRF tokens use a readable cookie with the same path and SameSite policy. Writes require matching cookie/header tokens and the exact configured frontend Origin. Production requires Secure cookies and HTTPS. Legacy Django sessions and pending links are rejected at cutover; users sign in or request links again.

Signup and reset return generic accepted replies. Default limits are 10 logins/minute and three signup/reset requests/hour per immediate peer address. Behind Next.js this is a shared bucket. Public deployments need trusted ingress/account limits; untrusted forwarding headers never select a bucket.

Development mail uses private 0700 directories and 0600 files. Tests use an explicit memory outbox or private fixture files and cannot send SMTP. Production requires explicit SMTP settings; delivery failures are logged without recipient/link credentials.
