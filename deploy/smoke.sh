#!/usr/bin/env bash
# Post-deploy smoke test.  Usage: deploy/smoke.sh <api-url> [web-url]
# Checks liveness, readiness, that unauthenticated calls are refused with the
# error envelope, and (with a web URL) that the web tier serves the app and
# proxies /api to the API. Exits non-zero on the first failure.
set -euo pipefail

API="${1:?usage: smoke.sh <api-url> [web-url]}"
WEB="${2:-}"
API="${API%/}"
WEB="${WEB%/}"
RETRIES="${SMOKE_RETRIES:-30}"

fail() { echo "FAIL: $*" >&2; exit 1; }

wait_for() { # url, expected-substring
  local url="$1" expect="$2" body=""
  for _ in $(seq 1 "$RETRIES"); do
    body="$(curl -fsS -m 10 "$url" 2>/dev/null || true)"
    [[ "$body" == *"$expect"* ]] && return 0
    sleep 2
  done
  fail "$url did not return '$expect' (last body: ${body:-<none>})"
}

check_unauthorized() { # url
  local out code
  out="$(curl -sS -m 10 -o /tmp/smoke-body -w '%{http_code}' "$1")"
  code="$out"
  [[ "$code" == "401" ]] || fail "$1 returned HTTP $code without a token (expected 401)"
  grep -q '"unauthorized"' /tmp/smoke-body || fail "$1 did not return the error envelope"
}

wait_for "$API/health" '"ok"'
echo "ok   API live      $API/health"
wait_for "$API/ready" '"ready"'
echo "ok   API ready     $API/ready"
check_unauthorized "$API/api/v1/organizations"
echo "ok   API refuses unauthenticated requests"

if [[ -n "$WEB" ]]; then
  for _ in $(seq 1 "$RETRIES"); do
    curl -fsS -m 10 -o /dev/null "$WEB/" 2>/dev/null && break
    sleep 2
  done
  curl -fsS -m 10 -o /dev/null "$WEB/" || fail "$WEB/ is not serving"
  echo "ok   web serves    $WEB/"
  check_unauthorized "$WEB/api/v1/organizations"
  echo "ok   web proxies /api to the API (401 envelope came back through it)"
fi
echo "smoke test passed"
