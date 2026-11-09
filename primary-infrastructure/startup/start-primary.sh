#!/bin/sh
# Resume one existing primary guest after login; never provision/reconfigure it.
set -eu
export LIMA_HOME="$HOME/.local/share/dots-primary-lima"
ROOT="$HOME/Library/Application Support/dots-primary-infrastructure"
LIMA="$ROOT/runtime/bin/limactl"
[ -x "$LIMA" ] && [ -f "$LIMA_HOME/primary/lima.yaml" ] || { echo 'Existing primary guest/runtime missing; refusing creation.' >&2; exit 1; }
# Never remove a pre-existing lock: uncertain/concurrent execution needs review.
LOCK="$ROOT/startup/start.lock"
mkdir "$LOCK" 2>/dev/null || { echo 'Startup lock present; refusing concurrent start.' >&2; exit 1; }
trap 'rmdir "$LOCK"' EXIT
trap 'exit 1' HUP INT TERM
status=$("$LIMA" list primary --format '{{.Status}}')
case "$status" in
  Running) echo 'Primary already running; no action.' ;;
  Stopped) "$LIMA" start primary ;;
  *) echo 'Primary status is not Running or Stopped; inspection required.' >&2; exit 1 ;;
esac
