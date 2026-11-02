# ClickHouse/Keeper image contract — offline candidate, not target approval

The official operator release **v0.0.8** resolves to commit
[`ebcb5b6c7b2031e88671b4281f2b8ae60f6f71fd`](https://github.com/ClickHouse/clickhouse-operator/tree/ebcb5b6c7b2031e88671b4281f2b8ae60f6f71fd).
`clickhouse-operator.lock.json` SHA256-pins the inspected source and both CRD
schemas. This is a **candidate source contract**, not selection/installation of
an operator and not evidence of the operator present on the offline target.

## Findings

- The locked Langfuse 2.2.1 chart templates emit
  `spec.containerTemplate.image.repository` and `.tag` for both
  `clickhouse.com/v1alpha1` resource kinds. Chart archive SHA256 was verified
  during source inspection; no Helm was run for this change.
- Candidate operator `api/v1alpha1/common.go:ContainerImage.String` concatenates
  nonempty repository/tag with `:` unchanged. Both candidate CRD schemas define
  `tag` as a string without a tag-specific regex/enum. Thus the reviewed candidate
  source preserves `repository:version@sha256:...`, the Kubernetes digest-pinned
  image syntax. This is source reasoning, **not an executed admission test**.
- Do **not** substitute a hash-only object merely because the schema exposes
  `hash`. Candidate `ClickHouseClusterSpec.WithDefaults` and
  `KeeperClusterSpec.WithDefaults` provide `Tag: latest`; generic
  `controllerutil.ApplyDefault` recursively fills empty fields, and `String`
  prefers Tag over Hash. Static analysis therefore indicates a hash-only pin can
  be shadowed by the default tag. The staged contract rejects hash-only objects.
- Staged values now provide explicit nonempty `version@sha256` tags for both
  components. `image_policy.py` checks each structured object against its exact
  component repository/digest lock, rejecting unpinned tags, mixed/unknown image
  fields, mismatched component images and different API versions. Ordinary pod
  container images, including nested init/ephemeral containers, remain checked.

## Verification and remaining gates

`operator_contract.py` is a read-only, checksum-bound source/schema inspector for
future **authorized Docker validation**; it never compiles or executes operator
code. `test_clickhouse_images.py` adds synthetic positive/negative contracts.
**These new checks have not run:** the owner disabled CI for budget and local
Docker is unavailable. Do not describe this revision as validated or green.

Even a future passing source/schema check cannot establish webhook defaulting,
controller-generated workloads/probes, RBAC, certificate-manager prerequisites,
operator image identity, supported Kubernetes version, resource fit, PVC behavior
or actual target compatibility. The generic renderer still reports both custom
resource kinds as unsupported, so pinning these candidate image fields does not
remove the deployment gate. Before activation, identify the actual target
operator/CRD revision, compare its schema and defaulting/string behavior with this
candidate, then perform explicitly approved isolated admission/runtime tests.
No cluster, operator, CRD or service was created or changed.
