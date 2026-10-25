#!/usr/bin/env bash
# Data-stack Replace/Delete gate (plan M0b story 8): refuse a deploy whose diff would replace or remove stateful
# resources unless the head commit message contains [allow-data-replace].
set -euo pipefail
cd "$(dirname "$0")/../infra"
diff=$(npx -y aws-cdk@2.1146.1 diff tasklane-dev-data --no-color 2>&1 || true)
echo "$diff" | tail -40
bad=$(echo "$diff" | grep -E "requires replacement|may be replaced|\[-\] AWS::(RDS|SecretsManager|KMS|EC2::VPC)" || true)
if [ -n "$bad" ]; then
  if git log -1 --format=%B | grep -q "\[allow-data-replace\]"; then
    echo "::warning::data-stack replacement allowed by commit message"; echo "$bad"
  else
    echo "::error::data stack change would replace/delete stateful resources:%0A${bad//$'\n'/%0A}"; exit 1
  fi
fi
