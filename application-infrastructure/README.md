# Application setup — staged, not activated

This is the **single current operator path**. It stages Langfuse + PostgreSQL,
ClickHouse/Keeper, Valkey and SeaweedFS; a trace-only OTel Collector; Tokscale +
its own PostgreSQL; and an independent `homarr-workload` instance. Shared
Authentik, OpenBao/ESO and domains are [deferred](../docs/auth-domain-plan.md).

For Git-backed configuration recovery, initial local access and the current
capacity calculation, see [configuration recovery](../docs/configuration-recovery.md).

**Status:** rendering, synthetic telemetry contracts and review tooling exist;
deployment/source enrollment do not. Full Docker validation passed locally on
2026-11-05, including lint, 54 validator tests, 7 primary tests, application tests,
Helm renders and strict schemas. Live cluster acceptance remains separate.
GitHub workflows remain owner-paused.

## 1. Prerequisites

- Use only the owner-selected target. A hypothetical compatible cluster permits
  design, not a readiness claim. Live inspection is deferred; do not substitute a
  different host, widen access or change storage/power/workloads to make it fit.
- Before activation, verify Kubernetes/node architecture, namespace identity,
  actual ClickHouse operator/CRDs and prerequisites, CNI ingress **and egress**
  enforcement, private DNS, trusted TLS, authenticated UI/read access and denied
  direct-origin access. NetworkPolicy alone is not authentication.
  Expose only approved web/ingestion interfaces; worker, database, queue, S3 and
  operator endpoints stay private. Allowlist exact egress; never permit all to
  make tests pass. Langfuse telemetry opt-out is not proof of zero external traffic.
- Measure one combined budget: existing workloads, operators, all replicas/init
  containers/Jobs, upgrade surge, databases, retained PVCs, queues/logs and growth.
  Verify physical backing, thin-pool/root/RAM headroom, RWO semantics and retention.
  Real-data profiles require encrypted volume backing and encrypted independent
  recovery. The explicitly synthetic-only unencrypted profile below is a narrow
  exception; it does not waive backing, capacity, RWO or retention checks. Shared
  disks count once; requests and the report's 25% planning headroom are not proof
  of fit. Browser/Temporal/lease/gateway workloads need their own manifests and
  acceptance evidence; they are not included implicitly.
- Establish private authenticated administration, least-privilege machine access,
  encrypted secret custody independent of this cluster/IdP, and an independently
  encrypted recovery destination with a tested restore. No default passwords,
  anonymous APIs, public usage data or disabled TLS verification.
- Validation must run in Docker through the committed entrypoint. Do not use
  another host/compiler or enable CI to bypass the workflow pause.
  Use newly invented fixtures only; `synthetic: true` does not sanitize real data.

## 2. Configure privately

### Synthetic-only unencrypted lab profile

The [synthetic unencrypted lab contract](contracts/synthetic-unencrypted-lab.example.json)
is a design-only exception for a disposable, synthetic-data lab on an
owner-selected host. It explicitly disables volume encryption and forbids
real histories, real telemetry, credentials, external source ingestion and
production use. Keep the target's actual identity, StorageClass and capacity
evidence private. This profile does not claim a volume exists, that its contents
are disposable, or that any deployment gate is satisfied.

This profile uses K3s' `local-path` provisioner on an ext4 filesystem mounted at
`/var/lib/rancher/k3s/storage`; it is node-local, is not CSI, and PVC size requests
are not hard quotas on the shared filesystem. This narrowly waives the generic
encrypted-RWO-CSI requirement only for synthetic-only use. Real-data profiles
continue to require encrypted CSI storage. The profile does not enable the
repository's blocked deployment path.

Keep Kubernetes Secret encryption, application encryption keys, private access
controls and normal PVC retention requirements unchanged. Do not reuse this
profile for real data: a real-data profile still requires encrypted volume
backing, independent encrypted recovery and a tested restore. Synthetic values
are not safe merely because they are labeled synthetic; ensure they contain no
copied histories, credentials, identifying payloads or internal telemetry.

Copy the [essential-input template](contracts/future-cluster.example.json) to a
mode-0600 file **outside the repository**, checked against its
[schema](contracts/future-cluster.schema.json). Keep actual context/namespace UID,
host capacity, private endpoints, evidence and recovery references private. Never
put secret values, histories, account identities or credentials in the packet.

| Input | Required for |
| --- | --- |
| Kubernetes version, StorageClass; namespace defaults to `dots-applications` | Bundle review rendering; neither value proves a live resource exists |
| Immutable app/PostgreSQL image references, private HTTPS origin, gateway label, explicit DB size | Tokscale rendering; see [exact contract](tokscale/README.md) |
| Target identity, dated capability/operator/capacity and recovery evidence | Later activation review; claims are not verified by the packet tool |

The bounded [Docker setup route](../validation/README.md#offline-setup-review)
accepts one explicitly prepared, owner-reviewed **nonsecret** JSON file outside
the repository (regular, non-symlink, at most 64 KiB). Once execution is authorized
and Docker already available, it assesses inputs or prints a review packet to
private stdout. It never mounts the file, creates durable output or contacts a
cluster; only a bounded private input snapshot is temporarily staged on the host.
These setup paths have not been verified end to end; record each actual result.

```sh
sh validation/run.sh setup cluster-assess /private/future-cluster.json
sh validation/run.sh setup cluster-packet /private/future-cluster.json
```

The packet's `documents` object contains synthetic `render-target.json`,
`assessment.json`, a hash receipt and, when complete, `tokscale-render-input.json`.
No packet directory or manifests are created. Live context/UID and evidence are
not copied; readiness gates remain false. Keep outputs private: schema validation
does not detect secrets hidden in otherwise valid fields or sanitize real history.
No pullable Tokscale app image is published by this work; a prior local CI image
ID is not a registry reference. Publishing an image needs separate authorization.

Checked-in values are the authoritative Secret/ConfigMap reference inventory:

- [Langfuse](values/langfuse.yaml): bootstrap, PostgreSQL, Valkey, ClickHouse and
  S3 credentials. Buckets/prefixes remain private and separately scoped.
- [Collector](values/collector.yaml): receiver mTLS, exporter CA, explicit private
  trace endpoint and **diagnostic-project** authorization. Ingestion keys are not
  assumed write-only; no headers/keys in logs or Git.
- [Homarr](values/homarr-workload.yaml): independent PVC and encryption key,
  separate from `homarr-management`; do not run the management ESO sequence.
- [Tokscale](tokscale/README.md#configuration-and-rendering): DB, OAuth/session
  secrets and trusted TLS. Issuance, registrations and access grants are not
  performed by rendering. Public test certificates/keys must never be deployed.

Review [version-matched Langfuse setup](https://langfuse.com/self-hosting/deployment/kubernetes-helm)
and owner organization/project/user onboarding before activation; the staged
signup restriction also affects invitations. Keep media/export/paid integrations
off unless separately scoped, and verify hardening rather than applying staging
values unchanged. No real bootstrap credential is generated by this guide.
The checksum-bound chart correction omits media bucket/credential environment
variables while retaining event ingestion. It does not remove existing media or
prove runtime access denial; current render regressions remain **UNRUN**.

## 3. Validate and inspect

The [Docker validation guide](../validation/README.md) owns the reproducible
command and tool/schema locks. Once execution is authorized, run from repo root:

```sh
sh validation/run.sh       # full lint plus both infrastructure contracts/schemas
sh validation/run.sh lint  # independent offline lint and validator unit tests only
```

Both [application](../.github/workflows/application-infrastructure.yml) and
[primary](../.github/workflows/primary-infrastructure.yml) workflows remain paused.
They need read-only repository access/public downloads, not deployment credentials.
The commands below are documented review interfaces, not evidence of execution
or permission to bypass Docker/the pause:

```sh
# Local plan/revision; no network or cluster command.
python3 application-infrastructure/scripts/bundle.py
python3 application-infrastructure/scripts/bundle.py revision
# Explicit public chart downloads, SHA256 checked; no installation.
python3 application-infrastructure/scripts/bundle.py fetch
# Offline renders; choose fresh output directories outside the repository.
python3 application-infrastructure/scripts/bundle.py render \
  --target /private/new-review-packet/render-target.json --output /private/new-render
python3 application-infrastructure/tokscale/render.py \
  /private/new-review-packet/tokscale-render-input.json > /private/tokscale-review.json
python3 application-infrastructure/scripts/resource_report.py /private/new-render/manifests.yaml
```

Rendering needs locked Helm and PyYAML from the validation image. No repo/dependency
update, cluster lookup or install runs. The selected StorageClass is wired to
PostgreSQL, Valkey, ClickHouse, Keeper, SeaweedFS and Homarr for review; this does
not verify that the class exists or meets storage/recovery requirements.
`report.json` binds bundle revision, target
JSON and manifest digests. Generated/cache/private outputs stay out of Git and CI
uploads. Resource totals retain omissions for custom resources and zero replicas;
they do not prove per-node placement, limits, topology or eviction safety.

Check [image locks](image-lock-evidence.md), [ClickHouse candidate contract](clickhouse-operator-contract.md),
all secret references, hooks and permissions. Image-index/platform metadata does
not prove runtime compatibility. ClickHouse custom resources remain deployment
blockers even with pinned images. Operator/cert-manager images need separate pins.
The checksum-bound SeaweedFS template correction suppresses an unused SFTP Secret
before Helm runs; CI rejects nonempty rendered Secrets. Its required bucket hook
is restricted to a dedicated no-token ServiceAccount, but bucket creation still
requires approval. No upstream fix or independent S3 HA is claimed.

**Never apply review output:** only Tokscale forces zero replicas; vendor charts
retain normal workload replicas. Even zero-replica resources mutate network,
storage and permissions. Successful rendering is not deployment consent.

### Optional read-only target preflight — deferred

Only after authorized inspection resumes, use the selected target's **existing
reviewed connection**. Privately copy [target.synthetic.json](fixtures/target.synthetic.json),
supply exact context, namespace/immutable UID, StorageClass and observed version,
and set `synthetic: false`. No new grants or host substitution:

```sh
python3 application-infrastructure/scripts/bundle.py preflight \
  --target /private/approved-target.json --output /private/fresh-preflight.json
```

The UID is checked before other reads. Output is aggregate node/storage/PVC/pod/CRD
status, never Secret contents, raw specs or annotations. No exec/apply/operator
install/port-forward runs; existing kubeconfig authentication may execute its
configured provider. A denied/unavailable command stops inspection. Physical
storage, combined capacity, architecture, access and restore still need evidence;
JSON booleans and healthy pod counts cannot establish them.

## 4. Deployment gates — no apply implementation

`bundle.py deploy` always exits blocked without external actions. The
[disabled deployment design](validation/deploy-workflow.yml.disabled) is not an
active workflow. Before implementing any bounded deployment route:

1. Validate the **final** revision: exact-image/architecture, Collector whole-envelope
   canaries, operator admission, TLS-negative/access-denial, isolated migration and
   restore checks. Tokscale migrates before every server start; rehearse interruption,
   retry and advisory-lock behavior with its existing migration engine.
2. Prepare source + target/namespace UID + manifest/image digests, fresh evidence,
   resource-level credential/network/storage/RBAC changes and rollback boundaries.
3. Obtain exact current owner approval for those actions. A populated file, PR
   merge, hypothetical compatibility or green check is not consent. Stop on target
   or manifest drift, capacity shortfall, TLS failure or recovery uncertainty;
   never weaken controls, regenerate keys, resize storage or switch hosts to proceed.
4. Only after separately approved initial acceptance may a separately approved
   protected CI environment own later rollouts with provenance and drift checks.
   No service, public ingress, source enrollment, reporter, schedule, paid feature
   or new credential follows automatically from deploying the hub.

Native diagnostics, plugin rich traces and bounded historical imports have
**separate source/content gates** in the [telemetry contract](runbooks/telemetry.md).
Logs/metrics remain disabled. Tokscale uses native reporting cadence and an
explicit private endpoint at later enrollment—not a new six-hour collector.

## 5. Recovery and rollback

Before startup/migration, privately record exact source/image/schema versions,
manifest hashes, custodian, encrypted independent destination, retention and
measured recovery objectives. No destination or schedule is invented here.

- Use [engine-consistent backups](https://langfuse.com/self-hosting/configuration/backups)
  for PostgreSQL data/schema/roles and matching ClickHouse,
  Keeper and SeaweedFS object/index procedures—not copies of live PVC directories.
  Preserve queue/replay semantics plus configuration and encryption material.
- Encrypt before transfer with approved tooling/private credential files; no
  passwords in arguments or logs. Same-cluster buckets/snapshots are not recovery.
- Restore in isolation, without real traffic/reporters/OAuth callbacks. Verify
  decryption/checksums, schema/journal, row/object/session IDs, authorization and
  sample reconciliation; measure recoverable point/time. A download/start is not
  a restore. Preserve source backups and evidence.
- Stop only newly approved traffic/reporting/reconciliation within its scope.
  Preserve original histories/attachments, receipts, PVCs, databases and keys.
  Image rollback does not reverse migrations; use a rehearsed forward fix or
  isolated restore/cutover with explicit data-loss approval. Never prune/uninstall,
  delete namespaces/PVCs, truncate logs, rotate keys blindly or overwrite backups.
  Reconcile unknown outcomes before retrying; existing services are not adopted.
