# Bounded synthetic lab

This is an explicit setup path for an owner-authorized single-node lab. Keep
target context, cluster UID and receipts privately. The production bundle's
deployment gate remains independent.

The foundation creates `dots-synthetic-lab`, an 80-GiB requested-storage budget,
6-GiB memory request budget, 10-GiB memory limit budget, retained local-path storage,
default resource limits and network isolation. Pods can communicate within the
namespace and resolve cluster DNS. The selected ClickHouse operator controller
can reach only its server native-control port 9001 and Keeper port 2181; other
cross-namespace pod ingress/egress is denied. These ports match the reviewed
operator source and observed replica-probe behavior. Actual
physical storage and CNI enforcement must be checked separately. Local-path
claims share backing capacity and have no hard filesystem quota.

After Docker validation and review, use the exact existing target context and
its observed `kube-system` namespace UID:

```sh
sh application-infrastructure/lab/foundation.sh PRIVATE_CONTEXT PRIVATE_CLUSTER_UID
```

The script checks cluster identity before dry run and apply and refuses to adopt
unlabeled existing namespace/storage resources. It does not format disks, start
apps, expose a port, enroll a source, or delete storage. Review both source and
server dry-run output before any later application installation. Keep retained
PVCs and PVs after stopping lab pods. Real-data startup requires the full operator
access, encryption and recovery checks.

## Live checks and application setup

Run `check.sh CONTEXT KUBE_SYSTEM_UID` after the foundation. It creates three
named probe pods (one in `default`), verifies internal connectivity, denied
cross-namespace ingress/egress and retained-volume write/read, then removes its
pods. The test PVC and invented marker are retained. Existing probe pods cause a
stop for reconciliation. Policy objects alone do not prove CNI enforcement.

After Docker validation, prepare a mode-0700 directory outside Git and run:

```sh
docker run --rm --read-only --user "$(id -u):$(id -g)" \
  --cap-drop=ALL --security-opt=no-new-privileges --memory=2g --cpus=2 \
  --tmpfs /tmp:rw,nosuid,nodev,size=1g \
  -v /PRIVATE/LAB_STATE:/output --entrypoint python infrastructure-validation:local \
  application-infrastructure/lab/render.py \
  --output /output/NEW_RENDER --kubernetes-version OBSERVED_VERSION
```

Review `lab.yaml` and its receipt. The renderer verifies locked images and resource
boundaries, removes empty vendor Secret placeholders, sets resource limits and
Recreate Deployments, and reduces six PVC requests to 43 GiB: PostgreSQL 8, Valkey
2, ClickHouse 20, Keeper 2, SeaweedFS 10 and Homarr 1. The retained probe adds 1 GiB.
Operator/system overhead and actual shared-filesystem growth need measurement.

Use the observed lab namespace UID and cluster UID. Generate fresh lab-only keys
once, privately; an existing key or private directory stops generation without
rotation. These service keys are independent of real user/source/OAuth credentials:

```sh
sh application-infrastructure/lab/bootstrap.sh PRIVATE_CONTEXT PRIVATE_CLUSTER_UID \
  PRIVATE_NAMESPACE_UID /PRIVATE/NEW_LAB_KEYS
sh application-infrastructure/lab/start.sh PRIVATE_CONTEXT PRIVATE_CLUSTER_UID \
  PRIVATE_NAMESPACE_UID /PRIVATE/NEW_RENDER/lab.yaml REVIEWED_MANIFEST_SHA256
```

The start script verifies both UIDs and manifest hash before server dry run and
apply. Keep generated keys and receipts outside Git. Observe pod/operator health,
memory peaks and disk growth. The lab exposes no UI port or ingress, configures no
real user account and enables no Collector source or Tokscale reporter. Prepare
trusted authenticated local TLS before browser use. Real-data startup requires
the complete operator encryption, access and independent recovery checks.

Pause only the reviewed lab workloads and preserve all PVCs, operator CRs, keys
and receipts. Do not uninstall the lab or delete its namespace as a rollback.
