# OpenTelemetry implementation design — selected cluster

**Current phase boundary:** see [application phases](application-phases.md). Shared
Authentik/OIDC, OpenBao/ESO and domain integration are later-stage proposals;
reference sequences below are not immediate rollout instructions. Secure local
bootstrap, private authenticated access and encrypted secret custody remain
mandatory before any separately approved deployment.

**Draft only · 2026-11-02.** The owner selected native Codex OTel, the community
historical importer and official Codex plugin, with Langfuse, Collector and
S3-compatible storage on the same existing Kubernetes cluster. Exact host identity
and verification gates stay in the private placement record. This document is an
implementation design. The later [staged application bundle](../application-infrastructure/README.md) adds offline chart values and synthetic contracts, not production acceptance: **no collectors, hooks, exporters, credentials or schedules are installed or enabled**. See the
[Langfuse plan](langfuse-plan.md) for content consent, canonical usage ownership,
historical/live cutover, preservation and resource gates.

## Components and flow

Plan a dedicated namespace and private Collector **gateway Deployment**, not an
unrequested privileged per-host DaemonSet. Use the reviewed upstream Collector
Helm chart/distribution after pinning its version, digest and included components.
A host-side allowlist adapter is required wherever native emissions contain fields
outside the approved schema; it is design work, not a claimed built-in privacy
flag. Rich plugin and historical importer content follow their own explicit gates.
Do not assume either producer can route through the Collector without testing its
actual exporter and authentication support; their supported Langfuse ingestion
path may remain direct.

| Signal / producer | Cluster processing and destination | Canonical accounting role |
| --- | --- | --- |
| Native Codex traces | Authenticated OTLP receiver → memory bound → approved field filtering/transform → batch → Langfuse **diagnostic project**, HTTP traces endpoint | Diagnostic, excluded when another producer owns session usage |
| Native Codex logs | Distinct logs pipeline → approved structured-log backend, selection pending | Not Langfuse trace payloads; no raw prompt/tool/error content by default |
| Native Codex metrics | Distinct metrics pipeline → approved metrics backend, selection pending | Operational counters, not duplicated token billing |
| Official Codex plugin | Supported Langfuse path to canonical rich-session project after opt-in | Future enrolled sessions assigned to plugin |
| Community importer | Bounded reviewed export to canonical historical project/ownership namespace | Approved historical sessions only; no watcher |

Logs/metrics backend selection is genuinely pending. Keep those exporters and
source collection **disabled until approved destinations exist**; no debug/stdout
fallback of potentially sensitive payloads, and no claim of full signal collection.
A raw S3 bucket is not automatically a queryable logs/metrics backend. Object
storage on the selected cluster is initially Langfuse's private dependency, not a
reason to archive every fleet log there.

## Configuration contract to render after version selection

The [Collector configuration model](https://opentelemetry.io/docs/collector/configuration/)
separates receivers, processors, exporters, extensions and enabled service
pipelines. Defining a component does not enable it; include only approved signal
pipelines. Validate the final rendered configuration with that exact Collector
binary in the established container-only validation path before deployment.

| Boundary | Planned implementation / acceptance |
| --- | --- |
| Receiver | Explicit OTLP HTTP bind/port (conventional 4318), private Service/ingress only; enable gRPC 4317 only if a verified source requires it. TLS plus mTLS or a reviewed supported authenticator, never anonymous network-wide ingest. Private DNS alone is not authorization. |
| Codex source | Check exact installed config schema: `otel.exporter` is logs, `otel.trace_exporter` is traces, `otel.metrics_exporter` is metrics. Configure only approved signals/endpoints; do not point the log exporter at the Langfuse traces API. |
| Processors | Memory limiter before transformation/batching; allowlist resource, span, event and log-body fields before transport and again at gateway. Drop unknown/private attributes, not only recognizable token strings. Preserve root/parent IDs and explicitly permitted session metadata. |
| Langfuse exporter | OTLP **HTTP** JSON/protobuf, trace-specific `/api/public/otel/v1/traces`; generic OTLP base `/api/public/otel` only when exporter appends the signal suffix. Confirm exact exporter component identifier in pinned distribution. Langfuse does not accept OTLP gRPC or log/metric payloads. |
| Exporter auth | Langfuse project public/secret key Basic authorization from approved secret injection, not hardcoded. For supported v4 ingestion send `x-langfuse-ingestion-version: 4`. No headers in diagnostics/Git. Reject wrong project/key and revoked credentials in synthetic tests. |
| Queue/retry | Bounded queue/backoff, explicit disk budget if persistent queue is selected, encrypted storage and private checkpoints; define outage/overflow behavior and alert. Avoid unbounded disk growth. Record gaps; never silently call dropped data complete. |
| Health/admin | Health endpoint restricted to approved probes; no public pprof/zpages/debug exporter. Collector own metrics are operational, not Codex content; verify their destination separately. |
| Network policy | Only approved sources to receiver; gateway to selected Langfuse and approved signal backends; deny unnecessary egress. Kubernetes RBAC scoped to necessary resources, no cluster-admin or host filesystem mounts for telemetry convenience. |

Source references: [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference),
[Codex OTel](https://github.com/openai/codex/blob/main/codex-rs/otel/README.md),
[Langfuse OTel](https://langfuse.com/integrations/native/opentelemetry),
[Collector Helm deployment](https://opentelemetry.io/docs/platforms/kubernetes/helm/collector/).
These upstream interfaces must be checked against pinned artifacts; this table
is not copy-paste executable configuration or a successful compatibility test.

## Planned implementation increments

1. Verify selected cluster inventory, access, versions, capacity and existing
   ownership without changes. Reserve distinct data/PVC budgets and establish an
   encrypted backup outside this cluster/failure domain.
2. Pin Langfuse/Collector/chart/dependencies and select supported receiver
   authentication. Produce reviewed Helm values, NetworkPolicies, secret-reference
   placeholders, storage definitions and container-only synthetic validation.
   Review any cluster-scoped CRDs separately. No secrets in manifests.
3. Render Collector **trace-only** pipeline first with synthetic metadata, not
   real session files. Assert secret canaries cannot reach the gateway or hub;
   inspect the complete exported envelope, not just selected UI fields.
4. Test two-turn session, tool failure, child session, resume/cancel, restart,
   retry and offline recovery. Verify trace lineage, timestamps and counters;
   native OTel is not full replay and plugin failure-open is not an audit guarantee.
5. Assign canonical producer/cutover in the private ledger. Test one approved
   plugin session and one bounded historical fixture; replay/import overlap twice
   and assert one canonical token total per source turn. Diagnostic project totals
   stay separate; preserve unavailable usage as unknown.
6. Add logs and metrics only after backend/security/retention choices are approved
   and their independent pipelines pass fixtures. Expand hosts/surfaces only with
   explicit evidence and source/content scope, not a blanket all-account scan.
7. Validate isolated restore, key revocation and enrollment disable/rollback.
   Rollback stops new telemetry; it does not delete original histories, PVCs,
   attachments or receipts. Confirm no raw secrets in operational reports.

Same-cluster S3, databases and replicas share failure risk. Test recovery with the
whole target cluster assumed unavailable. No off-host backup destination, RPO/RTO,
production availability or full fleet coverage is asserted until measured.
