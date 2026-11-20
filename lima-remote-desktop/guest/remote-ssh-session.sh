#!/usr/bin/env bash
set -euo pipefail

machine=$1
printf 'Connecting to %s over SSH\n' "$machine"
ssh -o StrictHostKeyChecking=yes -o ConnectTimeout=8 -o ServerAliveInterval=30 "$machine"
