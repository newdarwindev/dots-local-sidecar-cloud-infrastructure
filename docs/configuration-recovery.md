# Configuration recovery and local access

Git is the recovery source for reviewed, nonsecret configuration: chart values,
image and source locks, validation tooling, schemas and recovery instructions.
It is not a database, object-store or secret backup. A local commit is not an
off-machine copy until the remote commit is verified.

## Configuration checkpoint

1. Keep real host inventories, endpoints and activation packets outside this
   public repository. Use the existing generic values and input templates.
2. Review the exact diff and explicitly stage only intended source files. Never
   recursively add system configuration, home directories or generated output.
3. Run the committed Docker validation entrypoint and record its actual outcome.
   A failing check must remain visible; do not describe configuration as tested
   merely because it was committed or uploaded.
4. Commit the reviewed files and push to the authorized repository. Compare the
   remote branch commit with the local commit before claiming a remote backup.
5. Record the configuration commit privately alongside application image digests,
   database schema versions and the independent data-backup reference.

Do not commit kubeconfigs, TLS private keys, tokens, OAuth secrets, database dumps,
session histories or unreviewed encrypted archives. The separate encrypted
configuration snapshot repository is not automatically authorized for new secrets.
Git ignore rules are an accident guard, not a secret scanner or an access policy.

## Initial access without a domain

Use a local-only access design until a private DNS/TLS design exists. Keep
application Services ClusterIP and ingress disabled. Any future port-forward must
bind explicitly to `127.0.0.1`, target a verified context/namespace UID, remain in
the foreground and stop with the operator session. Do not expose a NodePort,
LoadBalancer, public tunnel or wildcard listener as a convenience fallback.

Loopback transport does not waive application authentication, trusted TLS,
Tokscale OAuth callback configuration or machine-ingestion authentication. A
local TLS endpoint and its trust distribution must be prepared and tested before
real-data activation. No domain, credentials or running forwarding process is
created by this document.

## Capacity and recovery gates

As reviewed on 2026-11-05, the upstream Langfuse v4 sizing table lists 4 GiB each
for web, worker and PostgreSQL, 1.5 GiB for Valkey, 8 GiB for ClickHouse and 4 GiB
for self-hosted object storage: **25.5 GiB combined**, before the additional
services and host overhead. This is vendor guidance, not a measurement or a
guarantee of fit. Lower review-manifest requests do not establish a production
capacity exception. See [upstream sizing](https://langfuse.com/self-hosting/configuration/scaling).

The current configured PVC sizes total **199 GiB** for Langfuse PostgreSQL (20),
Valkey (8), ClickHouse (100), Keeper (20), SeaweedFS (50), and Homarr (1), before
Tokscale. With the existing 25% planning allowance that is **248.75 GiB**, still
excluding Tokscale, snapshots, filesystem overhead and retained data. Do not
double-count shared backing disks or treat an unformatted reservation as a
usable StorageClass or as evidence of its encryption state. These totals are a
design check, not a live storage observation. A synthetic-only lab may use the
explicit [unencrypted lab policy](../application-infrastructure/contracts/synthetic-unencrypted-lab.example.json),
but must still verify backing, capacity, RWO semantics and PVC retention; the
profile itself is not target evidence or deployment approval. That profile uses
K3s `local-path` over the ext4 mount at `/var/lib/rancher/k3s/storage`; it is
node-local and PVC requests are not hard quotas, so all claims share filesystem
capacity. It does not meet the generic encrypted-CSI requirement for real data.

Before real-data startup, select an independent encrypted recovery destination,
establish key custody outside the cluster, and rehearse engine-consistent restore.
Until then, retain the deployment gate. A synthetic lab must not receive real
histories, credentials or source telemetry, and must not be presented as
production acceptance. Unencrypted lab data is exposed to offline device access.

## Rebuild sequence

Restore the exact reviewed source commit, validate it, verify target identity
and capacity, then provision the approved cluster/storage/network prerequisites.
Restore secrets from independent custody; restore databases and objects from a
matching consistent checkpoint; verify IDs, authorization and counts in isolation.
Only then reconnect approved sources. Never run a database migration against the
sole backup or assume an image downgrade reverses its schema changes.

The [operator setup guide](../application-infrastructure/README.md) remains the
deployment authority; this recovery procedure adds no automatic apply, scheduled
backup, CI activation or source enrollment.
