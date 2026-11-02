# Pinned Tokscale runtime contract audit

Source-inspection evidence only; no live database, OAuth, token issuance, ingestion, scheduler installation or deployment was performed. Source revision: [`junhoyeo/tokscale` at `b26c433d03f23a2255ad9f212512ce83ede83da3`](https://github.com/junhoyeo/tokscale/tree/b26c433d03f23a2255ad9f212512ce83ede83da3). No runtime tests were executed by this audit (repository requires Docker and local Docker is absent). A successful image build is not evidence that the following activation blockers are resolved.

## Database TLS: verified blocker, not just missing evidence

- `packages/frontend/src/lib/db/index.ts:getDatabaseSslMode` returns only `false` or `"require"`; production defaults to `"require"`. Even unrecognized values such as `verify-full` fall back to `require` in production.
- `bun.lock` pins `postgres@3.4.7`. The [driver's tagged connection source](https://github.com/porsager/postgres/blob/v3.4.7/src/connection.js#L269-L279) explicitly maps `require`, `allow` and `prefer` to `rejectUnauthorized:false`. This encrypts transport but does **not** authenticate the certificate chain/hostname. Retrieved driver source SHA256: `0847375f271c373745b4c2af1bbb5dc2da5ee6f69937cc52516b5b6a667af7a4`.
- `packages/frontend/scripts/migrate-core.ts` uses that same weak mode for its advisory-lock connection, then **overwrites** the URL's `sslmode` with `require` for its `bunx drizzle-kit migrate` subprocess. `drizzle.config.ts` supplies only that URL. Setting a `verify-full` query parameter in the original secret does not cure this path.
- Required fix scope: runtime connection, migration lock connection **and** migration subprocess must share strict certificate/hostname validation and trusted CA delivery. Tests must prove trusted matching DNS succeeds, wrong CA and wrong hostname fail, and no cleartext fallback exists for all paths. Do not loosen verification to make a build/runtime check pass. Renderer `DATABASE_SSL=require` is currently only a known-inadequate staging setting, not a deployment-approved TLS configuration.

## Private browser/read gate and narrow machine routes

The upstream public product is not a private authenticated hub by default. `/api/users/[username]/devices` delegates to a public-profile helper; leaderboard, user/profile, badges and embeds likewise must not become publicly reachable just because submission uses a token. Protect the entire browser/read surface by default and deny direct origin access. A user logged into the browser gateway is not automatically authorized to every upstream account.

| Exact route/method | Pinned behavior | Staging policy |
| --- | --- | --- |
| `POST /api/submit` | Extracts Bearer header; invalid/missing/expired token returns 401 before parsing submission | Candidate narrow non-interactive route; preserve native token auth, never exempt `/api/*` |
| `GET /api/auth/token` | Native CLI token validation; same personal-token authentication | Separately review if needed for CLI; do not silently broaden submission exception |
| `GET /api/me/stats` | Bearer-only own-user aggregate read across devices; no cookie auth | Optional machine read, not part of submission exception unless explicitly reviewed |
| `POST /api/auth/device` | Creates expiring device code without existing user auth | Enrollment endpoint; keep blocked/gated until separately authorized design |
| `POST /api/auth/device/poll` | Exchanges approved one-time device code for token | Enrollment endpoint; no blanket exemption; test native enrollment separately |
| `/device`, `POST /api/auth/device/authorize`, GitHub login/callback and settings | Browser/enrollment surfaces | Protected browser flow with exact callback design; no redirect bypass assumptions |

`src/lib/auth/personalTokens.ts` validates SHA256-hashed `tt_` tokens with optional expiry; deletion revokes tokens. Tokens bind to a **user**, not a device-only scope; they are accepted for own-user machine stats as well as submission. A device label/token name is not per-device isolation. Do not promise scope isolation or revocation outcomes without tests.

Acceptance must include unauthorized browser reads denied, wrong-user access denied, direct-origin denied, correct token submission not redirected, missing/expired/revoked tokens rejected, method/path normalization not widening exemptions, and real OAuth return paths staying private. Synthetic tests do not authorize enrolling real users or submitting histories.

## Endpoint and reporting defaults

- `crates/tokscale-cli/src/auth.rs:get_api_base_url` reads `TOKSCALE_API_URL`; absent variable silently defaults to `https://tokscale.ai`. Reporter processes must have an explicit validated private HTTPS origin in their **actual execution context**, not merely the interactive login shell.
- `packages/frontend/src/lib/seo/urls.ts:getPublicOrigin` separately reads `APP_URL`. Missing or malformed production input silently falls back to `https://tokscale.ai`; this affects device verification URLs, canonical metadata and auth origin handling. Explicit frontend `APP_URL` does not configure native reporters.
- `crates/tokscale-cli/src/tui/settings.rs:AutosubmitSettings::default` sets `enabled:false`. `commands/autosubmit.rs:AutosubmitEnableArgs` defaults `--interval` to `24h`. Preserve upstream default semantics; do not add a six-hour job or imply reporting is enabled by installing the hub.
- Native scheduler renderers launch `tokscale autosubmit run`; reviewed systemd/cron renderers do not embed `TOKSCALE_API_URL`. Exporting the variable when enabling a scheduler is not proof the future scheduled process receives it. Endpoint-negative tests and scheduler-specific environment review are required before any later authorized enrollment. No scheduler should be created in this staging work.

## Credential-free build versus network-offline/privacy

Upstream frontend can build without live DATABASE_URL/OAuth tokens. However `src/app/layout.tsx` imports Google fonts via `next/font/google`; dependency and font retrieval are public network inputs unless explicitly vendored. Credential-free does not mean air-gapped/offline-reproducible. Lock dependencies and record build network requirements honestly.

The same layout unconditionally renders `@vercel/analytics/next` `<Analytics />`. `NEXT_TELEMETRY_DISABLED=1` is not a browser analytics disable switch. Remove or explicitly disable optional analytics in a reviewed build overlay, then verify the served browser has no unapproved analytics/third-party egress before activation.

## Scope boundary

Complete source/base locks and credential-free CI image qualification can proceed without deploying. These findings do not authorize a TLS-insecure runtime, OAuth registration, token creation, real reporting, persistent jobs, database migration against existing data, or new secrets. Later Auth/Bao rollout and minimal bootstrap remain separate approval scopes. Kali6 remains offline; no target readiness claim follows from source inspection or CI.

## Unvalidated strict-TLS overlay candidate

The current local candidate now patches runtime, advisory lock, migration child
and drizzle-kit configuration with shared explicit certificate/hostname validation
and CA-file delivery. The existing bunx/drizzle-kit migration engine and lock/retry orchestration
are preserved. Its config uses structured credentials: pinned drizzle-kit 0.30.6
discards separate ssl options when a URL credential is supplied. Tests are written
but **unrun**, because the owner disabled GitHub workflows for budget and local
Docker is absent. The upstream findings above remain valid historical evidence;
the candidate is not a verified cure or permission to activate. Migration schema
compatibility, full restore rehearsal and target CA custody remain blocked.
