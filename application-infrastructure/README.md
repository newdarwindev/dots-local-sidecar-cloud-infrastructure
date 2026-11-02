# Staged application bundle — executable, not activated

**CI paused by owner:** the latest strict-TLS and structured ClickHouse image
changes are statically reviewed but **untested**. Both GitHub workflows remain
disabled for budget. Last fully green revision: `8659b0d` (44 tests, locked chart
rendering, exact Collector configuration validation and Tokscale AMD64 image
build/smoke). That result does not validate the newer patch.

**Implemented:** checksum-locked chart fetch/render, explicit-target read-only
preflight, rendered-resource risk inspection, synthetic metadata/ownership
harness, dedicated workload Homarr values, and Docker-only CI validation.
**Not deployment-ready:** actual apply is intentionally unavailable. Publication,
passing CI, an approval file, or a selected host does not authorize deployment.
No service, credentials, source collector, schedule or access route is enabled.

This implements the [application phase boundary](../docs/application-phases.md),
not the older primary-management bootstrap. Authentik, OpenBao/ESO, shared domains
and ingress remain later-stage. Exact host identities, measured capacity,
connection details and custody stay in the private overlay.

## Safe commands

From the repository root:

```sh
# Default: pure local plan, no network/cluster commands.
python3 application-infrastructure/scripts/bundle.py
# Hash all reviewed bundle inputs (excluding runtime/rendered/cache).
python3 application-infrastructure/scripts/bundle.py revision
# Explicit public chart download only; verifies SHA256, installs nothing.
python3 application-infrastructure/scripts/bundle.py fetch
# Offline Helm render with a clearly synthetic target, no cluster connection.
python3 application-infrastructure/scripts/bundle.py render \
  --target application-infrastructure/fixtures/target.synthetic.json \
  --output /tmp/staged-render-UNIQUE
```

Rendering requires Helm from the existing checksum-locked primary-infrastructure
validation image and PyYAML. Do not install/start Docker or another runtime merely
to bypass unavailable validation. The committed
[workflow](../.github/workflows/application-infrastructure.yml) runs validation
inside Docker on a hosted runner with **read-only repository permission and no
deployment credentials**. It checks both contracts and chart rendering; passing
means staging works, not that images ran or production readiness was established.
Local unit tests and chart checks must use this Docker workflow too.

Render output is written once to a fresh mode-0700 directory. `report.json` binds
bundle revision, complete target JSON digest and manifest digest. Every unresolved
resource/production gate is reported, including unpinned images. No generated
output is checked into Git or uploaded by CI. Helm runs without repo updates,
cluster lookup, dependency updates, release installation or automatic upgrade.

## Read-only live preflight

Only when the selected target has an **existing authorized connection**, copy the
synthetic target contract into private mode-0600 storage outside the repository;
supply real context, namespace and immutable namespace UID, approved storage
class, observed Kubernetes version, and `synthetic: false`. The UID is an explicit
cluster binding, not a substitute for matching the selected host. Use only its
existing kubeconfig; do not create grants or switch to another available host.

```sh
python3 application-infrastructure/scripts/bundle.py preflight \
  --target /private/approved-target.json --output /private/fresh-preflight.json
```

The command checks namespace UID before further reads, then reads nodes, storage
classes, namespace PVCs, pod status and CRDs with timeouts. It writes only aggregate
counts/readiness, not raw pod specs, annotations, names or credential output. It
never reads Secrets, execs into pods, applies objects, installs operators or starts
port forwards. An unavailable command/permission stops inspection; it does not
retry with broader access. `kubectl` may use the existing kubeconfig's configured
auth provider, so only use an already-reviewed connection.

**Still manual evidence:** physical storage backing/encryption, thin-pool/root
headroom, available RAM and existing workload reservations, dependency image
architectures, all required operator prerequisites, protected access, encrypted
independent recovery and tested restore. Aggregate pod health is not a combined
resource budget. Existing capacity constraints remain blockers until measured and
resolved through separately approved changes. Do not infer free capacity from
physical disk size, substitute another host, resize/repartition, change swap,
move workloads or fabricate readiness from a JSON boolean.

## Components and unresolved production gates

| Component | Staged artifact | Before actual deployment |
|---|---|---|
| Langfuse and dependencies | Vendor chart lock + explicit values | Verify all image digests/architectures; review dependency PVCs, resource budget, operator/CRD permissions and existing secret references; synthetic ingestion and isolated restore |
| SeaweedFS | Provisional chart dependency | Validate private bucket credentials/scopes, approved bucket provisioning, S3 compatibility and off-cluster encrypted recovery; renderer deterministically patches vendor-required bucket hook to the dedicated no-token ServiceAccount; not independent HA |
| OTel Collector | Trace-only mTLS values | Exact-binary config validation, TLS/private ingress and scoped diagnostic-project credential; source-side envelope adapter and live canary tests; logs/metrics disabled |
| Tokscale + dedicated PostgreSQL | [Build/staging contract](tokscale/README.md) | Source/image build, database migration/recovery and authenticated browser/read surface with tested narrow machine route; no scheduler |
| Homarr workload | Independent chart values | Own PVC/encryption key, private authenticated onboarding, approved storage class and backup; no dependency on deferred ESO |

All database/storage/network/permission creation needs explicit action scope.
Resource requests in checked-in values are staging inputs, not a measured fit.
No plaintext secret values, browser credentials, real source content, source
history reads, plugin hooks, importer watcher, public ingress or paid services are
included. Ingestion project keys are not claimed to be write-only.

## Telemetry: offline contract, not a live exporter

`telemetry.py` rebuilds a complete synthetic envelope from a positive typed
allowlist. Unknown names, bodies, events, paths, model/job labels and nested
attributes are not copied. It validates immutable explicit session ownership:
importer owns explicitly assigned completed pre-cutover sessions; plugin owns
assigned post-enrollment sessions; spanning sessions are held. Replays are
idempotent in the **in-memory synthetic harness**, conflicts are rejected, and
native diagnostic usage is removed. Missing usage remains unknown; cumulative
snapshots are not silently summed.

This is **not** a production source adapter, real OTLP semantic mapping, durable
ownership/delivery ledger, content classifier or cross-host enrollment system.
Marking input `synthetic: true` cannot prove that it contains no real data. Only
use newly created fixtures; never supply histories to this harness. A real
adapter must pass full-envelope canary/lineage tests and delivery reconciliation
before any source activation. Plugin rich content and importer history remain
separately disabled; native diagnostics never become canonical token accounting.

## Initial deployment, subsequent CI and rollback

`bundle.py deploy` **always exits blocked without running any external command**.
The [disabled deployment design](validation/deploy-workflow.yml.disabled) is not
an active workflow. This is intentional: essential live values, capacity solution,
image manifests, independent recovery, secure custody and access proofs are not
available yet. No approval token string or file can bypass this boundary.

After those gates are proven, present the owner a concrete revision + target +
manifest SHA256 review packet and resource-level change list. Initial owner
approval must separately cover credentials, network, storage and permissions
actually needed. Then implement/review the bounded apply route and protected
CI environment; only the approved scope may become CI-driven. Require matching
artifact provenance, fresh target identity and plan drift checks on each run.
Do not treat a populated file, PR approval or CI green result as deployment consent.

Rollback planning preserves original logs/history, PVCs, database state, encryption
keys and receipt ledgers. Stop newly enrolled telemetry or disable reconciliation
only under its approved scope. Do not uninstall, prune, delete namespaces/PVCs,
truncate logs or assume image downgrade reverses database migrations. Existing
services are not adopted or interrupted by this staging bundle.

**Raw-render warning:** only the Tokscale review renderer forces zero replicas.
Vendor Helm render outputs retain their chart workload replica defaults; they are
not a safe no-op to apply manually. Rendering also describes PVCs/permissions and
network-relevant resources. No output is authorized for `kubectl apply` or Helm
installation, regardless of a successful staging check.


### Reviewed vendor-template correction

The locked SeaweedFS chart emits an unused SFTP Secret whenever all-in-one mode
is enabled, even when SFTP is disabled. The runner verifies the original archive
SHA256 and the exact SFTP template SHA256, then narrows that single condition to
`allInOne.sftp.enabled` **before Helm evaluates any template**. Both SFTP flags
remain explicitly false. A changed/missing template fails closed. The original
archive is preserved; only a local deterministic derivative is used. CI rejects
any nonempty rendered Secret. This is a reviewed local vendor correction, not a
claim that the upstream chart has fixed it. No real service credential is supplied.

## Hypothetical future-cluster contract (new, untested)

The owner deferred live inspection and permits design against a compatible future
cluster—not a readiness assertion. See [the activation/recovery handoff](runbooks/future-cluster-activation.md),
[JSON schema](contracts/future-cluster.schema.json), and [essential-input template](contracts/future-cluster.example.json).
`cluster_contract.py` can prepare private synthetic render inputs once essential
values exist; it never executes rendering or enables deployment.
`resource_report.py` estimates declared requests with explicit omissions and never
approves fit. All new tests remain unrun with CI paused. Browser-runtime acceptance
is a separate repository contract; generic cluster capabilities do not prove its
lifecycle/lease fencing.
