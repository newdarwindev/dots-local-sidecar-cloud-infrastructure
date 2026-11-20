#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
instance=remote-desktop
if limactl list --format '{{.Name}}' | grep -Fxq "$instance"; then
    echo 'The remote-desktop instance already exists. Keep it and use the migration notes in the README.' >&2
    exit 1
fi
limactl start --tty=false --name "$instance" "$repo_dir/remote-desktop.yaml"
stage=$(limactl shell --workdir /tmp "$instance" mktemp -d)
limactl copy --backend=scp -r "$repo_dir/guest" "$instance:$stage/"
limactl shell --workdir /tmp "$instance" bash "$stage/guest/install.sh"
limactl restart --tty=false "$instance"
