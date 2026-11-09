#!/bin/sh
# Private nonsecret setup review only; never mount inputs or execute host Python.
set -eu
blocked() { echo "BLOCKED: ${1:-invalid setup action or nonsecret input file; no configuration applied.}" >&2; exit 2; }
[ "$#" -eq 2 ] || blocked
ACTION=$1
case "$ACTION" in
  cluster-assess|cluster-packet|plugin-render|plugin-check|conversation-render|native-message-render|native-event-render|native-log-diagnostic-render) ;;
  *) blocked ;;
esac
INPUT=$2
case "$INPUT" in /*.json) ;; *) blocked ;; esac
# No pipes, devices, directories or symlink files. The enclosing directory may
# resolve through a symlink, but the resolved input must stay outside the build.
[ -f "$INPUT" ] && [ -r "$INPUT" ] && [ ! -L "$INPUT" ] || blocked
ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
DIRECTORY=$(CDPATH='' cd -- "$(dirname -- "$INPUT")" 2>/dev/null && pwd -P) || blocked
case "$DIRECTORY/" in "$ROOT/"*) blocked ;; esac
INPUT="$DIRECTORY/$(basename -- "$INPUT")"
case "$INPUT" in
  */.codex/*|*/.ssh/*|*/.aws/*|*/.kube/*|*/.docker/*|*/.gnupg/*|*/.env*|*/auth.json|*/credentials*.json|*/kubeconfig*.json|*/history/*|*/sessions/*) blocked ;;
esac
# Host shell inspects size/type only, never validates or renders JSON.
SIZE=$(wc -c 2>/dev/null < "$INPUT") || blocked
[ "$SIZE" -gt 0 ] && [ "$SIZE" -le 65536 ] || blocked
command -v docker >/dev/null 2>&1 || blocked 'Docker CLI unavailable; no host fallback or daemon startup.'
# Pin and recheck the opened file, then take one bounded private snapshot before
# any long Docker operation. Never reopen the caller's path after this point.
# This assumes a caller-controlled file, not a hostile same-user filesystem.
{ exec 3< "$INPUT"; } 2>/dev/null || blocked
[ -f /dev/fd/3 ] && [ ! -L "$INPUT" ] && [ "$INPUT" -ef /dev/fd/3 ] || blocked
umask 077
STAGING=$(mktemp -d /tmp/infra-setup.XXXXXXXX 2>/dev/null) || blocked
trap 'rm -rf -- "$STAGING"' EXIT
trap 'exit 2' HUP INT TERM
STAGING=$(CDPATH='' cd -- "$STAGING" 2>/dev/null && pwd -P) || blocked
case "$STAGING/" in "$ROOT/"*) blocked ;; esac
head -c 65537 <&3 > "$STAGING/input.json" 2>/dev/null || blocked
exec 3<&-
SIZE=$(wc -c < "$STAGING/input.json")
[ "$SIZE" -gt 0 ] && [ "$SIZE" -le 65536 ] || blocked
# Private bytes must not follow an ambient remote Docker context. Pin the
# resolved local Unix endpoint for every subsequent Docker command.
ENDPOINT=${DOCKER_HOST:-}
if [ -n "${DOCKER_CONTEXT:-}" ]; then ENDPOINT=''; fi
if [ -z "$ENDPOINT" ]; then
  CONTEXT=$(docker context show 2>/dev/null) || blocked 'Docker context unavailable; no configuration applied.'
  ENDPOINT=$(docker context inspect "$CONTEXT" --format '{{.Endpoints.docker.Host}}' 2>/dev/null) || blocked 'Docker endpoint unavailable; no configuration applied.'
fi
case "$ENDPOINT" in unix:///*) ;; *) blocked 'Setup requires an already authorized local Unix Docker endpoint.' ;; esac
# Empty transient CLI configuration prevents automatic proxy/environment/header
# injection from the user's Docker config. No credentials are copied or changed.
CLI_CONFIG="$STAGING/docker"
mkdir "$CLI_CONFIG" 2>/dev/null || blocked 'Temporary Docker configuration unavailable.'
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH DOCKER_CUSTOM_HEADERS BUILDX_BUILDER BUILDKIT_HOST
docker --config "$CLI_CONFIG" --host "$ENDPOINT" info >/dev/null 2>&1 || blocked 'Docker daemon unavailable; do not start it for this operation.'
cd "$ROOT"
# Build never receives private stdin; input is outside the build context.
# Capture the exact image ID, avoiding mutable-tag races. Hide build diagnostics
# here so stdout is exclusively one review JSON document and errors stay fixed.
IMAGE=$(docker --config "$CLI_CONFIG" --host "$ENDPOINT" build --quiet --platform linux/amd64 -f validation/Dockerfile . 2>/dev/null) || blocked 'Validation image build failed; input was not delivered to a container.'
case "$IMAGE" in sha256:*) ;; *) blocked 'Validation image ID unavailable; no setup container started.' ;; esac
DIGEST=${IMAGE#sha256:}
[ "${#DIGEST}" -eq 64 ] || blocked 'Invalid validation image ID; no setup container started.'
case "$DIGEST" in *[!0-9a-f]*) blocked 'Invalid validation image ID; no setup container started.' ;; esac
# Recheck size and validate schema inside Docker. No input path, private environment,
# host mount or socket is passed to the container, and its output is not logged.
# Redirection is read-only; the temporary input snapshot is removed on exit.
docker --config "$CLI_CONFIG" --host "$ENDPOINT" run --rm -i --pull=never --log-driver=none \
  --network=none --read-only --user 65532:65532 \
  --cpus=1 --memory=256m --pids-limit=32 --cap-drop=ALL \
  --security-opt=no-new-privileges --tmpfs /tmp:rw,nosuid,nodev,noexec,size=16m \
  "$IMAGE" setup --action "$ACTION" 2>/dev/null < "$STAGING/input.json" || blocked 'Setup container failed or rejected JSON; no configuration applied.'
