#!/usr/bin/env bash
# Выполняет команду на VM 101 через прыжок с Proxmox-хоста.
# Пароль Proxmox-хоста обязателен и берётся из переменной PROXMOX_PASS.
set -euo pipefail

if [[ -z "${PROXMOX_PASS:-}" ]]; then
  echo "Задайте PROXMOX_PASS" >&2
  exit 1
fi

exec ssh -o StrictHostKeyChecking=no -o ConnectTimeout=20 \
  -i ~/.ssh/id_ed25519 \
  -o ProxyCommand="sshpass -p '${PROXMOX_PASS}' ssh -o StrictHostKeyChecking=no -W %h:%p -p 2222 root@94.131.230.101" \
  deploy@192.168.10.4 "$@"
