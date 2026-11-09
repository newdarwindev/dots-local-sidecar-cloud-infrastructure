#!/bin/sh
# Bounded local Docker validation only. Does not start Docker or enable GitHub CI.
set -eu
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
if [ "${1:-}" = tokscale-db ]; then
  shift
  export VALIDATION_IMAGE=infrastructure-validation:local
  exec sh "$ROOT/application-infrastructure/tokscale/db-integration.sh" "$@"
fi
if [ "${1:-}" = setup ]; then
  shift
  exec sh "$ROOT/validation/setup.sh" "$@"
fi
case "${1:-all}" in
  all|primary|application|lint) BUNDLE=${1:-all} ;;
  *) echo 'Usage: sh validation/run.sh [all|primary|application|lint] or setup ACTION /absolute/input.json or tokscale-db --local' >&2; exit 2 ;;
esac
[ "$#" -le 1 ] || { echo 'Only one scope argument is allowed.' >&2; exit 2; }
cd "$ROOT"
command -v docker >/dev/null 2>&1 || {
  echo 'BLOCKED: Docker CLI unavailable. No host fallback; do not start a daemon.' >&2
  exit 2
}
docker info >/dev/null 2>&1 || {
  echo 'BLOCKED: Docker daemon unavailable. Do not start it merely for validation.' >&2
  exit 2
}
# Existing dormant application workflow reuses this image for its build recipe.
IMAGE=infrastructure-validation:local
docker build --platform linux/amd64 -f validation/Dockerfile -t "$IMAGE" .
run_stage() {
  docker run --rm --read-only --user 65532:65532 \
    --cpus=2 --memory=2g --pids-limit=256 --cap-drop=ALL \
    --security-opt=no-new-privileges "$@"
}
# Runner regressions execute their authored mock Docker CLI from a dedicated
# tmpfs. Keep general /tmp noexec; setup inputs retain their own noexec tmpfs.
run_stage --network=none \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=512m \
  --tmpfs /runner-exec:rw,nosuid,nodev,exec,size=64m \
  -e VALIDATION_EXEC_TMPDIR=/runner-exec \
  "$IMAGE" lint
if [ "$BUNDLE" = all ] || [ "$BUNDLE" = application ]; then
  run_stage --network=none --tmpfs /tmp:rw,nosuid,nodev,noexec,size=128m \
    "$IMAGE" collector-runtime
fi
if [ "$BUNDLE" != lint ]; then
  # Only public pinned artifacts/schema downloads. No kubeconfig, host mounts,
  # daemon socket, private account environment or cluster endpoint is passed in.
  run_stage --tmpfs /tmp:rw,nosuid,nodev,size=1g \
    "$IMAGE" contracts --bundle "$BUNDLE"
fi
