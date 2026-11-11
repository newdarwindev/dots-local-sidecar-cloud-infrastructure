# Operating entry points by role

This is a navigation guide to the generic implementation, **not a deployment
inventory**. Keep real machine names, private addresses, component measurements,
credentials and acceptance receipts in the owner's private operational overlay.
A published manifest or passing source test does not establish installed state.

## Select the role

| Role | Start here | What to verify privately | Next gate |
| --- | --- | --- | --- |
| Existing application / monitoring hub | [Application setup](../application-infrastructure/README.md), [native monitoring](codex-native-monitoring.md), [Tokscale](../application-infrastructure/tokscale/README.md) | Node/controller readiness; UI TLS/auth; exact machine ingest route; databases/storage; source/version/privacy gates | Independent synthetic persistence, denied-input and outage/replay acceptance, then explicitly scoped real-source use |
| Existing primary management guest | [Primary reference](../primary-infrastructure/README.md), [recovery](primary-recovery.md) | Guest and K3s separately from launcher status; Argo/Homarr readiness; secret-store seal and dependent sync | Owner-controlled unseal where needed; tested startup/login recovery; independent recovery qualification |
| Native workstation telemetry client | [Native integration matrix](codex-native-monitoring.md), [telemetry contract](../application-infrastructure/runbooks/telemetry.md) | Installed source tuple, local receiver, fixed data boundary, exact TLS identity/destination, queue type and persistence scope | Correlate invented IDs at backend; test denials/replay without reading private history |
| Local archive interface | [Application phases](application-phases.md) | Loopback-only UI, explicit source allowlist, no-sync mode, approved import status and coverage | Separate archive/import/recovery authorization; UI success is not archive completeness |
| Unconnected or unqualified host | [Fleet evidence rules](fleet-alignment.md), [inventory template](inventory-template.md) | Actual connectivity, OS/runtime, power and capacity before assigning a role | No enrollment, service start, trust or access changes by inference |
| Future CI capacity | [Placement boundaries](boundaries-and-cloud.md) | Separate runner target, isolation, architecture, repo scope and availability | Separate runner/credential approval; never use the management guest implicitly |

## One private entry page per machine

Record these fields without copying private values into this public repository:

1. Observation time, source/method and unavailable checks.
2. Role and installed/deployed components, with versions and separate health.
3. Exact browser/machine entry point, hostname and client trust; keep UI auth and
   machine ingest identity distinct. Never suggest disabling TLS verification.
4. Startup scope: host boot, user manager, GUI login, guest or manual; distinguish
   configured enablement from an observed recovery test.
5. Installed source revision versus published source, preserving dirty work.
6. Current blockers and ordered next steps, with security, backup, access and
   deployment approvals separated from read-only diagnosis.
7. Links to dated acceptance and existing canonical implementation/runbooks.

A sealed secret store can coexist with a Ready Kubernetes node. A failed startup
job can coexist with a subsequently healthy guest. A TLS address route can work
while an mDNS hostname fails certificate verification. A bound durable-queue
volume does not prove replay or complete delivery. Report each separately.

See the [hub access and recovery handoff](hub-access-handoff.md) for the
current continuation gates and isolated replay test.

## Safe refresh and maintenance

Use bounded read-only inspection first. Preserve unknown/offline states rather
than moving work to another host or copying historical green results forward.
Do not import histories, expose databases, enable CI, install persistent jobs,
start recovery guests or create backups just to produce an inventory.

For documentation-only edits run the committed
[Docker lint and link validation](../validation/README.md). Executable changes
need the applicable full validation scope and separate installed-path acceptance.
Document exactly which checks passed, failed or were not run. Leave owner-paused
workflows paused. This guide installs no agent, watcher or scheduled process.
