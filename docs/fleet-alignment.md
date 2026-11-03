# Private target evidence and enrollment

Use [application setup](../application-infrastructure/README.md) for the current
selected workload. Actual host names, access, measurements and placement stay in
the private inventory/overlay; the [blank template](inventory-template.md) is not
an expected fleet size or authorization to discover/enroll additional machines.

Record each component with dated source, collection method, visibility limits and
blocking gates: **discovered → observed → candidate → approved → staged → verified
deployed → recovery verified**. “Reported active” is a dated claim, not verified
health. A CLI, connection, repository, manifest or green CI is not a running app.
Preserve conflicting/prior evidence and distinguish owner reports from inspection.

- Existing Kubernetes ownership/workloads are preserved, not replaced to match a
  template. No broader access, host substitution, demo placement or implicit jobs.
- Linux-only K3s uses verified Linux hosts/guests; macOS/ordinary Windows notebooks
  are not native K3s nodes. Check runtime, image architecture, networking, resources
  and awake/restart availability; preserve immutable OS bases and concurrent work.
- Count physical storage once, including shared filesystems/thin pools/snapshots;
  assess actual data/metadata/root headroom. GPUs need separate driver/passthrough/
  plugin proof, not inference from the device name. Sleeping laptops are unavailable.
- Management/workload credentials stay separate. Co-located guests share hardware
  failure; cloud extension is [separately scoped](boundaries-and-cloud.md), not HA
  or automatic failover. Do not migrate secrets/data because a host is asleep.
- Usage reporters need no Kubernetes; hub databases need their own allocation.
  Preserve stable IDs, native cadence and duplicate-history controls. Each telemetry
  source follows [content/coverage gates](../application-infrastructure/runbooks/telemetry.md).

Only exact-current activation approval plus target-specific health, denial,
restart and isolated restore evidence establishes a deployment. Preserve all
original Tether/chat/decision/session histories and receipts through rollback.
