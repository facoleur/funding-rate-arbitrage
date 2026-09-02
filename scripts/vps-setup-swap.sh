#!/usr/bin/env bash
# One-time: add a 2 GB swapfile as an OOM cushion. Idempotent — safe to re-run.
# Run once on the VPS: sudo bash /srv/arbitrage/scripts/vps-setup-swap.sh
set -euo pipefail

SIZE="${SIZE:-2G}"
FILE="${FILE:-/swapfile}"

if swapon --show | grep -q "$FILE"; then
  echo "swap already active:"
  swapon --show
  exit 0
fi

if [ ! -f "$FILE" ]; then
  fallocate -l "$SIZE" "$FILE" || dd if=/dev/zero of="$FILE" bs=1M count=2048
  chmod 600 "$FILE"
  mkswap "$FILE"
fi

swapon "$FILE"
grep -q "^$FILE " /etc/fstab || echo "$FILE none swap sw 0 0" >> /etc/fstab

# favour keeping app memory resident; only swap under real pressure
sysctl -w vm.swappiness=10
grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf

echo "done:"
swapon --show
free -h
