#!/bin/sh
# Synthetic CNI and retained-volume acceptance, without application credentials.
set -eu
[ "$#" -eq 2 ] || { echo 'Usage: sh check.sh CONTEXT KUBE_SYSTEM_UID' >&2; exit 2; }
LAB_CONTEXT=$1
LAB_UID=$2
LAB_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
[ "$(kubectl --context "$LAB_CONTEXT" get ns kube-system -o jsonpath='{.metadata.uid}')" = "$LAB_UID" ] || exit 2
[ "$(kubectl --context "$LAB_CONTEXT" get ns dots-synthetic-lab -o jsonpath='{.metadata.labels.dots\.example/purpose}')" = synthetic-lab ] || exit 2
for LAB_PAIR in dots-synthetic-lab:dots-lab-server-probe dots-synthetic-lab:dots-lab-client-probe default:dots-lab-outside-probe; do
  [ -z "$(kubectl --context "$LAB_CONTEXT" -n "${LAB_PAIR%:*}" get pod "${LAB_PAIR#*:}" --ignore-not-found -o name)" ] || {
    echo 'A probe pod already exists; reconcile it before retrying.' >&2; exit 2;
  }
done
LAB_OWNER=$(kubectl --context "$LAB_CONTEXT" -n dots-synthetic-lab get pvc dots-lab-storage-probe --ignore-not-found -o jsonpath='{.metadata.labels.dots\.example/purpose}')
if kubectl --context "$LAB_CONTEXT" -n dots-synthetic-lab get pvc dots-lab-storage-probe --ignore-not-found -o name | grep -q .; then
  [ "$LAB_OWNER" = synthetic-lab-probe ] || exit 2
fi
kubectl --context "$LAB_CONTEXT" apply --server-side --dry-run=server -f "$LAB_ROOT/probes.yaml"
cleanup() {
  kubectl --context "$LAB_CONTEXT" -n dots-synthetic-lab delete pod dots-lab-server-probe dots-lab-client-probe --ignore-not-found --wait=false
  kubectl --context "$LAB_CONTEXT" -n default delete pod dots-lab-outside-probe --ignore-not-found --wait=false
}
trap cleanup EXIT HUP INT TERM
kubectl --context "$LAB_CONTEXT" apply --server-side -f "$LAB_ROOT/probes.yaml"
kubectl --context "$LAB_CONTEXT" -n dots-synthetic-lab wait --for=condition=Ready pod/dots-lab-server-probe pod/dots-lab-client-probe --timeout=180s
kubectl --context "$LAB_CONTEXT" -n default wait --for=condition=Ready pod/dots-lab-outside-probe --timeout=180s
LAB_INSIDE=$(kubectl --context "$LAB_CONTEXT" -n dots-synthetic-lab get pod dots-lab-server-probe -o jsonpath='{.status.podIP}')
LAB_OUTSIDE=$(kubectl --context "$LAB_CONTEXT" -n default get pod dots-lab-outside-probe -o jsonpath='{.status.podIP}')
connect() {
  kubectl --context "$LAB_CONTEXT" -n "$1" exec -i "$2" -- python - "$3" "$4" <<'PY'
import socket, sys
try:
    with socket.create_connection((sys.argv[1], 8000), timeout=3):
        connected = True
except OSError:
    connected = False
assert connected == (sys.argv[2] == 'allow'), 'CNI boundary differs from expected'
print('CNI probe:', sys.argv[2], 'verified')
PY
}
connect dots-synthetic-lab dots-lab-client-probe "$LAB_INSIDE" allow
connect dots-synthetic-lab dots-lab-client-probe "$LAB_OUTSIDE" deny
connect default dots-lab-outside-probe "$LAB_INSIDE" deny
kubectl --context "$LAB_CONTEXT" -n dots-synthetic-lab exec -i dots-lab-client-probe -- python - <<'PY'
from pathlib import Path
p = Path('/probe/synthetic-marker.txt')
if not p.exists():
    p.write_text('invented lab storage marker\n')
assert p.read_text() == 'invented lab storage marker\n'
print('Synthetic volume write/read verified; marker and PVC retained.')
PY
LAB_PV=$(kubectl --context "$LAB_CONTEXT" -n dots-synthetic-lab get pvc dots-lab-storage-probe -o jsonpath='{.spec.volumeName}')
[ "$(kubectl --context "$LAB_CONTEXT" get pv "$LAB_PV" -o jsonpath='{.spec.persistentVolumeReclaimPolicy}')" = Retain ] || exit 2
echo 'PASS: CNI ingress/egress boundaries and retained local-path storage.'
