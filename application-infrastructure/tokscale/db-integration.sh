#!/bin/sh
# Local-only disposable PostgreSQL qualification; no host ports or credentials.
# Invoke only through validation/run.sh's explicit local database test option.
set -eu
[ "${1:-}" = --local ] && [ "$#" -eq 1 ] || exit 2
: "${VALIDATION_IMAGE:?Use the committed validation runner}"
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
BASE="$ROOT/application-infrastructure/tokscale"
APP=$(docker image inspect tokscale-ci:review --format '{{.Id}}')
[ "$APP" = sha256:c00d1142738b8d503e963c25488e9fe73c507043216c639fb6608816e869f4d3 ] || {
  echo 'BLOCKED: Tokscale image differs from the reviewed local candidate.' >&2; exit 2;
}
VALIDATOR=$(docker image inspect "$VALIDATION_IMAGE" --format '{{.Id}}')
PG=$(docker run --rm --network=none --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  -v "$BASE/images.lock.json:/images.json:ro" --entrypoint python "$VALIDATOR" \
  -c 'import json; print("postgres@"+json.load(open("/images.json"))["images"]["postgres"]["digest"])')
docker image inspect "$PG" >/dev/null
mkdir -p "$ROOT/application-infrastructure/.runtime"
OUT=$(mktemp -d "$ROOT/application-infrastructure/.runtime/tokscale-db.XXXXXX")
printf '%s\n' "$APP" "$PG" > "$OUT/images.txt"
CLIENT=
DATABASE=
finish() {
  status=$?
  trap - EXIT HUP INT TERM
  if [ -n "$DATABASE" ]; then
    docker exec "$DATABASE" cat /state/postgres.log > "$OUT/postgres.log" 2>&1 || true
    docker logs "$DATABASE" > "$OUT/postgres-container.log" 2>&1 || true
  fi
  if [ -n "$CLIENT" ]; then docker logs "$CLIENT" > "$OUT/client-container.log" 2>&1 || true; fi
  # Retain containers and their logs; never rm/prune/delete volumes or history.
  [ -z "$DATABASE" ] || docker stop "$DATABASE" >> "$OUT/stopped.txt" 2>&1 || true
  [ -z "$CLIENT" ] || docker stop "$CLIENT" >> "$OUT/stopped.txt" 2>&1 || true
  printf 'exit=%s\n' "$status" > "$OUT/result.txt"
  printf 'Tokscale synthetic database receipts: %s (exit %s)\n' "$OUT" "$status"
  exit "$status"
}
trap finish EXIT HUP INT TERM
CLIENT=$(docker run -d --network=none --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  --memory=1g --cpus=2 --pids-limit=128 --tmpfs /tmp:rw,nosuid,nodev,size=64m \
  --add-host agent1:127.0.0.1 --add-host wrongname:127.0.0.1 \
  -e DATABASE_URL=postgresql://postgres:PUBLIC_TEST_VALUE@agent1:5432/postgres -e DATABASE_SSL=verify-full \
  -e DATABASE_CA_FILE=/fixtures/ca1-cert.pem.fixture \
  -v "$BASE/fixtures/tls-public:/fixtures:ro" \
  -v "$BASE/db-integration.ts:/app/packages/frontend/scripts/db-integration.ts:ro" \
  -w /app/packages/frontend --entrypoint /bin/sleep "$APP" 900)
DATABASE=$(docker run -d --network="container:$CLIENT" --read-only --user 70:70 \
  --cap-drop=ALL --security-opt=no-new-privileges --memory=512m --cpus=2 --pids-limit=128 \
  --tmpfs /state:rw,nosuid,nodev,size=256m,uid=70,gid=70,mode=0700 \
  --tmpfs /var/lib/postgresql/data:rw,nosuid,nodev,size=1m,uid=70,gid=70 \
  -v "$BASE/fixtures/tls-public:/fixtures:ro" --entrypoint /bin/sh "$PG" -ec '
    cp /fixtures/agent1-key.pem.fixture /state/server.key
    chmod 600 /state/server.key
    initdb -D /state/data --auth=trust --no-locale
    printf "listen_addresses = '\''127.0.0.1'\''\nunix_socket_directories = '\''/state'\''\nssl = on\nssl_cert_file = '\''/fixtures/agent1-cert.pem.fixture'\''\nssl_key_file = '\''/state/server.key'\''\n" >> /state/data/postgresql.conf
    pg_ctl -D /state/data -l /state/postgres.log -w start
    exec sleep 900')
printf '%s\n' "$CLIENT" "$DATABASE" > "$OUT/containers.txt"
ready=0
for _attempt in $(seq 1 60); do
  if docker exec "$DATABASE" pg_isready -h 127.0.0.1 > /dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
[ "$ready" = 1 ]
run() {
  docker exec "$CLIENT" bun scripts/db-integration.ts "$1" > "$OUT/$1.log" 2>&1
  cat "$OUT/$1.log"
}
run baseline
run negative
run child-retry
run reconnect & reconnect=$!
ready=0
for _attempt in $(seq 1 60); do
  if docker exec "$CLIENT" test -f /tmp/reconnect-ready; then ready=1; break; fi
  sleep 1
done
[ "$ready" = 1 ]
docker exec "$DATABASE" pg_ctl -D /state/data -m fast -w stop > "$OUT/restart.log" 2>&1
run retry & retry=$!
sleep 5
docker exec "$DATABASE" pg_ctl -D /state/data -l /state/postgres.log -w start >> "$OUT/restart.log" 2>&1
docker exec "$CLIENT" sh -c 'echo ready > /tmp/reconnect-resume'
wait "$reconnect"
wait "$retry"
grep -q 'could not reach DB to acquire migration advisory lock' "$OUT/retry.log"
grep -q 'drizzle-kit migrate hit a transient' "$OUT/child-retry.log"
docker exec "$DATABASE" pg_ctl -D /state/data -m fast -w stop > "$OUT/plaintext-restart.log" 2>&1
docker exec "$DATABASE" pg_ctl -D /state/data -l /state/postgres.log -o '-c ssl=off' -w start >> "$OUT/plaintext-restart.log" 2>&1
run plaintext
echo 'PASS real PostgreSQL TLS/migrations/load/process-restart/retry; NOT backup or encrypted recovery.'
