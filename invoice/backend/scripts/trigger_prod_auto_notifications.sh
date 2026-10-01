#!/usr/bin/env bash
# Ручной запуск авторассылки на prod через admin API.
# Требует: SUPER_ADMIN_USERNAME, SUPER_ADMIN_PASSWORD (или из backend/.env.production)
set -euo pipefail

API_URL="${API_URL:-https://api.invoice.metrix.com.ai}"
TENANT_ID="${TENANT_ID:-}"
FORCE_WINDOW="${FORCE_WINDOW:-false}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$SCRIPT_DIR/../.env.production}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a && source "$ENV_FILE" && set +a
fi

: "${SUPER_ADMIN_USERNAME:?Set SUPER_ADMIN_USERNAME}"
: "${SUPER_ADMIN_PASSWORD:?Set SUPER_ADMIN_PASSWORD}"

TOKEN=$(curl -s -m 30 -X POST "$API_URL/api/admin/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$SUPER_ADMIN_USERNAME\",\"password\":\"$SUPER_ADMIN_PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

if [[ -z "$TOKEN" ]]; then
  echo "ERROR: admin login failed" >&2
  exit 1
fi

BODY='{"force_window":false}'
if [[ "$FORCE_WINDOW" == "true" ]]; then
  BODY='{"force_window":true}'
fi
if [[ -n "$TENANT_ID" ]]; then
  BODY=$(python3 -c "import json; print(json.dumps({'tenant_id': int('$TENANT_ID'), 'force_window': '$FORCE_WINDOW' == 'true'}))")
fi

echo "POST $API_URL/api/admin/auto-notifications/run tenant_id=${TENANT_ID:-all} force=$FORCE_WINDOW"
curl -s -m 600 -X POST "$API_URL/api/admin/auto-notifications/run" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "$BODY"
echo
