#!/bin/sh
# Credential-free reviewed build. No database, push or deploy.
set -eu
: "${VALIDATION_IMAGE:?Supply the already-built application validation container image}"
# Local execution is explicit; never impersonate CI by setting CI=true.
case "${1:-}" in
  --local) [ "$#" -eq 1 ] || exit 2 ;;
  '') [ "$#" -eq 0 ] && [ "${CI:-}" = true ] || {
    echo 'Supply --local for an authorized local build, or run in CI.' >&2; exit 2;
  } ;;
  *) echo 'Usage: sh application-infrastructure/tokscale/ci-build.sh [--local]' >&2; exit 2 ;;
esac
# Pin the already-built validation image once for this invocation.
VALIDATION_IMAGE=$(docker image inspect "$VALIDATION_IMAGE" --format '{{.Id}}')
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
docker build --platform linux/amd64 --memory=5g --cpu-period=100000 --cpu-quota=200000 \
  --build-arg "BUN_IMAGE=$BUN_IMAGE" \
  -f "$BASE/Dockerfile" -t tokscale-ci:review "$WORK/source"
# Image-only smoke check: do not run the migration entrypoint or start a server.
docker run --rm --network=none --cap-drop=ALL --security-opt=no-new-privileges \
  --entrypoint /bin/sh tokscale-ci:review -c \
  'set -eu; test "$(id -u)" = 10001; test -f /app/packages/frontend/server.js; test -x /usr/local/bin/docker-entrypoint.sh; bun --version; printf "%s\n" "console.log(process.version)" > /tmp/runtime-smoke.cjs; node /tmp/runtime-smoke.cjs'
docker image inspect tokscale-ci:review --format '{{.Id}}' > "$WORK/built-image-id.txt"
printf 'Image build and isolated image smoke check succeeded; no DB/runtime/deployment acceptance.\n'
# Future explicitly reauthorized CI only: shared TLS contract, public fixtures.
# Loopback-only PostgreSQL startup mock; no database/migration/server activation.
TLS_CLIENT=$(docker run -d --network=none --cap-drop=ALL --security-opt=no-new-privileges \
  --add-host agent1:127.0.0.1 --add-host wrongname:127.0.0.1 \
  -v "$BASE/tls-contract.test.ts:/app/packages/frontend/scripts/tls-contract.test.ts:ro" \
  -v "$BASE/fixtures/tls-public:/fixtures:ro" \
  -w /app/packages/frontend --entrypoint /bin/sleep tokscale-ci:review 600)
TLS_MOCK=
cleanup_tls() {
  [ -z "$TLS_MOCK" ] || docker rm -f "$TLS_MOCK" >/dev/null
  docker rm -f "$TLS_CLIENT" >/dev/null
}
trap cleanup_tls EXIT HUP INT TERM
TLS_MOCK=$(docker run -d --network="container:$TLS_CLIENT" --read-only \
  --user 65532:65532 --cap-drop=ALL --security-opt=no-new-privileges \
  --memory=128m --cpus=1 \
  -v "$BASE/tls_mock.py:/mock.py:ro" -v "$BASE/fixtures/tls-public:/fixtures:ro" \
  --entrypoint python "$VALIDATION_IMAGE" /mock.py)
docker exec "$TLS_CLIENT" bun test scripts/tls-contract.test.ts
