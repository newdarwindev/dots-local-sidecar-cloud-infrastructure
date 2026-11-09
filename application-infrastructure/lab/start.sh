#!/bin/sh
# Apply one reviewed lab render, bound to cluster/namespace identity and file digest.
set -eu
[ "$#" -eq 5 ] || { echo 'Usage: sh start.sh CONTEXT CLUSTER_UID NAMESPACE_UID MANIFEST SHA256' >&2; exit 2; }
LAB_CONTEXT=$1
LAB_CLUSTER_UID=$2
LAB_NAMESPACE_UID=$3
LAB_MANIFEST=$4
LAB_DIGEST=$5
check_identity() {
  [ "$(kubectl --context "$LAB_CONTEXT" get ns kube-system -o jsonpath='{.metadata.uid}')" = "$LAB_CLUSTER_UID" ] || exit 2
  [ "$(kubectl --context "$LAB_CONTEXT" get ns dots-synthetic-lab -o jsonpath='{.metadata.uid}')" = "$LAB_NAMESPACE_UID" ] || exit 2
  [ "$(sha256sum "$LAB_MANIFEST" | cut -d ' ' -f 1)" = "$LAB_DIGEST" ] || exit 2
}
check_identity
kubectl --context "$LAB_CONTEXT" -n dots-synthetic-lab apply --server-side --dry-run=server -f "$LAB_MANIFEST"
check_identity
kubectl --context "$LAB_CONTEXT" -n dots-synthetic-lab apply --server-side -f "$LAB_MANIFEST"
echo 'Synthetic lab applied. Verify health and capacity before any access; sources remain disabled.'
