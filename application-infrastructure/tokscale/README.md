# Tokscale — executable review artifacts, activation blocked

This directory translates the [reviewed upstream source](https://github.com/junhoyeo/tokscale/tree/b26c433d03f23a2255ad9f212512ce83ede83da3)
into a **zero-replica** Kubernetes review bundle. It is not a running hub or a
validated production image. No scheduler or reporter enrollment is installed.
The derived Dockerfile includes upstream MIT attribution in `LICENSE.upstream`
(Copyright 2025 Junho Yeo), verified at the pinned revision.
Source revision and SHA256 hashes of inspected upstream files are recorded in
`source.lock.json`; these are source-inspection evidence, not a whole-tree digest.

## Verified source contract

- Upstream `Dockerfile` installs the Bun workspace with `--frozen-lockfile`, builds
  Next.js standalone output, runs non-root, and starts on port 3000. The derived
  recipe here replaces the floating Bun base with a **required digest input** and
  makes its non-root UID/GID explicit (`10001`). No app image was built or pushed.
- `docker-entrypoint.sh` runs Drizzle migrations **before every server start**.
  Scaling/restarting the hub therefore needs migration/backup approval, not only
  a container-start decision. Downgrading an image does not reverse migrations.
- The pinned Compose example uses PostgreSQL 16. Its default passwords, plaintext
  DB transport and floating image tags are deliberately **not** carried forward.
- `DATABASE_URL`, `DATABASE_SSL`, `APP_URL`, GitHub OAuth credentials and a stable
  `AUTH_SECRET` are required independently. Never rely on upstream automatic
  session-secret generation. GitHub OAuth registration is a separate owner action.
- `POST /api/submit` uses upstream bearer-token authentication. This does **not**
  protect public profile, leaderboard or other read routes. An authenticated
  private browser/read gate and narrowly reviewed machine submission route remain
  necessary. Do not exempt all `/api/*` or replace machine auth with a browser
  redirect. Token issuance/revocation and redirects need end-to-end testing.

## Offline rendering

`render.py` accepts a private JSON configuration path and emits a Kubernetes List
(JSON is valid Kubernetes input). Required keys: `namespace`, `storageClass`,
`appImage`, `postgresImage`, `origin`, `gatewayPodLabel`, `databaseSize`.
Both images must include `@sha256:` plus 64 lowercase hex characters; no default
registry, floating tag, actual endpoint, storage class or capacity is guessed.
Use an explicit HTTPS origin without a path. The PostgreSQL storage request must
be an explicit Gi/Ti budget. Inputs and rendered manifests stay outside Git.

```sh
python application-infrastructure/tokscale/render.py /private/review-input.json > /private/tokscale-review.json
```

Rendering changes no cluster state. Output includes dedicated app and PostgreSQL
services, a zero-replica Deployment and StatefulSet, retained PVC template, TLS
secret references and NetworkPolicies. No Namespace/Secret/Ingress/CRD/Job is
created. Both workloads have service-account token mounting disabled. Database
credentials/ownership are independent of Langfuse. Resource requests/limits are
**review starting points, not demonstrated capacity or production reservations**.

Only same-namespace pods bearing the explicitly supplied gateway label can reach
the app under the proposed policies. Only the app can reach this PostgreSQL.
This is **not application authentication**: namespace/pod-label mutation authority
must be reviewed and CNI policy enforcement tested. DNS and external OAuth egress
are intentionally absent; separately review exact cluster DNS and outbound routes.
NetworkPolicy installation itself requires approval. No gateway is deployed here.

Existing Secret references (contents must never go into Git/tools/logs):

| Secret | Keys / role |
| --- | --- |
| `tokscale-database` | `postgres-password`, `database-url`; dedicated database/user `tokscale`, URI refers to this instance and matching password |
| `tokscale-auth` | `auth-secret`, `github-client-id`, `github-client-secret`; independent approved custody |
| `tokscale-postgres-tls` | `tls.crt`, `tls.key`; certificate matches private database service DNS |

The PostgreSQL projection uses root-owned, group-readable `0440` material with
GID 999. Verify this UID/GID against the **selected PostgreSQL image digest**,
mounted key permissions, PVC ownership, certificate validity and PostgreSQL
startup in an isolated container/cluster test before activation. Do not loosen
permissions to get past errors. `DATABASE_SSL=require` alone is **not evidence of
CA/hostname verification**: pinned driver behavior, trusted CA delivery and
negative-certificate tests remain blockers. No TLS-verification claim is made.

## Reproducible build handoff — not executed

Obtain and verify the complete upstream tree at the locked commit through the
approved source route. Inspect the full tree/lockfile and its license. From that
source root, use this derived Dockerfile, supplying a separately verified
`oven/bun@sha256:...` as `BUN_IMAGE`. Use `build_plan.py` to reject a floating
base **before** any Docker invocation; it only prints a command and never runs
Docker. The Dockerfile also rejects a non-digest base during its base-stage RUN
check (direct Docker invocation may resolve/pull the base before that check).
The frontend build does not need a live
`DATABASE_URL`; never inject live credentials into a Docker build. Record build
provenance, full-tree integrity, base digest, target architecture, dependency
license/security checks and output image digest. The reviewed file hashes are
not enough to attest uninspected files. Do not claim this recipe is reproducible
until that complete-source/base-image lock and an actual build test succeed.

## Release blockers and acceptance

No deployment/apply command is included. Do not scale these artifacts or apply
NetworkPolicies/PVC templates until the parent bundle's exact-current approval,
capacity and access gates pass. A zero-replica apply still mutates services,
storage policy and network policy and is not authorized by rendering.

Required evidence: selected-host combined RAM/root/backing-storage solution;
verified image digests/architecture and build; tested private authenticated reads,
wrong-user denial, direct-origin denial and exact machine auth routes; no optional
browser analytics/third-party egress without review; trusted database TLS with
wrong-CA/hostname rejection; OAuth/secret custody; migration rehearsal; encrypted
off-cluster PostgreSQL restore with authorization/data reconciliation. Establish
upstream native reporter cadence and an **explicit private hub endpoint** at
separate enrollment; never fall back to a public hub or add a six-hour scheduler.

Rollback stops new traffic/reporting and scales only approved workload changes;
it does not delete the database/PVC, source histories, attachments or receipts.
Run `test_render.py` only inside the committed validation container. Tests are
synthetic and establish render invariants, not application/auth/database health.
