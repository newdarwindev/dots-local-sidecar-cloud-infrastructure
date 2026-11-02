# Public registry image lock evidence

**Observed 2026-11-02, read-only.** [`images.lock.json`](images.lock.json)
records the exact selected image tags, registry manifest-index SHA256, published
platform descriptors and source URL for each of the nine chart-selected images.
Every index advertises both `linux/amd64` and `linux/arm64`; `unknown/unknown`
descriptors are provenance/attestation entries, not runnable architectures.

## Method and scope

Fetched registry v2 manifest endpoints with OCI-index / Docker-manifest-list
Accept headers. Public registry bearer challenges were answered with anonymous
pull-scope tokens held only in process memory. No account login, credentials,
registry changes or new permission grants were used. SHA256 was computed over
response bytes and matched the registry's `Docker-Content-Digest` header where
present. The lock stores no bearer tokens or credential-bearing URLs.

The official Langfuse chart uses `docker.langfuse.com/langfuse/langfuse` and
`docker.langfuse.com/langfuse/langfuse-worker`. Docker Hub requests use
`registry-1.docker.io`; `library/postgres` is the expanded registry path for
`docker.io/postgres`. Homarr uses `ghcr.io/homarr-labs/homarr`.

Tag selection was read from checksum-pinned chart archives plus this bundle's
explicit values: Langfuse 4.70.1, Collector 0.163.2, PostgreSQL 18, Valkey 8.0,
SeaweedFS 4.23, ClickHouse server/Keeper 26.8.36.3, Homarr v2.10.1. Mutable major
or minor tags are retained as provenance only: a production renderer must use
the recorded digest, never resolve these tags again silently. All rendered
workloads, including init containers and hooks, must be checked against this
lock; unlisted images fail closed.

## Limits

This is **image-index identity and advertised architecture evidence**, not a
container pull, software-signature verification, vulnerability scan, runtime
compatibility test, target capacity assessment, or deployment approval. Child
manifest platforms are reported by the registry index; layers were not fetched
or executed. Exact-image Collector configuration and synthetic-canary tests
still belong in Docker CI. Do not equate an architecture entry with a healthy
application or a safe migration. Operator/cert-manager images and any future
Tokscale image remain outside this application image lock and need separate
reviewed pins before their stages can be enabled.

## Chart consumption review

The staged values now consume these locks:

- Collector has a supported `image.digest` field, which overrides the tag.
- Langfuse web/worker, Homarr, bundled PostgreSQL, Valkey and SeaweedFS chart
  templates concatenate repository and tag without a digest field. Their tag
  values therefore use the Kubernetes-supported `version@sha256:...` form,
  yielding `repository:version@sha256:...`. The digest determines image identity.
  Web and worker have independent overrides because their image digests differ.
- PostgreSQL's init and main container use the same image setting. SeaweedFS's
  all-in-one workload and bucket hook use the same `seaweedfs.master.image`
  helper, so the selected digest covers both. Disabled exporters, tests, volume
  resizing, standalone components and COSI are not activated by these edits.

**Structured ClickHouse/Keeper candidate pins:** both CR image objects now carry
explicit nonempty `version@sha256` tags, checked separately against their exact
component locks. The [candidate operator contract](clickhouse-operator-contract.md)
records checksum-pinned official operator v0.0.8 schema and source evidence for
this form, including why hash-only objects are unsafe under its defaulting.
This does **not** identify or approve the operator on the target. Both custom
resource kinds remain unsupported deployment blockers. New contract tests are
unrun because the owner disabled CI for budget and local Docker is unavailable.

No Helm rendering, schema validation or container execution was performed while
editing these values; the committed Docker workflow must verify final manifests.

Reference: [Kubernetes image names](https://kubernetes.io/docs/concepts/containers/images/#image-names)
explains combined tag/digest references; when both are present, pulling uses the
digest. This container-image syntax does not establish third-party CRD support.
