# Tokscale setup reference — activation blocked

Use [application setup](../README.md) for target, validation, approval and recovery.
This directory supplies a **zero-replica review bundle**, not a running hub or a
published production image. No reporter/scheduler is installed. Strict-TLS overlays
and current tests are **UNRUN**: Docker is absent and CI is owner-paused. Earlier
successful AMD64 build `8659b0d` does not validate the changed source.

## Pinned source and behavior

[Upstream revision `b26c433d`](https://github.com/junhoyeo/tokscale/tree/b26c433d03f23a2255ad9f212512ce83ede83da3)
is SHA256-locked in `source.lock.json`, including the complete archive and prepared
file tree. The derived image retains upstream MIT attribution in `LICENSE.upstream`.
It uses locked Bun, frozen dependencies, Next.js standalone output, non-root
UID/GID `10001` and port 3000. PostgreSQL ownership is independent of Langfuse.

**Migrations run before every server start.** Restarts/scaling need migration and
backup review; image downgrade does not reverse schema changes. The strict-TLS
candidate preserves upstream Drizzle engine/directory and lock/retry orchestration.
Runtime, advisory lock and migration child share explicit `verify-full`, trusted
CA and hostname checks; URL query/fragment overrides, IP endpoints and verification
disabling are rejected. Drizzle uses structured credentials because the pinned
version ignores separate SSL options with URL credentials. This is an unvalidated
candidate, not evidence TLS/migration/recovery works.

## Configuration and rendering

`render.py` accepts explicit JSON keys: `namespace`, `storageClass`, `appImage`,
`postgresImage`, `origin`, `gatewayPodLabel`, `databaseSize`. Images require
`@sha256:` plus 64 lowercase hex characters; origin is HTTPS with no path; database
size is explicit Gi/Ti. Never guess an image/endpoint/storage class/capacity or use
floating tags. Keep inputs/output outside Git. This is the renderer's CLI interface,
not a host run recipe; the current Docker runner accepts synthetic fixtures only,
and private-input container wiring still needs review:

```sh
python3 application-infrastructure/tokscale/render.py \
  /private/review-input.json > /private/tokscale-review.json
```

Output contains app/PostgreSQL Services, zero-replica Deployment/StatefulSet,
retained PVC template, TLS references and NetworkPolicies. No Namespace, Secret,
Ingress, CRD or Job is created. Service-account token mounts are off. Requests are
review starting points, not measured reservations. Even zero-replica apply changes
storage/network policy and requires approval; rendering authorizes no apply.

| Existing Secret | Required keys |
| --- | --- |
| `tokscale-database` | `postgres-password`, `database-url`; dedicated `tokscale` DB/user and matching instance/password |
| `tokscale-auth` | `auth-secret`, `github-client-id`, `github-client-secret` |
| `tokscale-database-ca` | `ca.crt` independently trusted by app and migration clients |
| `tokscale-postgres-tls` | `tls.crt`, `tls.key`; matches private database service DNS |

`DATABASE_URL`, `DATABASE_SSL=verify-full`, `DATABASE_CA_FILE`, explicit `APP_URL`,
GitHub OAuth and stable `AUTH_SECRET` are required; no automatic session-secret
fallback. OAuth registration/certificates/Secret creation need separate scope.
PostgreSQL TLS projection is root-owned `0440`, group 999: verify selected-image
UID/GID, key/PVC permissions and actual startup without loosening permissions.
Public `.pem.fixture` certificates/keys are test material, never deployment keys.

## Access and reporters

Protect all browser/read routes with private authenticated access and deny direct
origins. The gateway pod label/CNI NetworkPolicy is **not authentication**; review
namespace/label mutation authority. DNS/OAuth egress is absent until exact routes
are approved. Native `POST /api/submit` bearer auth remains a narrow machine path,
not a blanket `/api/*` exemption or browser redirect. See the
[exact route and upstream contract audit](contract-audit.md).

Test wrong-user/anonymous reads, direct-origin denial, missing/expired/revoked
machine tokens, method/path normalization and private OAuth callbacks. Upstream
tokens are user-scoped, not per-device identities. Server login does not grant
all account data or enroll reporters.

At separately approved enrollment, require the private `TOKSCALE_API_URL` in the
**actual reporter/scheduler context**, not just the interactive shell. `APP_URL`
configures the frontend separately. Missing endpoints may fall back to the public
hub upstream. Preserve stable device IDs, aggregate-only authorized roots and
native default cadence (autosubmit disabled by default; enable interval `24h`).
No six-hour collector, watcher or persistent job is introduced.

## Credential-free image build

`prepare_source.py` checks the archive, safe members and entire prepared tree,
refuses overwrite and removes the exact Vercel Analytics import/component.
`NEXT_TELEMETRY_DISABLED` alone does not disable browser analytics. Further browser
third-party egress still needs runtime review.

`images.lock.json` pins Bun 1.3.14-alpine and PostgreSQL 16-alpine indexes plus
AMD64/ARM64 manifests; inspected PostgreSQL AMD64 reports 16.15. Manifest existence
is not runtime qualification. `build_plan.py` verifies exact Bun digest/full tree
and prints, never executes, a build command. The paused
[application workflow](../../.github/workflows/application-infrastructure.yml)
owns `ci-build.sh`, sets `VALIDATION_IMAGE=infrastructure-validation:local`, and
supplies the genuine CI context. Do not force `CI=true` locally or invoke Docker
directly to bypass that guard; direct builds can pull before the build-time check.

Source/Python checks run inside Docker. CI builds AMD64 only, checks non-root user,
required files and Bun's node wrapper under `--network=none`, and records a local
image ID. It does not push, start the server, migrate, access a cluster or use live
DB/OAuth credentials. ARM64 build/run is unqualified. Public package/font downloads
are needed during build: credential-free does not mean offline. Receipts remain
in ignored `.runtime`, never evidence of application health.

`tls-contract.test.ts` uses isolated PostgreSQL TLS/startup mocks with public Node
fixtures, not a real DB/migration/server. Correct CA/DNS must reach a synthetic
marker; wrong CA/DNS or refused TLS must fail for runtime, lock and migration child.
These tests are authored **not run**. Activation additionally requires real isolated
migration/interruption/retry and encrypted off-cluster restore with authorization/
data reconciliation, exact-platform runtime and private browser/machine tests.
Rollback preserves databases/PVCs, keys, source histories, attachments and receipts.
