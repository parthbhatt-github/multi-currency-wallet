# Multi-Currency Wallet Platform

Production-minded full-stack wallet challenge implementation with:

- FastAPI backend with clean service boundaries
- React + Vite frontend
- PostgreSQL persistence
- Exchange-rate refresh and conversion traceability
- User-to-user transfers with consistency controls
- Unit and integration test coverage
- Docker Compose, CI, health checks, structured logs, and operational notes

## Setup

Prerequisites:

- Docker and Docker Compose
- Python 3.12 for local backend development
- Node.js 20 for local frontend development

Create local environment files:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

## Run Steps

Run the full stack:

```bash
docker compose up --build
```

Services:

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

Seeded exchange rates are inserted at startup so the platform works even before a third-party refresh succeeds.

## Local Development

Backend:

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Tests:

```bash
cd backend
pytest
```

## Deployment

This repository includes a GitHub Actions workflow in `.github/workflows/ci.yml` that runs backend tests, frontend checks, and Docker image builds. A practical deployment path is:

1. Push to GitHub.
2. Connect the repository to Render, Fly.io, Railway, ECS, or similar.
3. Provision PostgreSQL.
4. Use `render.yaml` as a Render blueprint or deploy the two Docker services manually.
5. Set backend environment variables from `backend/.env.example`.
6. Configure the frontend `VITE_API_BASE_URL` build argument to the deployed backend URL.
7. Add GitHub repository secrets for scheduled exchange refresh:
   - `DEPLOYED_API_BASE_URL`
   - `EXCHANGE_REFRESH_TOKEN`

Public deployment URL: not provisioned from this local environment. The app is containerized and ready for deployment to a public host.

## Assumptions

- Supported currencies are configured in `SUPPORTED_CURRENCIES`.
- All balances are stored as integer minor units.
- Exchange rates are quoted against a configurable base currency, default `USD`.
- External exchange refresh can fail; the platform falls back to the latest non-expired stored rate.
- Profile photos are stored as URLs rather than uploaded binaries.

## Trade-Offs

- The challenge implementation uses SQLAlchemy table creation on startup instead of Alembic migrations to keep review friction low. Production should add migrations.
- The transfer service uses row locks where supported. SQLite tests run without true row-level locking, so PostgreSQL remains the target production database.
- The frontend is intentionally utilitarian and API-driven rather than heavily styled.
- The exchange provider client is replaceable; the bundled implementation supports exchangerate.host-style responses and seeded fallback rates.

## Known Limitations

- No real email verification or password reset flow.
- No KYC, AML screening, sanctions checks, or fraud engine.
- No real object storage integration for profile photos.
- No distributed tracing collector is bundled.
- Public deployment URL and provider credentials must be supplied by the reviewer/operator.

## Detecting Increased 4XX/5XX Errors

The API emits structured JSON logs including method, path, status code, latency, request id, and user id when available. In production:

- Export logs to CloudWatch, Datadog, Grafana Loki, or OpenTelemetry Collector.
- Track `http_requests_total{status_class="4xx"}` and `http_requests_total{status_class="5xx"}`.
- Alert on rolling 5-minute error-rate increases above baseline and absolute thresholds.
- Break down by route, deployment version, and request id for triage.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the scale exercise and deeper design notes.
