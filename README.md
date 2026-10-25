# Tasklane

A self-hosted work-management + CRM platform (functional replica of monday.com Work Management + CRM) for one organization, serverless on AWS.

- Requirements, architecture and plan: [`docs/`](docs/) — start with `docs/00-decision-log.md`, `docs/02-requirements/README.md`, `docs/03-architecture/README.md`, `docs/04-plan/implementation-plan.md`.
- Backend: Python 3.13 (`backend/`, managed with `uv`).
- Frontend: React + TypeScript (`web/`).
- Infrastructure: AWS CDK in Python (`infra/`).

## Local development
```bash
cd backend
uv sync
uv run pytest            # unit + integration (starts an embedded PostgreSQL 18 automatically)
```
