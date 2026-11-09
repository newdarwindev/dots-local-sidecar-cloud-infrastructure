# Tokscale setup reference — activation blocked

Use [application setup](../README.md) for target, validation, approval and recovery.
This directory supplies a **zero-replica review bundle**, not a running hub or a
published production image. No reporter/scheduler is installed. Python contract
tests, the AMD64 app build, image smoke check and all 13 TypeScript TLS socket
tests passed locally on 2026-11-05. Isolated real PostgreSQL TLS, migration, load
and process-restart checks also passed locally. CI remains owner-paused.
Encrypted recovery, deployed-platform and browser access acceptance remain pending.

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
version ignores separate SSL options with URL credentials. Isolated synthetic
qualification below is not evidence of deployed service or encrypted recovery.

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
PostgreSQL TLS projection is root-owned `0440`, group 70: verify selected-image
UID/GID, key/PVC permissions and actual startup without loosening permissions.
The locked Alpine PostgreSQL image reports UID/GID **70**. Qualification exposed
an earlier renderer mismatch (999); source now uses 70 for user, group and fsGroup
with an explicit regression test. Live root-owned `0440` group-70 key projection
and persistent storage startup remain unqualified: the isolated test copies the
public key to its own tmpfs with mode `0600`. Public `.pem.fixture`
certificates/keys are test material, never deployment keys.

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
uses `ci-build.sh` and supplies the genuine CI context. For an authorized local
AMD64 build, first run the committed validation entrypoint, then use:

```sh
VALIDATION_IMAGE=infrastructure-validation:local sh application-infrastructure/tokscale/ci-build.sh --local
```

The script pins the validation image ID, verifies source and base locks, caps the
build at 5 GiB/two CPUs, and runs the same image and TLS socket checks locally.
It does not publish an image or connect a database. Do not force `CI=true` locally.

Source/Python checks run inside Docker. CI builds AMD64 only, checks non-root user,
required files and Bun's node wrapper under `--network=none`, and records a local
image ID. It does not push, start the server, migrate, access a cluster or use live
DB/OAuth credentials. ARM64 build/run is unqualified. Public package/font downloads
are needed during build: credential-free does not mean offline. Receipts remain
in ignored `.runtime`, never evidence of application health.

`tls-contract.test.ts` uses isolated PostgreSQL TLS/startup mocks with public Node
fixtures, not a real DB/migration/server. Correct CA/DNS must reach a synthetic
marker; wrong CA/DNS or refused TLS must fail for runtime, lock and migration child.
All 13 checks passed locally with an independent Python/OpenSSL STARTTLS mock
sharing the client's `network=none` container namespace. Activation still requires
encrypted off-cluster restore with authorization/data reconciliation,
exact-platform runtime and private browser/machine tests.
Rollback preserves databases/PVCs, keys, source histories, attachments and receipts.

## Isolated real PostgreSQL qualification

The explicit local-only `sh validation/run.sh tokscale-db --local` route uses
`db-integration.sh` and `db-integration.ts`. On 2026-11-05 it passed against the
reviewed AMD64 app image and locked PostgreSQL 16.15 image. It uses a shared
`network=none` loopback namespace, tmpfs PostgreSQL storage, public TLS fixtures,
trust authentication and a public ignored client password placeholder. It creates
no authentication credential, host listener, deployment or reporter. Containers
are stopped but retained; logs and receipts remain in ignored `.runtime`.

Verified checks:

- All 33 migrations apply; repeated/concurrent runs retain 33 journal records.
- Real runtime TLS works; wrong CA and hostname fail for runtime, advisory-lock
  and Drizzle-child clients. TLS-disabled PostgreSQL is rejected by runtime and
  Drizzle child. The advisory-lock wrapper stays fail-closed during a bounded
  10-second observation but retries refusal; **fail-fast behavior is not qualified**.
- 100 concurrent synthetic writes complete through the runtime singleton.
- A deliberately terminated real migration child retries successfully on its
  second attempt without duplicate journal entries.
- PostgreSQL process restart preserves the 100 synthetic rows in the same tmpfs;
  the existing runtime pool reconnects and migration-lock acquisition retries
  the interruption. Upstream postgres.js emits `TimeoutNegativeWarning` during
  reconnect, but the assertions pass.

This is process restart/reconnection, **not a backup, restore or encrypted
recovery test**. The interrupted migration was waiting on its journal query;
rollback of partially executed schema changes is not established. No browser,
OAuth, HTTP load, production key projection or persistent-volume acceptance is
implied. The earlier TLS-disabled lock test was bounded by stopping its fixture
client; that failed-run receipt is retained alongside the successful bounded run.

## Prepared source evidence

The first local build stopped on an inconsistent aggregate prepared-tree hash.
The locked archive, original patch sources and overlay checksums matched. A file
comparison against that archive found exactly the five documented privacy/TLS
changes and no other modified, missing or added file. The aggregate tree lock was
corrected to `872f0424d40400ad9f856656422de9baa5f476f3126a6a95ca17a938226c4500`.
Source preparation, the AMD64 build and all TLS checks then passed with the
existing archive, patch, image and certificate checks retained.
