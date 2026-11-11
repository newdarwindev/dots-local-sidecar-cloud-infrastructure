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

## Validation through an isolated Docker CLI

The committed Dockerfile retains its BuildKit read-only lock mount because the
installer uses that mount as a Docker-build guard when `.dockerenv` is absent.
The host's missing Buildx was resolved for validation by using the official Docker
CLI image, pinned below, against the already running local daemon. No host plugin
installation, daemon start, credential mount or CI enablement is needed.

From this repository root, with existing permission to the local Docker socket:

```sh
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" \
  --group-add "$(stat -c %g /var/run/docker.sock)" \
  --cpus 2 --memory 768m --pids-limit 256 \
  --tmpfs /tmp:rw,nosuid,nodev,size=256m \
  -e DOCKER_CONFIG=/tmp/docker -e DOCKER_BUILDKIT=1 \
  -e BUILDKIT_PROGRESS=plain \
  --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock \
  --mount "type=bind,source=$PWD,target=/workspace,readonly" \
  -w /workspace --entrypoint sh \
  docker:29.9.3-cli@sha256:2357639ad1ea7d0194134bf3292622fd4e562483966ed674e5d7c945b5f3b28d \
  validation/run.sh
```

The outer container is trusted orchestration with Docker-socket authority, not
an untrusted test sandbox. It runs the unchanged committed entrypoint. The inner
validation containers retain its original non-root, resource, capability and
network boundaries, and receive no daemon socket or host credentials. The daemon
performs authorized public image/build downloads; `--network none` on the outer
CLI does not make the build or networked contract stages offline. Use `lint`
after `validation/run.sh` for the documented lint-only scope.

## Handoff validation

At the original handoff, a temporary legacy-build snapshot passed 316 tests and
184 schema-valid resources; that temporary Dockerfile change was withdrawn to
preserve the installer guard. The later exact-source BuildKit run and final
documentation checks are distinct from that snapshot. The unmodified committed
entrypoint with BuildKit passed **316 tests and 184 strict-schema resources** on
November 11, 2026, with zero invalid resources, errors or skips. This covers the
executable source at `8e6c08d`; the subsequent changes document the validated CLI
route only. Final documentation is checked with the same entrypoint's `lint`
scope before publication. No live cluster or peer acceptance follows.

## Resume checklist

The November 11 hub-only continuation reran the same Docker CLI/BuildKit route:
**316 tests and 184 strict-schema resources passed**, with zero invalid resources,
errors or skips. These remain isolated source/runtime-contract checks; no peer
delivery, live outage or independent restore acceptance follows.

Hub-only preparation can continue while a selected peer is deferred: refresh
capacity and object identities, review a memory-only quota adjustment with
UID/resourceVersion/spec/status guards, and submit the exact Pod template for
server-side dry-run. Share that template with the activation renderer so the
admission probe cannot silently diverge. Leave unknown source checks false; do
not emit a full activation packet or substitute another client. A quota patch
dry-run does not alter the quota used by a later Pod dry-run. Generate rollback
only after an actual change, from a fresh post-change version and confirmed unused
allowance; never invent a future resourceVersion.

An explicitly authorized closed startup is a separate stage: one normal gateway
Pod, no Service or published application routes, and deny-all ingress/egress
without additive namespace-policy grants. It must not invent a verified peer
source. Inspect provider startup and strict TLS as well as TCP readiness; an
empty dynamic middleware map can fail provider loading while the listener is
Ready. Opening later requires guarded updates of the same owned objects. Keep
initial-create collision checks intact and preserve the existing app origin and
forwarders until the appropriate acceptance gates pass. Private deployment
observations and renderer inputs remain outside this public repository.

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
