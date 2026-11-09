#!/bin/sh
# Explicit owner-authorized synthetic setup. No data imports, credentials or deletion.
set -eu
[ "$#" -eq 2 ] || { echo 'Usage: sh foundation.sh CONTEXT KUBE_SYSTEM_UID' >&2; exit 2; }
LAB_CONTEXT=$1
LAB_CLUSTER_UID=$2
LAB_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
check_cluster() {
  [ "$(kubectl --context "$LAB_CONTEXT" get namespace kube-system -o jsonpath='{.metadata.uid}')" = "$LAB_CLUSTER_UID" ] || {
    echo 'Cluster identity differs; stopped.' >&2; exit 2;
  }
}
check_cluster
for LAB_RESOURCE in namespace/dots-synthetic-lab storageclass/dots-lab-retain; do
  LAB_OWNER=$(kubectl --context "$LAB_CONTEXT" get "$LAB_RESOURCE" --ignore-not-found -o jsonpath='{.metadata.labels.dots\.example/purpose}')
  if kubectl --context "$LAB_CONTEXT" get "$LAB_RESOURCE" --ignore-not-found -o name | grep -q .; then
    [ "$LAB_OWNER" = synthetic-lab ] || { echo 'Existing resource is outside this lab.' >&2; exit 2; }
  fi
done
kubectl --context "$LAB_CONTEXT" apply --server-side --dry-run=server -f "$LAB_ROOT/namespace.yaml"
check_cluster
kubectl --context "$LAB_CONTEXT" apply --server-side -f "$LAB_ROOT/namespace.yaml"
kubectl --context "$LAB_CONTEXT" apply --server-side --dry-run=server -f "$LAB_ROOT/foundation.yaml"
check_cluster
kubectl --context "$LAB_CONTEXT" apply --server-side -f "$LAB_ROOT/foundation.yaml"
