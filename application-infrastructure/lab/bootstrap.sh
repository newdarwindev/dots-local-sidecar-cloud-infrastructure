#!/bin/sh
# Generate lab-only service keys privately. Never reuse source/account credentials.
set -eu
umask 077
[ "$#" -eq 4 ] || { echo 'Usage: sh bootstrap.sh CONTEXT CLUSTER_UID NAMESPACE_UID NEW_PRIVATE_DIRECTORY' >&2; exit 2; }
LAB_CONTEXT=$1
[ "$(kubectl --context "$LAB_CONTEXT" get ns kube-system -o jsonpath='{.metadata.uid}')" = "$2" ] || exit 2
[ "$(kubectl --context "$LAB_CONTEXT" get ns dots-synthetic-lab -o jsonpath='{.metadata.uid}')" = "$3" ] || exit 2
LAB_PRIVATE=$4
case "$LAB_PRIVATE" in /*) ;; *) exit 2 ;; esac
LAB_REPO=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
case "$LAB_PRIVATE/" in "$LAB_REPO/"*) echo 'Keep lab keys outside Git.' >&2; exit 2 ;; esac
for LAB_SECRET in langfuse-bootstrap langfuse-postgresql-auth langfuse-redis-auth langfuse-clickhouse-auth langfuse-s3-auth homarr-workload-encryption; do
  [ -z "$(kubectl --context "$LAB_CONTEXT" -n dots-synthetic-lab get secret "$LAB_SECRET" --ignore-not-found -o name)" ] || {
    echo 'Lab keys already exist; reconcile them without rotation.' >&2; exit 2;
  }
done
mkdir -m 700 "$LAB_PRIVATE"
for LAB_SECRET in langfuse-bootstrap langfuse-postgresql-auth langfuse-redis-auth langfuse-clickhouse-auth langfuse-s3-auth homarr-workload-encryption; do
  mkdir -m 700 "$LAB_PRIVATE/$LAB_SECRET"
done
for LAB_KEY in salt encryption-key nextauth-secret; do
  openssl rand -hex 32 | tr -d '\n' > "$LAB_PRIVATE/langfuse-bootstrap/$LAB_KEY"
done
for LAB_KEY in POSTGRES_PASSWORD USERDB_PASSWORD; do
  openssl rand -hex 32 | tr -d '\n' > "$LAB_PRIVATE/langfuse-postgresql-auth/$LAB_KEY"
done
printf langfuse > "$LAB_PRIVATE/langfuse-postgresql-auth/POSTGRES_DB"
printf langfuse > "$LAB_PRIVATE/langfuse-postgresql-auth/USERDB_USER"
openssl rand -hex 32 | tr -d '\n' > "$LAB_PRIVATE/langfuse-redis-auth/default"
openssl rand -hex 32 | tr -d '\n' > "$LAB_PRIVATE/langfuse-clickhouse-auth/password"
openssl rand -hex 16 | tr -d '\n' > "$LAB_PRIVATE/langfuse-s3-auth/accessKey"
openssl rand -hex 32 | tr -d '\n' > "$LAB_PRIVATE/langfuse-s3-auth/secretKey"
printf '{"identities":[{"name":"synthetic-lab","credentials":[{"accessKey":"%s","secretKey":"%s"}],"actions":["Admin","Read","Write","List","Tagging"]}]}' \
  "$(cat "$LAB_PRIVATE/langfuse-s3-auth/accessKey")" "$(cat "$LAB_PRIVATE/langfuse-s3-auth/secretKey")" \
  > "$LAB_PRIVATE/langfuse-s3-auth/seaweedfs_s3_config"
openssl rand -hex 32 | tr -d '\n' > "$LAB_PRIVATE/homarr-workload-encryption/db-encryption-key"
for LAB_SECRET in langfuse-bootstrap langfuse-postgresql-auth langfuse-redis-auth langfuse-clickhouse-auth langfuse-s3-auth homarr-workload-encryption; do
  kubectl --context "$LAB_CONTEXT" -n dots-synthetic-lab create secret generic "$LAB_SECRET" --from-file="$LAB_PRIVATE/$LAB_SECRET"
done
echo 'Lab-only keys installed; private originals retained. No source credentials used.'
