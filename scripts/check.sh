#!/usr/bin/env bash
# Same gates as CI, run before every push.
set -euo pipefail
cd "$(dirname "$0")/.."
(cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run lint-imports \
  && uv run pytest -q --cov=tasklane --cov-fail-under=90)
(cd infra && uv run ruff check . && uv run ruff format --check . && uv run pytest -q)
(cd web && npx tsc -b && npx vitest run --reporter=dot)
