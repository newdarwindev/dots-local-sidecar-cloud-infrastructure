# Current application placement and later-stage platform proposals

**Owner-directed draft revision · 2026-11-02. No services changed.** This is the
current phase boundary for the infrastructure documents. Generic reference
manifests remain preserved; their existence does not make their whole bootstrap
sequence the current rollout plan. Exact host mapping and capacity evidence stay
in the private placement overlay.

## Current planned application target

The selected existing Kubernetes target is planned to host:

- Langfuse and its dependencies, OpenTelemetry Collector and S3-compatible storage,
  with the integration, privacy and deduplication gates in the [Langfuse plan](langfuse-plan.md).
- **Tokscale hub and its own PostgreSQL**, moved from the prior candidate placement.
  Reuse upstream reporting and default cadence, not a new six-hour collector.
  Keep Tokscale database ownership and credentials separate from Langfuse's
  PostgreSQL even if a future reviewed topology shares a database server.
- **A target-specific Homarr instance**, `app_id=homarr-workload`, with its own
  database/PVC, encryption-key reference and configuration. This is distinct from
  `homarr-management`, the preserved generic primary-management reference.
  No second physical host assignment or existing-instance migration is implied.

All are **planned, not deployed**. The selected target must pass one combined
resource/storage budget including existing workloads, both application databases,
Homarr, Collector, object storage and indexing/queue headroom. Do not infer fit
from physical disk size or budget each component as if it owns the entire host.
No repartition, resize, power change, workload move or alternate host substitution
is authorized by this document.

Tokscale requires reviewed authenticated submission and protected read surfaces;
set the private hub endpoint explicitly for scheduler invocations. Preserve stable
device IDs, native cadence, aggregate-only collection and duplicate-history rules.
No scheduler is activated. For a Kubernetes destination, translate and review the
upstream application contract and durable PostgreSQL deployment before activation;
no working chart/manifests or successful migration are claimed here.

## Later-stage proposals, not immediate rollout dependencies

| Area | Later-stage direction | Current boundary |
| --- | --- | --- |
| Shared human identity | Authentik is the **preferred proposal**; native OIDC where supported and reviewed proxy integration elsewhere | Not installed, not an immediate prerequisite implying permission to deploy it; live compatibility/access migrations remain unverified |
| Central secret management | OpenBao plus narrowly scoped ESO integration | Existing generic reference files are preserved, but centralized bootstrap, unseal, policies and synchronization are deferred proposals |
| Domains / shared ingress / certificates | Canonical private app names and a reviewed certificate strategy | Proposed catalog only; no DNS, trust-store, ingress or public exposure changes |
| Unified auth integration | App-specific roles, MFA, offboarding and machine identities | Future migration plan; do not imply local authentication is disabled or every app already shares SSO |

**Deferring these platform systems does not defer baseline security.** Before any
application is activated, provide a reviewed secure local bootstrap: authenticated
administration, restricted private/loopback access, approved encrypted secret
custody, minimum machine permissions, TLS wherever traffic crosses its approved
local boundary, backup/recovery and explicit owner activation scope. No plaintext
secrets in Git, logs or public manifests; no default passwords, anonymous APIs or
publicly readable usage data. If a safe baseline is unavailable, deployment stays
blocked rather than bypassing it until the future platform exists.

The current generic Homarr reference depends on ESO/OpenBao for its encryption
secret. **Do not run that sequence as-is for the new instance.** A later reviewed
implementation must supply the same required application secret through an
approved independent bootstrap mechanism without weakening its handling. Do not
edit manifests or fabricate an ExternalSecret merely to make the draft appear
ready. Preserve existing encryption keys and all original histories.

## Sequence and evidence

1. Refresh the selected target's inventory, cluster ownership/readiness and actual
   RAM/storage availability. Agree a sustainable combined capacity solution.
2. Review app-specific versions, storage ownership, secure local bootstrap and
   independent encrypted backup/restore. Keep current data and services intact.
3. Stage and validate isolated target-specific application configuration with
   synthetic data; keep activation a separate scoped decision.
4. Only later revisit the [auth/domain proposal](auth-domain-plan.md), OpenBao/ESO
   and their independent recovery design. Test authorization equivalence and
   rollback before replacing local gates or migrating secrets.

The [primary reference runbook](../primary-infrastructure/README.md) remains useful
implementation history/scaffolding, not a competing current deployment mandate.
The private overlay owns current placement; archived original-context documents
are preserved unchanged and do not override this phase decision.

## Executable staging bundle

The [application bundle](../application-infrastructure/README.md) adds checksum-
locked chart rendering, explicit-target read-only preflight, synthetic telemetry
contracts and Docker CI. It does not activate applications or resolve the private
capacity/access/recovery gates. Actual deployment remains disabled pending the
initial owner-approved resource-level change and subsequent reviewed CI enablement.
