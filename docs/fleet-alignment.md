# Fleet alignment and enrollment

**Planning only · 2026-11-02.** No host enrollment or runtime changes. Actual
hostnames, capacity, security observations, addresses and placement decisions
remain in the private inventory and its current placement matrix. This document
is the generic contract, not a second copy of that inventory.

## Evidence, not assumptions

| State | Minimum evidence | Does not imply |
| --- | --- | --- |
| Discovered | Stable private identity and dated source | Access, ownership of workloads, or permission to modify |
| Observed | Dated measurements with collection method and visibility limits | Current capacity or deployment health |
| Candidate | Proposed role with resource and dependency budget | Approved placement or unattended availability |
| Approved | Exact current scope, host, versions and rollback reviewed | Execution or success |
| Staged | Reviewed configuration and validation results | Installed runtime |
| Reported active | Service state from a named dated source | Ready Kubernetes nodes or healthy application |
| Verified deployed | Target-specific health, access and acceptance observations | Future availability or recovery coverage |
| Recovery verified | Isolated restore with measured loss/time | HA or unrestricted failover |

Keep these labels per component; a host can have an existing reported service
while the new management stack remains staged. Record conflicting or newer
observations as dated updates, never silently replace their provenance. An
installed CLI, available connection, mounted directory, repository or passing CI
is not proof of a running application. Demo repositories stay outside platform
placement unless separately reviewed; a demo scheduler is not fleet infrastructure.

## Placement contract

1. **Management:** one reliable Linux server or Linux guest, separate credentials
   from workload clusters. The staged macOS guest is an initial reference, not an
   automatic match to a similarly named computer. Establish identity, resource
   reservations, awake window, restart access and off-host recovery first.
2. **Existing Linux Kubernetes:** inspect health, ownership and workloads before
   considering enrollment. Never replace an existing cluster to match a template.
   Do not infer cluster membership or control-plane role from an active service.
3. **macOS / Windows:** use a verified Linux guest/runtime; native desktop OSs are
   not K3s nodes. Check architecture-specific images, VM memory/disk reservations,
   guest networking and restart behavior. Client installations are insufficient.
4. **Immutable Linux:** preserve the OS base; evaluate supported user-space or
   guest options before assigning infrastructure roles.
5. **Storage:** count physical backing capacity once. Shared APFS/Btrfs free space,
   thin volumes and loop devices are not independent capacity. Confirm thin-pool
   data/metadata headroom and snapshot growth before persistent workloads.
6. **Usage reporting:** prefer native supported reporters with stable device IDs,
   authorized data roots and duplicate-history controls. A reporter does not need
   Kubernetes. A usage hub/database needs its own durable resource allocation;
   management VM capacity is not implicitly spare workload capacity.

## Enrollment and expansion gates

- Refresh dated inventory; preserve prior observations and distinguish direct
  inspection from owner-supplied output. Never enroll unobserved machines by name.
- Verify runtime access, architecture, workload headroom, storage ownership and
  power/network availability without changing existing jobs or services.
- Select private placement and data classification; review the
  [auth/domain plan](auth-domain-plan.md) and required service identities.
- Obtain bounded activation approval, then follow the
  [primary bootstrap and recovery sequence](primary-host-rollout.md). Do not
  widen controller roles, firewall exposure or secret paths to make a test pass.
- Require per-application access/denial tests, backup/restore and restart evidence.
  Only then consider workload enrollment, automation or additional cloud targets.

A sleeping laptop is unavailable, not a reason to silently replicate secrets or
move private state to another machine. Preserve all original Tether, decision and
chat histories through every archive, migration or rollback. Record unmet gates
and unknowns rather than presenting staged manifests as a fleet deployment.
