#!/bin/sh
# Resume one existing primary guest after login; never provision/reconfigure it.
set -eu
export LIMA_HOME="$HOME/.local/share/dots-primary-lima"
ROOT="$HOME/Library/Application Support/dots-primary-infrastructure"
LIMA="$ROOT/runtime/bin/limactl"
[ -x "$LIMA" ] && [ -f "$LIMA_HOME/primary/lima.yaml" ] || { echo 'Existing primary guest/runtime missing; refusing creation.' >&2; exit 1; }
# Preserve old boot locks; never remove uncertain same-boot execution locks.
BOOT_ID=$(sysctl -n kern.bootsessionuuid) || { echo 'Boot identity unavailable; refusing start.' >&2; exit 1; }
case "$BOOT_ID" in
  ????????-????-????-????-????????????) ;;
  *) echo 'Invalid boot identity; refusing start.' >&2; exit 1 ;;
esac
case "$BOOT_ID" in
  *[!a-fA-F0-9-]*) echo 'Invalid boot identity; refusing start.' >&2; exit 1 ;;
esac
COMPACT_BOOT_ID=$(printf '%s' "$BOOT_ID" | tr -d '-')
[ "${#COMPACT_BOOT_ID}" -eq 32 ] || { echo 'Invalid boot identity; refusing start.' >&2; exit 1; }
LOCK="$ROOT/startup/start.$BOOT_ID.lock"
mkdir "$LOCK" 2>/dev/null || { echo 'Startup lock present; refusing concurrent start.' >&2; exit 1; }
trap 'rmdir "$LOCK"' EXIT
trap 'exit 1' HUP INT TERM
status=$("$LIMA" list primary --format '{{.Status}}')
case "$status" in
  Running) echo 'Primary already running; no action.' ;;
  Stopped) "$LIMA" start --timeout=180s primary ;;
  *) echo 'Primary status is not Running or Stopped; inspection required.' >&2; exit 1 ;;
esac
