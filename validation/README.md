# Lint and validation

From the repository root, using **already available** authorized Docker:

```sh
sh validation/run.sh              # Lint + both bundles' tests, Helm and schemas
sh validation/run.sh lint         # Offline lint + validator regression tests only
sh validation/run.sh primary      # Lint + primary bundle tests/Helm/schemas
sh validation/run.sh application  # Lint + application tests/Helm/Tokscale schemas
```

**Current status:** Docker CLI unavailable; the runner exits 2 before building or
checking anything. Lint/tests/rendering remain **unrun**. Both GitHub workflows
remain disabled for budget. Do not start a daemon, install host tools, or enable
CI to bypass this block. Missing tools or schemas fail; they are never skipped.

## Execution boundary

The runner builds a Linux amd64 tool image with checksum-pinned public downloads.
Lint runs offline, non-root, read-only, capability-free and resource-bounded; only
container `/tmp` is writable. Parsed Python/TS/shell/config inputs are not executed
by linters. Synthetic validator tests separately import trusted helpers/renderers.
The contracts stage permits public downloads and uses an ephemeral source copy.
No host mounts, daemon socket, credentials, kubeconfig, live preflight, install,
deployment or service startup. Commands fail fast; use `lint` independently of
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
is exposed. Setup and its synthetic regression tests remain **UNRUN** here.

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
