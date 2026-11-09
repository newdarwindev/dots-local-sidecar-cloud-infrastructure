#!/bin/sh
# Recover only the three existing guest-loopback UI routes; never start a guest.
set -eu
export LIMA_HOME="$HOME/.local/share/dots-primary-lima"
LIMA="$HOME/Library/Application Support/dots-primary-infrastructure/runtime/bin/limactl"
[ "$#" -eq 1 ] || { echo 'Exactly one approved UI route is required.' >&2; exit 1; }
case "$1" in
  homarr) namespace=homarr; target=svc/homarr; ports=17575:7575 ;;
  argocd) namespace=argocd; target=svc/argocd-server; ports=18443:443 ;;
  openbao) namespace=openbao; target=svc/openbao; ports=18200:8200 ;;
  *) echo 'Unknown UI route; refusing forward.' >&2; exit 1 ;;
esac
[ -x "$LIMA" ] && [ -f "$LIMA_HOME/primary/lima.yaml" ] || { echo 'Existing primary guest/runtime missing; refusing forward.' >&2; exit 1; }
[ "$("$LIMA" list primary --format '{{.Status}}')" = Running ] || { echo 'Primary is not running; refusing forward.' >&2; exit 1; }
exec "$LIMA" shell primary -- sudo k3s kubectl -n "$namespace" port-forward "$target" "$ports" --address=127.0.0.1
