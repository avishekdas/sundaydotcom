#!/usr/bin/env bash
# Data/Network Replace/Delete gate (plan M0b story 8, M0B-7): refuse a deploy whose diff would replace or remove
# stateful resources unless the head commit message contains [allow-data-replace]. Fails closed: if the diff
# itself fails, the deploy stops.
set -euo pipefail
cd "$(dirname "$0")/../infra"
for stack in tasklane-dev-network tasklane-dev-data; do
  if ! diff=$(npx -y aws-cdk@2.1146.1 diff "$stack" --no-color 2>&1); then
    echo "$diff" | tail -30
    echo "::error::cdk diff failed for $stack — refusing to deploy (gate fails closed)"; exit 1
  fi
  echo "$diff" | tail -25
  bad=$(echo "$diff" | grep -iE "requires replacement|may be replaced|may cause replacement|replace\]|\[-\] AWS::" || true)
  if [ -n "$bad" ]; then
    if git log -1 --format=%B | grep -q "\[allow-data-replace\]"; then
      echo "::warning::$stack replacement/removal allowed by commit message"; echo "$bad"
    else
      echo "::error::$stack change would replace/remove resources:%0A${bad//$'\n'/%0A}"; exit 1
    fi
  fi
done
