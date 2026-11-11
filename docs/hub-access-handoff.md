# Hub access and recovery handoff

**2026-11-11: source preparation; no deployment or peer acceptance.** Private
host state and selected names belong in the private formation handoff. The
owner deferred Mac qualification and requested repository handoffs. Do not
interpret these commits as enrollment or successful authenticated access.

## Selected direction

Reuse the existing applications behind one private gateway with distinct
application names. Qualify the dashboard first, then the tracing UI through the
same gateway. Keep machine ingestion, usage submission, databases and the
control plane separate. Retain existing forwarders until their replacements
pass acceptance; serial forwarding layers are not automatically duplicates.
Keep the legacy custom relay disabled; add no custom receiver or uploader.

Name resolution, certificate SAN coverage and client trust are separate gates.
A correct hostname does not grant trust, and a trusted issuer does not fix the
wrong SAN. Verify native application login, redirects, cookies, protected
resources and logout after TLS. Usage-hub OAuth callbacks and aggregate
submission require their own qualification. Never bypass TLS to finish tests.

## Reproducible queue qualification

The Docker runtime suite now includes
`test_durable_outage_crash_replay_exact_ids` in
[collector_runtime.py](../validation/collector_runtime.py). It uses three
invented trace/span pairs, a TLS destination returning 503, a byte-sized persistent
queue with fsync, and an abrupt test-process kill. Restart reuses that queue,
without resubmitting the source payload. Exact pair comparison detects missing
and unexpected IDs; counts and a three-second quiet window check duplicates.
Only loopback exists in this container. Certificates and queue files are ephemeral.
This qualifies process-crash replay in the test, not a live PVC, disk/power loss,
peer source buffering, indefinite no-loss delivery or independent recovery.

The committed Dockerfile retains its BuildKit read-only lock mount because the
installer uses that mount as a Docker-build guard when `.dockerenv` is absent.
Do not remove it simply to work around missing Buildx. The earlier dirty-checkout
validation result is separate from this clean-source handoff. Run
`sh validation/run.sh` with an already available compatible builder; no host
validator fallback, daemon startup or CI activation is authorized by this file.

## Handoff validation

The added persistent replay test passed in a Docker build snapshot using the
legacy-compatible build recipe evaluated during this handoff. That snapshot
completed the full runner: 316 tests and 184 schema-valid resources, with no
invalid resources, schema errors or skips. The temporary Dockerfile change was
withdrawn after reviewing the BuildKit-specific installer guard; it is not part
of this commit. The final committed `sh validation/run.sh lint` attempt stopped
at the existing `RUN --mount` because BuildKit/Buildx is unavailable. Therefore
final-revision validation is **blocked**, not passed. Preserve the guard and use
an already authorized compatible builder for the next exact-source run.

## Resume checklist

1. Refresh installed/source revisions, pod/PVC readiness, backing storage,
   reservations, forwarders and enabled units; preserve existing dirty work.
2. Inspect exact Pod admission as well as the Deployment. Namespace quota can
   accept a controller yet reject its Pods. Budget rollout overlap explicitly.
3. Recollect guarded object identities and resourceVersions. Never reuse a
   stale generated packet or replace an unknown check with a passing assertion.
4. Verify approved client ownership/source, private discovery, serving SANs,
   trust custody and backend isolation before declaring the gateway usable.
5. Correlate normal, rejection, outage buffering, restart replay, duplicate and
   loss cases separately. Receiver ACK is not persistence; use the installed
   backend's actual storage/API model, including v4 rather than legacy tables.
6. On failure restore only owned changes with fresh guards. Preserve queues,
   histories, certificates and volumes. Keep encrypted independent restore
   qualification separate from queue replay and Retain PVC observations.

See [operator setup](../application-infrastructure/README.md),
[native integration contract](codex-native-monitoring.md),
[validation](../validation/README.md) and
[operating entry points](operating-entrypoints.md).
