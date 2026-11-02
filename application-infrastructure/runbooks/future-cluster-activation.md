# Future compatible-cluster handoff — design only

The owner has deferred live inspection and allowed design against a **hypothetical
compatible Kubernetes cluster**. That assumption is not a measurement, credential,
permission, readiness result or deployment approval. All GitHub workflows stay
disabled. These new scripts/tests have **not run**: local Docker is absent and
CI execution is paused. Never use another session/host/compiler to bypass that.

## What is now packageable

The machine-readable contract is `contracts/future-cluster.schema.json`; copy
`contracts/future-cluster.example.json` to private storage outside the repository.
It deliberately contains null essential inputs and unverified capabilities.
Do not put passwords, tokens, key material, account histories or secret values in
it. `evidenceRef` and recovery references identify privately held evidence only;
this tooling does not read, validate or publish that evidence.

After future authorized Docker validation, the following **local-only** commands
can assess inputs and prepare a write-once mode-0700 review packet. They do not
fetch, render, contact a cluster, run a shell, create credentials or install anything:

```sh
python application-infrastructure/scripts/cluster_contract.py assess --config /private/future-cluster.json
python application-infrastructure/scripts/cluster_contract.py packet --config /private/future-cluster.json --output /private/new-review-packet
```

**Essential bundle-render inputs:** intended Kubernetes version and StorageClass;
namespace defaults to `dots-applications` and may be changed explicitly. This is
only selection of render inputs, not proof either exists. Packet targets remain
`synthetic: true`, with a deliberately nonexistent context/namespace UID and all
readiness gates false. Supplying evidence claims cannot change those fields.

**Additional Tokscale-render inputs:** approved immutable app image, approved
PostgreSQL image, private HTTPS origin (no userinfo/path/query), gateway label and
explicit database-size budget. The app image has not been published by this work;
a local image ID from old CI is not a pullable registry reference. Image publication
requires separate authorization. Never replace missing input with a floating tag.

With complete inputs, a packet contains `render-target.json`, `assessment.json`,
a hash receipt, and optionally `tokscale-render-input.json`. After validation is
reauthorized, existing commands may consume them for **review-only** rendering:

```sh
# Public artifact fetch, only when expressly allowed; no chart execution here.
python application-infrastructure/scripts/bundle.py fetch
python application-infrastructure/scripts/bundle.py render --target /private/new-review-packet/render-target.json --output /private/new-render
python application-infrastructure/tokscale/render.py /private/new-review-packet/tokscale-render-input.json > /private/tokscale-review.json
python application-infrastructure/scripts/resource_report.py /private/new-render/manifests.yaml
```

Run validation only through the repository's authorized Docker path. The commands
above are documentation, not commands already executed or permission to reenable
CI. Hash receipts bind input files, not consent. The packet is **not installable**:
no apply command is emitted, `bundle.py deploy` stays blocked, Tokscale retains
zero replicas, and ordinary Helm manifests are NOT a no-op to apply manually.

## Compatibility and capacity acceptance

1. Identify exact Kubernetes/distribution/version, node architectures, target
   context and immutable namespace UID. Refresh actual evidence only when owner
   authorizes inspection. A different available cluster is not a substitute.
2. Compare actual ClickHouse operator/CRD source, served APIs, defaulting and
   admission behavior with `clickhouse-operator.lock.json`. v0.0.8 is an inspected
   candidate, not an installation choice or observed operator. Review its webhook,
   certificate and RBAC prerequisites without installing them by assumption.
3. Prove CNI ingress **and** egress policy enforcement, private DNS, authenticated
   browser/read gateway, wrong-user/direct-origin denial and exact machine routes.
   NetworkPolicy is not authentication. Enumerate and separately approve outbound
   OAuth, DNS, registry and recovery destinations; never allow all egress to fix tests.
4. Prove CSI physical backing/encryption, RWO semantics, reclaim/retention policy,
   volume growth limits and independent encrypted recovery. Snapshot support alone
   is not off-cluster recovery; a snapshot sharing the host/storage failure domain
   does not satisfy the contract. No resize/repartition/adoption is authorized here.
5. Reconcile actual app/dependency replicas, operators, init containers, deployment
   surge, old pods, Jobs, retained PVCs, DB growth, logs, root disk and existing loads.
   `resource_report.py` adds ordinary + init requests conservatively; unresolved
   CRs and zero-replica workloads remain explicit omissions. Its 25% design headroom
   is a tunable planning assumption, **not a fit claim**. CPU/memory totals cannot
   prove per-node placement, topology constraints, limits, burst or eviction safety.
6. Browser runtime, Temporal, lease store and gateway budgets are **not included**
   unless their actual manifests are assessed too. Use the browser repository's
   own runtime requirements/acceptance contract. Record both repository revisions;
   generic infrastructure evidence cannot prove browser lifecycle fencing.

## Secret custody and TLS preparation — no secrets in packets

The staged charts reference existing secret objects; none are created here.
Inventory required names/keys from checked-in values and the Tokscale README.
The owner must identify the independent custodian and delivery procedure. Avoid
single-host-only encryption-key custody. Authentik/OpenBao/ESO remain a later
proposal, not a prerequisite silently bootstrapped by this bundle.

Tokscale needs a trusted CA projection and URL with one matching DNS host, without
query overrides. Runtime, lock connection and the preserved Drizzle CLI must all
reject wrong CA/hostname and TLS refusal. Public `.pem.fixture` test files are
compromised-by-design fixtures: **never use them for a deployed certificate/key**.
Actual certificate issuance, OAuth registration, secret creation and access grants
require their own approved scope; supplying a template does not authorize them.

## Backup and restore rehearsal

Before any application start/migration, record: exact image/source revision,
database/schema version, resource/manifest hashes, approved recovery destination,
custodian, retention policy, existing-data ownership and recovery objectives.
Unfilled references block activation; don't invent a bucket, account or key owner.

- Take database-consistent logical/physical backups appropriate to each engine.
  PostgreSQL backups must preserve schema/data and required roles separately;
  ClickHouse, Keeper coordination and SeaweedFS object/index state need their
  engine-specific consistency procedures, not copies of live PVC directories.
- Encrypt **before** transfer to the independently approved destination. Use a
  reviewed client and private credential files, not passwords in command arguments,
  public logs or CI output. No backup command is executed by this packet.
- Verify authenticated encryption/decryption, checksums and retrieval using an
  isolated recovery environment with no production traffic, reporters or OAuth.
  Restore with explicit test identities and prevent callbacks/exports to real systems.
- Compare row/object counts, schema/journal state, authorization isolation and
  application-level sample reconciliation. Record measured recovery time and
  recoverable point; a successful download or container start is not a restore test.
- Retain source backups and recovery evidence. Do not delete/expire old copies,
  change retention, prune volumes or rotate keys as part of this staging work.

## Migration and activation sequence

Each step waits for exact-current owner approval and prerequisite evidence. Do not
turn this sequence into an automatic CI deployment or persistent job.

1. Reauthorize and run static/unit, image provenance/platform, TLS-negative,
   operator admission and full-envelope Collector canary tests on isolated fixtures.
   The earlier green `8659b0d` does not cover later TLS/image or contract changes.
2. Rehearse migrations from an authorized isolated restore, using exact proposed
   images and the **existing** upstream migration engine. Capture migration journal,
   schema and data reconciliation before/after; test interrupted startup/retry and
   advisory-lock serialization. Tokscale runs migrations before every server start.
3. Produce a review packet binding source revision, approved target/namespace UID,
   fresh evidence timestamps, final manifests and image digests; include the complete
   resource-level storage/network/RBAC/credential change list and rollback boundary.
4. Obtain explicit initial-activation approval covering those changes. Implementing
   a bounded deployment path is future work: current `bundle.py deploy` is disabled.
   A PR merge, hypothetical cluster match or green CI never grants apply permission.
5. During the separately approved activation, stop on target/manifest drift, failed
   TLS/access tests, restore uncertainty or capacity shortfall. Do not weaken TLS,
   bypass policy, change host, resize storage or regenerate secrets to proceed.
6. Only after approved acceptance may a separately approved CI environment own
   subsequent rollout. Owner's current workflow pause must be lifted explicitly.
   Source enrollment, real token histories, reporters and persistent schedules
   remain separately disabled. A running hub does not enroll devices.

## Rollback and stop conditions

Stop new traffic/reporting only within the approved scope; preserve original
histories, receipts, PVCs, databases and encryption keys. Application image rollback
does **not** reverse schema migrations. Prefer the rehearsed forward fix or isolated
restore/cutover plan with explicit data-loss approval. Never uninstall/prune a
namespace, delete PVCs, truncate histories or overwrite original backups as a
rollback shortcut. Record unknown outcomes and reconcile before repeating an action.
