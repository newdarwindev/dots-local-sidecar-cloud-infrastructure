# Fleet trust and recovery boundaries (draft)

This is a proposed design, not an installed control. See the [fleet brief](../README.md).

## Authorization and execution

Each existing host needs explicit enrollment and revocation, scoped identity and an approved task boundary. Manual placement names the chosen host. The fleet layer must reject unknown hosts and ambiguous or expired authorization. Agent access to a host does not grant cluster or secret-store permissions. A Linux VM has its own guest boundary and shares its physical host's availability.

Native host work stays on its supported OS. Optional K3s workloads run on eligible Linux hosts or Linux guests. Scope Kubernetes credentials to the chosen cluster and namespace. If chosen, Argo CD reads only reviewed desired state and approved destinations. Homarr is a dashboard, not an authorization mechanism or scheduler.

## Prerequisites and recovery

Privately verify OS/version, CPU architecture, memory, disk, virtualization, power behavior, network reachability and owner consent. Before an optional stack, identify an eligible Linux host/guest, persistent storage and an off-host encrypted backup destination. Define key custody, restore order and acceptable data loss. Test disposable restore and measure recovery time before claiming recoverability. Surface notebook sleep or disconnection as placement failure.

Manual placement and backup do not imply high availability or automatic failover. No control-plane endpoint should be public by default. Credentials, private inventory and backup material do not belong here.

## Separate credential feature

[Issue #2](https://github.com/newdarwindev/dots-local-sidecar-cloud-infrastructure/issues/2) proposes OpenBao delivery, rotation and encrypted browser profiles. None is implemented here. If later authorized, use synthetic secrets to test namespace isolation, rotation after documented refresh/restart, ciphertext-only profile storage and denied unauthorized decryption. Revoking future secret fetches does not terminate a website session; track that separately. Base64 Kubernetes Secret data is encoding, not encryption.
