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

## Manual placement and acceptance plan

This reconciles the earlier fleet brief with the selected application bundle.
Native agents may perform supported tasks on individually authorized macOS,
Windows or Linux hosts; they do not require Kubernetes. Container placement uses
an explicitly approved compatible runtime. K3s is Linux-only, including Linux
VMs on other host operating systems. A guest shares its physical host's power,
storage and availability. Homarr displays approved service links; it is neither
an authorization mechanism nor a scheduler.

Before execution, record the selected host/guest alias, supported OS and CPU
architecture, task scope, authorization expiry and revocation procedure privately.
Reject unknown hosts and ambiguous, expired or out-of-scope requests. Existing
agent access does not grant cluster, secret-store or other-host permissions.
Do not silently move work when a host sleeps or disconnects.

The current workload selection is not reopened by this plan. Before adding a
host, choose native execution or an eligible Linux guest, identify any separately
approved infrastructure prerequisites, and record the recovery boundary. Optional
management components and cloud expansion remain deferred; a planning decision
or successful source validation does not authorize installation or activation.

Use synthetic tasks/data for the following proposed acceptance checks, only
within exact current owner authorization. These are requirements, not recorded
passes or permission to run backups or restore work:

1. **Placement and denial:** Manually select an authorized host for a harmless
   task. Verify it executes only there. An unknown host, expired grant or
   cross-host request outside scope must fail without fallback execution.
2. **OS and interruption:** Record supported OS/architecture and agent/runtime
   versions. Verify Linux guest placement where required. A sleeping,
   disconnected or unsupported target must report unavailable, not migrate.
3. **Optional components:** If separately approved, verify the chosen cluster,
   Argo CD repository/destination scope and Homarr links. Opening the dashboard
   must not create workloads, acquire credentials or expand access.
4. **Recovery:** Before stateful work, identify data, destination class, key
   custody, acceptable data loss and restore order. Obtain explicit approval
   before creating a backup or performing a restore. Use a separately approved
   disposable target, compare synthetic checksums and measure elapsed time.
   Missing material or a failed comparison leaves the recovery gate open.
5. **Evidence:** Keep dated expected/observed outcomes, prerequisite failures and
   rollback results privately. Publish only sanitized aggregate evidence; never
   hostnames, addresses, tokens, sessions, private links or recovery material.

Record each check independently; no fleet-wide readiness, automatic failover or
high availability follows from one successful host or source-contract run.
