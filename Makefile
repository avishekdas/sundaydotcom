.PHONY: dev check test-e2e
# Local stack (DL-9): embedded PostgreSQL 18.6 + real api handler + in-process bus + local WebSocket (:8000),
# Vite dev server with proxy (:5173). Open http://localhost:5173 — signed in as the seeded dev user.
dev:
	@cd web && npm install --no-audit --no-fund --loglevel=error
	@trap 'kill 0' EXIT; (cd backend && uv run python -m tasklane.devserver.app) & (cd web && npx vite --port 5173) & wait

check:
	./scripts/check.sh

test-e2e:  # against a running stack: BASE_URL=... E2E_EMAIL=... E2E_PASSWORD=...
	cd e2e && npx playwright test
