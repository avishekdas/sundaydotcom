#!/usr/bin/env bash
# AC-K7-2 on dev (D-046): IP A = this runner, IP B = the tasklane-dev-ip-probe λ (AWS egress through CloudFront).
# 5 wrong passwords from IP A → 401 each; the 6th (correct) from IP A → 429; a correct one from IP B → 200 ≤ 35 s.
# Needs BASE_URL, E2E_OUTSIDER_EMAIL / _PASSWORD and the deploy role (may invoke the probe).
set -euo pipefail
FN=tasklane-dev-ip-probe
OUT=$(mktemp)
email="$E2E_OUTSIDER_EMAIL"; pw="$E2E_OUTSIDER_PASSWORD"

probe() { aws lambda invoke --function-name "$FN" --cli-binary-format raw-in-base64-out --payload "$1" "$OUT" >/dev/null; cat "$OUT"; }
clear_counters() { probe "$(jq -nc --arg e "$email" '{action:"clear_counters", email:$e}')" >/dev/null; }
signin() {
  curl -s -o /dev/null -w '%{http_code}' -X POST -H 'content-type: application/json' \
    -d "$(jq -nc --arg e "$email" --arg p "$1" '{email:$e, password:$p}')" "$BASE_URL/api/auth/sign-in"
}

clear_counters
trap clear_counters EXIT
for i in 1 2 3 4 5; do
  c=$(signin "Wrong-password-$i")
  [ "$c" = 401 ] || { echo "::error::attempt $i from IP A answered $c (want 401)"; exit 1; }
done
c=$(signin "$pw")
[ "$c" = 429 ] || { echo "::error::6th attempt from IP A answered $c (want 429 even with the right password)"; exit 1; }
res=$(probe "$(jq -nc --arg e "$email" --arg p "$pw" '{action:"sign_in", email:$e, password:$p}')")
status=$(echo "$res" | jq -r .status); took=$(echo "$res" | jq -r .elapsed_s)
if [ "$status" != 200 ] || ! awk "BEGIN { exit !($took <= 35) }"; then
  echo "::error::IP B answered $status after ${took}s (want 200 within 35 s)"; exit 1
fi
echo "::notice::AC-K7-2 on dev: IP A 5×401 then 429; IP B 200 in ${took}s"
