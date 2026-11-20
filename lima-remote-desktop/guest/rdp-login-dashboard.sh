#!/usr/bin/env bash
set -euo pipefail
umask 077

config="${XDG_CONFIG_HOME:-$HOME/.config}/lima-remote-desktop/targets.env"
if [[ ! -r "$config" ]]; then
    notify-send 'RDP dashboard' 'Configure the two local RDP targets.' || true
    exit 1
fi
# shellcheck disable=SC1090
source "$config"
fingerprint_pattern='^([0-9a-fA-F]{2}:){31}[0-9a-fA-F]{2}$'
if [[ ! ${LEFT_CERT_SHA256:-} =~ $fingerprint_pattern ||
      ! ${RIGHT_CERT_SHA256:-} =~ $fingerprint_pattern ||
      -z ${LEFT_RDP_USER:-} || -z ${RIGHT_RDP_USER:-} ||
      ! ${RIGHT_RDP_HOST:-} =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]]; then
    notify-send 'RDP dashboard' 'Check the local account, host and SHA-256 certificate pins.' || true
    exit 1
fi

runtime_dir="${XDG_RUNTIME_DIR:?}/rdp-login-dashboard"
install -d -m 700 "$runtime_dir"
exec 9>"$runtime_dir/lock"
if ! flock -n 9; then
    exec "$HOME/.local/bin/rdp-dashboard-tile"
fi

keyring_unlocked() {
    [[ $(busctl --user get-property org.freedesktop.secrets /org/freedesktop/secrets/collection/login \
        org.freedesktop.Secret.Collection Locked 2>/dev/null) == 'b false' ]]
}

for _ in {1..45}; do
    if keyring_unlocked; then break; fi
    sleep 1
done
if ! keyring_unlocked; then
    notify-send 'RDP dashboard' 'Unlock the Mac login keychain, then reopen this dashboard.' || true
    exit 1
fi
for slot in rdp-left rdp-right; do
    if ! secret-tool lookup application rdp-dashboard host "$slot" >/dev/null; then
        notify-send 'RDP dashboard' 'Enroll both RDP passwords in the login keyring.' || true
        exit 1
    fi
done

read -r display_width display_height < <(xdotool getdisplaygeometry)
rdp_width=$((display_width / 2 - 4))
rdp_height=$((display_height * 72 / 100 - 4))

tunnel_socket="$runtime_dir/left.ssh"
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 \
    -M -S "$tunnel_socket" -fNT -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -L 127.0.0.1:13389:127.0.0.1:3389 rdp-left 9>&-
left_pid=
right_pid=
cleanup() {
    for child in "$left_pid" "$right_pid"; do
        if [[ -n "$child" ]]; then kill "$child" 2>/dev/null || true; fi
    done
    ssh -S "$tunnel_socket" -O exit rdp-left >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 0' HUP INT TERM

connect() {
    local slot=$1 endpoint=$2 account=$3 fingerprint=$4 title=$5 password
    password=$(secret-tool lookup application rdp-dashboard host "$slot")
    exec xfreerdp "/v:$endpoint" "/u:$account" /from-stdin:force \
        "/cert:fingerprint:sha256:$fingerprint" "/t:$title" "/wm-class:dashboard-$slot" \
        "/size:${rdp_width}x${rdp_height}" /smart-sizing -clipboard < <(printf '%s\n' "$password") 9>&-
}

connect rdp-left 127.0.0.1:13389 "$LEFT_RDP_USER" "$LEFT_CERT_SHA256" 'Left RDP' >"$runtime_dir/left.log" 2>&1 &
left_pid=$!
connect rdp-right "$RIGHT_RDP_HOST:3389" "$RIGHT_RDP_USER" "$RIGHT_CERT_SHA256" 'Right RDP' >"$runtime_dir/right.log" 2>&1 &
right_pid=$!

last_layout=
while kill -0 "$left_pid" 2>/dev/null || kill -0 "$right_pid" 2>/dev/null; do
    layout=$(wmctrl -d; wmctrl -lGx | awk '/dashboard-|SSH Workbench/ {print $1, $3, $4, $5, $6}')
    if [[ "$layout" != "$last_layout" ]]; then
        "$HOME/.local/bin/rdp-dashboard-tile"
        last_layout=$layout
    fi
    sleep 1
done
wait "$left_pid" "$right_pid" || true
