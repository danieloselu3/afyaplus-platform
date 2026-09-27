#!/usr/bin/env bash
# curl_evidence.sh - prove 200 / 401 / 403 / 422 / 429 against a running triage API.
# Usage: bash scripts/curl_evidence.sh [base_url]  > evidence/01_secure_api_curl.txt
BASE="${1:-http://127.0.0.1:8000}"
JSON="Content-Type: application/json"
GOOD='{"patient_message": "I have chest pain and feel dizzy", "county": "Kisumu"}'

show() {  # show "<title>" <curl args...>
  echo "=== $1"
  shift
  echo "\$ curl $*" | sed -E 's/Bearer [A-Za-z0-9._-]+/Bearer <token>/'
  curl -s -w '\n--> HTTP %{http_code}\n\n' "$@"
}
token() {
  curl -s -X POST "$BASE/token" -H "$JSON" -d "{\"username\": \"$1\", \"password\": \"$2\"}" \
    | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])"
}

echo "# AfyaPlus triage API evidence - $(date -u +%Y-%m-%dT%H:%M:%SZ) - $BASE"
echo

echo "## 200: health is open, login works, triage answers"
show "GET /health (no token needed)" "$BASE/health"
show "POST /token as mercy (coordinator)" -X POST "$BASE/token" -H "$JSON" \
  -d '{"username": "mercy", "password": "logistics2026"}'
MERCY=$(token mercy logistics2026)
GUEST=$(token guest viewonly2026)
show "POST /triage red-flag message, coordinator token" -X POST "$BASE/triage" -H "$JSON" \
  -H "Authorization: Bearer $MERCY" -d "$GOOD"
show "POST /triage everyday message, coordinator token" -X POST "$BASE/triage" -H "$JSON" \
  -H "Authorization: Bearer $MERCY" -d '{"patient_message": "My child has had a runny nose and mild cough for two days", "county": "Vihiga"}'

echo "## 401: who are you?"
show "POST /triage with no token" -X POST "$BASE/triage" -H "$JSON" -d "$GOOD"
show "POST /triage with a garbage token" -X POST "$BASE/triage" -H "$JSON" \
  -H "Authorization: Bearer not.a.real.token" -d "$GOOD"
show "POST /token with the wrong password" -X POST "$BASE/token" -H "$JSON" \
  -d '{"username": "mercy", "password": "wrong-password"}'

echo "## 403: we know you, and the answer is no"
show "POST /triage with a valid VIEWER token (guest)" -X POST "$BASE/triage" -H "$JSON" \
  -H "Authorization: Bearer $GUEST" -d "$GOOD"

echo "## 422: rejected at the door, the model never runs"
show "(a) message too short" -X POST "$BASE/triage" -H "$JSON" -H "Authorization: Bearer $MERCY" \
  -d '{"patient_message": "hi", "county": "Kisumu"}'
show "(b) county missing" -X POST "$BASE/triage" -H "$JSON" -H "Authorization: Bearer $MERCY" \
  -d '{"patient_message": "I feel unwell today"}'
show "(c) body is not JSON" -X POST "$BASE/triage" -H "$JSON" -H "Authorization: Bearer $MERCY" \
  -d 'not json at all'
show "(d) unexpected extra field" -X POST "$BASE/triage" -H "$JSON" -H "Authorization: Bearer $MERCY" \
  -d '{"patient_message": "I feel unwell today", "county": "Kisumu", "priority": "vip"}'

echo "## 429: authenticated is not unlimited (5 triage calls per minute; 2 already used above)"
for i in 1 2 3 4 5; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/triage" -H "$JSON" \
    -H "Authorization: Bearer $MERCY" -d '{"patient_message": "I feel a little tired today", "county": "Kisii"}')
  echo "burst call $i --> HTTP $code"
done
