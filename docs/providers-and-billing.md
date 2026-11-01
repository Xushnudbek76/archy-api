# Social sign-in and test billing

Integrations default to disabled. Register this application's own provider apps; never copy the original project's credentials. Secrets belong only in the backend's ignored environment. Fixture tests make no provider calls.

## Social sign-in

Set the relevant `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, `KAKAO_CLIENT_ID`/`KAKAO_CLIENT_SECRET`, or `APPLE_CLIENT_ID`/`APPLE_CLIENT_SECRET`. Apple's secret is a short-lived Service ID client-secret JWT; rotate before expiry. Apple requires HTTPS/secure cookies. Enable Kakao OIDC and its email consent scope.

Register exact callbacks at `<FRONTEND_ORIGIN>/api/oauth/<google|kakao|apple>/callback`.

Start requires same-origin CSRF. Ten-minute, one-use state is bound to an HttpOnly browser cookie. Google uses S256 PKCE; Kakao/Apple use a transaction-specific OIDC nonce and confidential exchange. Apple's form POST needs Secure/SameSite=None on its flow cookie only. Application sessions stay SameSite=Lax.

ID-token signatures, issuer, audience, expiry, issue time, subject and nonce are verified against fixed provider JWKS endpoints. Access/refresh tokens are discarded. New identities need verified email. Existing emails never silently link accounts; users must use their established method. Authenticated identity linking is a separate future workflow.

References: [Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect), [Kakao](https://developers.kakao.com/docs/en/kakaologin/rest-api), [Apple](https://developer.apple.com/documentation/signinwithapplerestapi/generate-and-validate-tokens).

## Toss test subscriptions

Only `test_ck_`/`test_sk_` keys are accepted. Set `TOSS_CLIENT_KEY`, `TOSS_SECRET_KEY`, and a dedicated Fernet `TOSS_KEY_ENCRYPTION_KEY`. Generate the encryption key privately with `Fernet.generate_key()` and retain it for outstanding subscriptions/backups. Replacing it without migration makes saved credentials unreadable. Optional `TOSS_WEBHOOK_TOKEN` must be a random 32–128-character value.

The regular monthly catalog mirrors the original: Plus ₩9,900 and Pro ₩14,900. Promotions/native purchases are excluded. This installation exposes test plans only, sharing its current study capabilities and recording cap. It does not promise unlimited processing or change Groq quotas.

Checkout persists an owned order, server price, request identity, consent version and random customer key. The browser SDK registers a test card and returns `authKey`/`customerKey`; the result page strips them from history. The server binds the auth key to the order, encrypts credentials, issues the billing key, and approves with a stable idempotency key. Retries look up the order before repeating approval. Only verified order, integer KRW amount, payment key and timestamp activate a subscription. Redirect parameters and webhook bodies never grant access.

Leases release database connections during provider calls and fence saved results. Lost responses are reconciled by order ID. Eight attempts within twelve hours and exponential delays bound recovery; ambiguous results become `review` for operator inspection. External effects cannot be guaranteed exactly-once.

Schedule `python -m scripts.run_billing` once per minute on a single scheduler. It processes bounded pending work and renewals. Calendar months clamp month-end dates; missed periods do not trigger catch-up charges. Include this process's pool in the hosted connection budget. Test gates also apply to the command.

Configure the Toss payment-status webhook to `<API_ORIGIN>/v1/billing/events/<TOSS_WEBHOOK_TOKEN>` over HTTPS. Keep that URL private and redact URL values in upstream logs. The API logs route templates. Events trigger an authenticated provider lookup; old approvals cannot undo verified cancellation. Without webhooks, use Check status when investigating a payment.

Cancellation stops renewals and preserves the paid period; it does not refund past charges. An in-flight renewal must be reconciled before closure. Live keys, merchant approval, refunds and native billing need a separate rollout.

References: [Toss integration](https://docs.tosspayments.com/guides/v2/billing/integration), [API/idempotency](https://docs.tosspayments.com/en/api-guide), [cancellation](https://docs.tosspayments.com/guides/v2/billing).

## Rollout

Back up database/media → verify on disposable loopback database → apply additive migrations `0014`–`0022` using the migration role → deploy code. Readiness checks every model table. Configure and test each provider before exposing controls. The local implementation does not run hosted migrations or live transactions.
