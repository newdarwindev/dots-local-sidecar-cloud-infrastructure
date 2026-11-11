# Lint and validation

From the repository root, using **already available** authorized Docker:

```sh
sh validation/run.sh              # Lint + both bundles' tests, Helm and schemas
sh validation/run.sh lint         # Offline lint + validator regression tests only
sh validation/run.sh primary      # Lint + primary bundle tests/Helm/schemas
sh validation/run.sh application  # Lint + application tests/Helm/Tokscale schemas
```

**Current status:** the full Docker runner passed locally on 2026-11-07: lint
(91 validator tests), 8 isolated Collector runtime tests, 7 primary tests, 115
application tests, 16 Tokscale tests, exact Collector configuration validation,
Helm rendering and strict schema checks. Live cluster acceptance remains separate
and is recorded in private local receipts. Both GitHub workflows remain
owner-paused. Missing tools or schemas fail; they are never skipped.

## Execution boundary

The runner builds a Linux amd64 tool image with checksum-pinned public downloads.
Lint runs offline, non-root, read-only, capability-free and resource-bounded; only
container `/tmp` is writable. Parsed Python/TS/shell/config inputs are not executed
by linters. Synthetic validator tests separately import trusted helpers/renderers.
The contracts stage permits public downloads and uses an ephemeral source copy.
No host mounts, daemon socket, credentials, kubeconfig, live preflight, install,
deployment or live service startup. Commands fail fast; use `lint` independently of
networked schema checks. ARM hosts need an already configured amd64 builder.

## Offline setup review

After execution is authorized and Docker is already available:

```sh
sh validation/run.sh setup cluster-assess /private/future-cluster.json
sh validation/run.sh setup cluster-packet /private/future-cluster.json
sh validation/run.sh setup plugin-render /private/plugin-render.json
sh validation/run.sh setup plugin-check /private/plugin-check.json
```

These are the **only** setup actions. Prepare an owner-reviewed nonsecret JSON
file using [cluster](../application-infrastructure/README.md#2-configure-privately)
or [plugin](../application-infrastructure/runbooks/telemetry.md#plugin-configuration-before-any-later-enrollment)
instructions: absolute path, outside this checkout, regular/non-symlink, 1–65536
bytes, preferably mode 0600. Known auth/history directories are rejected, but this
is **not a secret detector**: never supply credentials, account config or histories.
Use a caller-controlled file in a private caller-controlled directory; do not
modify it until snapshotting finishes. Hostile concurrent filesystem changes are
outside this route's guarantee. The host shell checks path/type/size, pins a read-only file
descriptor and snapshots at most 65537 bytes (rejecting anything over 64 KiB)
before building; no host Python runs.

The runner permits only a selected local Unix Docker endpoint, uses an empty
transient CLI config (no proxy/env/credential inheritance), builds before input
delivery, and pins the returned image ID. Runtime has no network, capabilities,
host mounts, socket or daemon logging; it is non-root, read-only and resource
bounded with ephemeral `/tmp`. This is not a claim of a rootless Docker daemon.
The input reaches Docker before schema checks; prepare and protect it accordingly.
Only the review runtime is offline; image building may download public dependencies.

Stdout is one **private review JSON** document; fixed stage errors go to stderr.
Only a mode-0600 input snapshot in a mode-0700 temporary directory is written on
the host and removed on normal exit; no durable output is created. Any separately chosen
capture must stay private and out of Git/CI uploads. `cluster-packet` returns named
`documents`, not a directory; each
receipt digest covers the document serialized with JSON indent 2 plus a newline
(in returned key order). Plugin output remains disabled. No arbitrary command,
chart fetch/render, preflight, deployment, config installation or source enrollment
is exposed. Setup's synthetic regression tests passed in the full local run;
a private target packet has not been assessed through this route.

## Coverage

| Files | Checks |
| --- | --- |
| All Dockerfiles | Hadolint warning threshold, inline shell; digest-pinned bases and Collector source consistency |
| Shell; workflow `run` blocks | ShellCheck; actionlint on both workflows and disabled deployment design; full-SHA action pins |
| Python, including helpers/tests | Ruff `E9`, `F`, `PLE` correctness/syntax; no whole-repo formatting |
| YAML, including `.yml.disabled` | Duplicate keys, whitespace, booleans, finite floats and strict mappings |
| JSON, including synthetic fixtures/locks/schemas | Duplicate keys, nonfinite/overflow numbers; artifact/source/image/tool pin policy |
| TypeScript | Biome syntax/correctness, not typechecking or runtime tests |
| HCL; systemd; TOML | HCL parser; strict declared unit structure; TOML parser—not runtime/authorization acceptance |
| Markdown | Parsed local links/images and heading anchors, not remote URL reachability |
| Public TLS fixtures | Exact filenames, checksums and separately pinned provenance; no directory-wide exception |

New unknown file types fail and need intentional coverage. Generated/cache trees,
Git metadata and common credential paths are excluded by `.dockerignore`; never
put private records in this public repo/build context. Ignore/license text is
classified, not semantically validated. This is not a comprehensive secret scan,
vulnerability scan, SBOM, or JSON Schema metaschema validator.

## Helm and Kubernetes

Full validation retains the existing safety regression suites and exact Collector
configuration check, then lints/renders all four primary and three application
charts. Strict kubeconform checks static and rendered manifests, plus Tokscale's
separate **synthetic zero-replica** output. Argo/ESO CRD schemas come from locked
charts; ClickHouse schemas come from its checksum-locked operator source. Missing
schemas, unknown kinds, conflicting CRDs and empty scopes fail—no skip/fallback.

The immutable schema snapshot in [tools.lock.json](tools.lock.json) must support
the exact render input: primary/Tokscale **1.37.1**, existing synthetic application
fixture **1.32.0**. These are assumptions, not observed cluster versions. Schemas
do not exercise CEL, admission, defaulting or controllers. Live acceptance remains
separate. The local runner does not build/run Tokscale's app or TLS socket tests;
those remain in its existing disabled CI recipe.

**Narrow exception:** Helm lint cannot supply discovery APIs, so only Langfuse's
lint command gets upstream-supported `clickhouse.crdCheck=false`. Normal rendering
retains the guard, supplies both APIs and checks their locked CRD schemas. No
source values or live guard are changed. Bun's existing variable `FROM` is the
only base-pin exception; its build CLI requires the exact reviewed digest.

## Maintenance

Executable binaries and all mandatory Python wheels/transitives are exact-version
and SHA256 locked in [tools.lock.json](tools.lock.json) and
[requirements.txt](requirements.txt). Legacy bundle images share the pinned
[runtime PyYAML wheel](runtime-requirements.txt). Official artifact bytes/base-image
manifest hashes were verified; this does not establish a successful build/test.

To update: review official releases, verify bytes, update matching locks/references,
then run the full Docker suite. Fix findings rather than add blanket disables.
Any necessary exception must name the exact file/rule/resource, reason, upstream
evidence and removal condition, with a narrow regression test. Never ignore
missing schemas, skip missing tools or exempt whole fixture directories.

Tool references: [Hadolint](https://github.com/hadolint/hadolint),
[ShellCheck](https://github.com/koalaman/shellcheck),
[Ruff](https://docs.astral.sh/ruff/configuration/),
[yamllint](https://yamllint.readthedocs.io/en/stable/rules.html),
[actionlint](https://github.com/rhysd/actionlint/blob/main/docs/usage.md),
[Biome](https://biomejs.dev/reference/cli/),
[kubeconform](https://github.com/yannh/kubeconform),
[Helm lint](https://helm.sh/docs/helm/helm_lint/).

## Isolated Collector runtime canaries

The `all` and `application` scopes also run `collector_runtime.py` in a separate
**network-none**, non-root, read-only container. Only loopback listeners exist;
there are no host ports, mounts, live services, account credentials or installed
trust changes. OpenSSL already in the pinned image creates one-day synthetic
self-signed SAN certificates solely in ephemeral container tmpfs. These test
keys never leave the container or enter a deployment. Collector process logs
are emitted into the caller's validation log before ephemeral files disappear.

Eight tests exercise the exact pinned Collector 0.163.2 with the unchanged privacy
processors and strict receiver/exporter TLS. Test-only substitutions are local
endpoints, ephemeral certificate paths, obvious synthetic authorization, JSON
export encoding and shorter batch/retry time bounds. Positive export verifies
the authorization and ingestion headers; missing/untrusted client certificates,
TLS 1.2, wrong exporter CA and wrong exporter hostname must fail. These are
bounded synthetic controls, not delivery durability, load, or live acceptance.

The native rollout tests additionally load `native-monitoring/collector.yaml`.
They verify empty OTLP at exactly 65,536 bytes, rejection at 65,537 bytes,
malformed JSON rejection, destination outage/reconnection, queue overflow,
retry exhaustion and bounded shutdown. Failure tests retain the 256-request
volatile queue and 60-second retry window; test-only one-span batches and a
one-second HTTP timeout fill the queue without large receiver requests.
Shutdown can drop queued spans, so successful receiver acknowledgement does
not establish durable delivery.

**Confirmed limitation:** direct Collector input retains resource and scope
schema URLs. That test intentionally verifies the limitation rather than
weakening it or claiming privacy readiness. Arbitrary attribute/name/status/
trace-state canaries are stripped and spans with events or links are dropped.
A separate test passes the synthetic request through `native_otlp.py` first and
checks the entire exported JSON for canary/schema-URL absence. This qualifies
only that offline synthetic reconstruction path, not connected source
activation, arbitrary real-content classification, or every possible covert
channel in identifiers/numeric fields. Real-source consent and recovery gates
remain unchanged.

## Explicit local Tokscale database qualification

```sh
sh validation/run.sh tokscale-db --local
```

This separate, opt-in local scope requires the already built
`infrastructure-validation:local` and `tokscale-ci:review` images plus the locked
PostgreSQL image already available to Docker. It does not run as part of `all`,
`application`, or CI, and it does not enable CI. No daemon is started or image
pulled by this route. The harness rejects a missing or additional local flag.

It uses a disposable PostgreSQL server and synthetic client sharing an isolated
network-none namespace, with no published host ports. Only public compromised-
by-design TLS fixtures and the authored test script are mounted read-only;
no real credentials, databases or source histories are mounted. Runtime state
lives in container tmpfs. Receipts and logs are retained under the ignored
`application-infrastructure/.runtime/` directory; containers are stopped and
retained, not pruned. Database migration, workload and restart tests do not
establish encrypted backup/recovery or production readiness.
