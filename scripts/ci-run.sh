#!/usr/bin/env bash
# Run a command; on failure surface the last 60 log lines as a GitHub annotation (readable via the API).
set -o pipefail
log=$(mktemp)
"$@" 2>&1 | tee "$log"
rc=${PIPESTATUS[0]}
grep -E "converged|North star" "$log" | head -5 | while read -r l; do echo "::notice::$l"; done
if [ "$rc" -ne 0 ]; then
  msg=$(grep -vE "^\s*$" "$log" | tail -40 | cut -c1-300 | sed ':a;N;$!ba;s/%/%25/g;s/\n/%0A/g')
  echo "::error title=$1 failed::${msg}"
fi
exit "$rc"
