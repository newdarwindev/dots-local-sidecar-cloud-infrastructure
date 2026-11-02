# Primary macOS host rollout

Status: staged plan, 2026-11-01. No cluster, Homarr, OpenBao, or continuous
deployment is installed or verified by this change. This public repository holds
architecture and [staged generic implementation](../primary-infrastructure/README.md).
Live host inventory, sensitive settings and operational decisions stay private;
reviewed generic desired state is stored here. Publication does not activate it.

## Preserve the existing architecture

Use the primary Mac as the physical host for Linux ARM64 guests. K3s does not run
natively on macOS. Keep the management and workload cluster credentials separate;
co-location does not provide hardware failure isolation. Start with management
only, and defer workload enrollment until management recovery works. Do not
substitute a dashboard demo for Homarr or start unrelated demo services.

The existing proposal selects K3s with embedded etcd, Argo CD, OpenBao and
per-destination ESO. Crossplane and cloud providers are later stages requiring
their own approved identities and resource scopes. Issue #1 adds Homarr to the
small-stack discussion; issue #2 tracks OpenBao delivery and rotation. Neither
issue supplies executable deployment manifests.

## Bootstrap order and acceptance

1. Record the intended host, runtime, available resources, sleep behavior and
   concurrent jobs privately. Choose an existing supported Linux VM runtime or
   obtain approval for an additional runtime. Review licensing before activation.
   Reserve resources for ongoing jobs; do not reboot or change sleep settings as
   an incidental installation step. Agree an availability window before claiming
   this is a continuously available primary host.
2. Prepare reviewed desired state: exact repository and branch, image/chart
   versions and digests, ARM64 support, VM storage, non-overlapping CIDRs and
   backup destination. Review rendered resources before applying them. This
   public repository is the source for reviewed generic manifests only; private
   settings and host/recovery records must remain outside it.
3. Obtain action-time approval for cluster credentials, Linux guest networking,
   controller permissions, persistent repository access and local UI endpoints.
   Keep an explicit inventory of each generated identity and its revocation path.
4. Bootstrap one Linux management server with pinned K3s, embedded etcd and
   Kubernetes Secret encryption at rest. Secure the owner-held kubeconfig and
   matching server token outside Git. Keep API access private; do not open host
   firewall rules or publish ingress implicitly. Verify node readiness, storage,
   DNS and an isolated restart before adding services.
5. Install pinned OpenBao using its supported Helm chart, persistent storage and
   TLS. Avoid development mode. Initialize only under an approved owner-held
   recovery process; never emit root/unseal material into agent logs. Establish
   encrypted off-host recovery before storing real credentials. Bootstrap and
   recovery must work without ESO.
6. Install pinned Argo CD. Scope an AppProject to the approved repository, destination and resource kinds;
   set each Application’s desired-state targetRevision to the approved branch. Bootstrap with manual synchronization.
   Configure annotation resource tracking before Crossplane integration. A
   repository read identity must not have write/admin access. Do not install a
   broad self-hosted CI runner to obtain deployment access.
7. Install Homarr from the official chart, with persistence and an approved
   database encryption secret. Prefer a ClusterIP service and explicit loopback
   port-forward for initial access, without public/LAN ingress or Docker socket
   mount. Confirm chart-supported secret references for the pinned chart. Keep
   integrations and third-party account capture disabled until separately scoped.
   Reconstruct the prior manual bookmark mapping and verify links; it is not a
   supported bulk import. Back up the database and encryption key separately.
8. Configure ESO only after approval of the exact OpenBao auth role, policy,
   namespace and secret paths. Prove rotation and denial using synthetic secrets;
   revocation blocks future fetches but does not revoke external sessions or erase
   already materialized Kubernetes Secrets. Record refresh/restart behavior.
9. Enable Argo CD automatic synchronization only for reviewed desired state after
   successful manual sync and rollback. Initially leave automatic pruning off.
   Prove a harmless approved Git change reconciles, unauthorized destinations are
   refused, and a reverted change reconciles. Record source commit and observed
   health privately. Configuration alone is not continuous deployment evidence.

## Recovery and rollback

Before real state, define an encrypted off-host backup destination and perform an
isolated restore drill. Cover etcd plus matching K3s token; OpenBao storage and
separate recovery material; Homarr database, encryption key and configuration;
and any private configuration required in addition to the public manifests. A Git checkout alone cannot restore application data.
Measure backup age, recovery duration and actual data loss before setting RPO/RTO.

For a failed rollout, disable Argo CD reconciliation first, close explicit port
forwards, and stop only the new guest/services. Retain disks, PVCs, snapshots,
credentials needed for recovery, and all audit evidence. Revoke only newly issued
deployment credentials when authorized. Do not use chart uninstall or volume
deletion as a generic rollback: that can remove persistent state. Never delete,
truncate or destructively rotate Tether logs, decision logs or chat histories.

## Evidence required to call the host deployed

- Running Linux management node with explicit tested version and resource limits.
- Healthy OpenBao, Argo CD and Homarr; secrets excluded from Git and logs.
- Successful approved Git reconciliation, denial and rollback observations.
- Homarr access and bookmarks verified on the intended host.
- Restart and off-host restore verified without disturbing unrelated jobs.
- Explicit availability limitations and unimplemented components recorded.

Until these checks pass, report each component as staged, blocked or unverified.

## Sources

- [Existing architecture](../README.md) and [trust boundaries](boundaries-and-cloud.md).
- [Placement and Homarr handoff](https://github.com/newdarwindev/dots-local-sidecar-cloud-infrastructure/issues/1).
- [OpenBao delivery and rotation scope](https://github.com/newdarwindev/dots-local-sidecar-cloud-infrastructure/issues/2).
- [K3s requirements](https://docs.k3s.io/installation/requirements).
- [Homarr Helm installation and secrets](https://homarr.dev/docs/getting-started/installation/helm/).
- [OpenBao Helm installation](https://openbao.org/docs/platform/k8s/helm/).
