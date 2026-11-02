#!/bin/sh
# Called only by committed Docker CI. No credentials, database, push or deploy.
set -eu
: "${VALIDATION_IMAGE:?Supply the already-built application validation container image}"
# The caller must be the repository root and this script runs only on a hosted CI runner.
[ "${CI:-}" = "true" ] || { echo 'Blocked: this build recipe is restricted to CI.' >&2; exit 2; }
BASE="$PWD/application-infrastructure/tokscale"
mkdir -p "$PWD/application-infrastructure/.runtime"
WORK=$(mktemp -d "$PWD/application-infrastructure/.runtime/tokscale-build.XXXXXX")
# Source preparation and all Python validation execute inside Docker, never on host.
docker run --rm --user "$(id -u):$(id -g)" --cap-drop=ALL --security-opt=no-new-privileges \
  -v "$PWD:/work" -w /work --entrypoint python "$VALIDATION_IMAGE" \
  application-infrastructure/tokscale/prepare_source.py \
  --output "/work/${WORK#"$PWD/"}/source"
BUN_IMAGE=$(docker run --rm --network=none --user "$(id -u):$(id -g)" --cap-drop=ALL --security-opt=no-new-privileges \
  -v "$PWD:/work:ro" -w /work --entrypoint python "$VALIDATION_IMAGE" -c \
  'import json; x=json.load(open("application-infrastructure/tokscale/images.lock.json"))["images"]["bun"]; print("oven/bun@"+x["digest"])')
docker run --rm --network=none --user "$(id -u):$(id -g)" --cap-drop=ALL --security-opt=no-new-privileges \
  -v "$PWD:/work:ro" -w /work --entrypoint python "$VALIDATION_IMAGE" \
  application-infrastructure/tokscale/build_plan.py --bun-image "$BUN_IMAGE" \
  --source "/work/${WORK#"$PWD/"}/source" --platform linux/amd64
# Network is needed for public package downloads and next/font's Google fonts.
# No secret mounts/build args, private registry credentials, DB URL or OAuth keys.
docker build --platform linux/amd64 --build-arg "BUN_IMAGE=$BUN_IMAGE" \
  -f "$BASE/Dockerfile" -t tokscale-ci:review "$WORK/source"
# Image-only smoke check: do not run the migration entrypoint or start a server.
docker run --rm --network=none --cap-drop=ALL --security-opt=no-new-privileges \
  --entrypoint /bin/sh tokscale-ci:review -c \
  'set -eu; test "$(id -u)" = 10001; test -f /app/packages/frontend/server.js; test -x /usr/local/bin/docker-entrypoint.sh; bun --version; node --version'
docker image inspect tokscale-ci:review --format '{{.Id}}' > "$WORK/built-image-id.txt"
printf 'Image build and isolated image smoke check succeeded; no DB/runtime/deployment acceptance.\n'
