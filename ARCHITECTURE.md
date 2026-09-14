# Architecture

## System Overview

The platform is split into a FastAPI backend, React frontend, PostgreSQL database, and a scheduled exchange-rate refresh worker endpoint. The backend is organized around domain services rather than route-heavy business logic.

```text
React UI -> FastAPI routers -> Application services -> SQLAlchemy repositories -> PostgreSQL
                                  |
                                  -> Exchange provider client
```

## Domain Model

Core entities:

- `User`: authentication identity, display profile, photo URL, default currency.
- `Wallet`: one user and one currency, with integer minor-unit balance.
- `ExchangeRate`: provider quote, base currency, quote currency, rate, freshness timestamps.
- `Transaction`: immutable ledger-style record of credits, debits, conversions, and transfers.
- `Transfer`: ties together debit and credit transactions for cross-user movement.
- `IdempotencyKey`: prevents duplicate money movement on retried requests.

Money is represented as integer minor units at the boundaries after validation. Decimal arithmetic is used for conversion, rounded half up to the target currency minor unit.

## API Design

Main endpoints:

- `POST /auth/signup`
- `POST /auth/login`
- `GET /me`
- `PATCH /me`
- `GET /wallets`
- `POST /wallets/credit`
- `POST /wallets/debit`
- `POST /transfers`
- `GET /transactions`
- `POST /exchange-rates/refresh`
- `GET /health`
- `GET /ready`

Protected money movement endpoints require an `Idempotency-Key` header.

## Security

- Passwords are hashed with bcrypt through Passlib.
- JWT access tokens are signed with `HS256`.
- Inputs are validated with Pydantic.
- CORS origins are configurable.
- Error responses avoid leaking internals.
- Money movement is wrapped in database transactions.

Production additions:

- Short-lived access tokens plus refresh tokens.
- MFA for risky operations.
- Rate limiting by account, IP, and route.
- Secret rotation and managed secret storage.
- Audit log export to immutable storage.

## Reliability

- Money movement operations are idempotent.
- Transfers debit and credit inside one database transaction.
- Transaction records include exchange-rate id, provider, source amount, target amount, and rate used.
- Exchange refresh stores rates rather than relying on live conversion calls during transfers.
- Health and readiness endpoints separate process liveness from dependency readiness.

## Observability

The backend emits structured logs with request id, route, status code, latency, and authenticated user id when available. Prometheus-style metrics can be added at `/metrics` with `prometheus-fastapi-instrumentator` or OpenTelemetry.

Operational dashboards should include:

- Request rate, latency p50/p95/p99
- 4XX and 5XX rates by route
- Transfer success/failure counts
- Exchange refresh age and failures
- Database connection pool usage
- Queue lag for async jobs

## Scale Exercise

Assumptions:

- 500k registered users
- 20k daily active users
- 100 transactions per second
- Exchange provider downtime

### Scaling Approach

Run the API as horizontally scaled stateless containers behind a load balancer. Use autoscaling on CPU, request latency, and queue depth. Keep all state in PostgreSQL, Redis, object storage, and external observability systems.

At 100 TPS, a carefully indexed PostgreSQL primary can handle the transactional load. Separate read-heavy queries, such as transaction history, from critical write paths through read replicas or dedicated projections once needed.

### Database Strategy

Use PostgreSQL with:

- `users.email` unique index
- `wallets(user_id, currency)` unique index
- `transactions(user_id, created_at)` index
- `transactions(wallet_id, created_at)` index
- `idempotency_keys(user_id, key)` unique index

Use row-level locks on the affected wallets during transfers. Keep transactions short. Partition transaction history by month when volume grows enough to affect maintenance or query latency.

For ledger-grade rigor, evolve from balance-on-wallet plus transaction rows to double-entry accounting tables:

- `ledger_accounts`
- `ledger_entries`
- `ledger_postings`

### Caching

Cache exchange rates in Redis with a short TTL and persist every provider refresh to PostgreSQL. Conversion should use the latest acceptable persisted rate, not a synchronous provider call.

Cache read-only profile and settings data cautiously. Do not cache wallet balances unless using strict invalidation or read-through projections because stale balances create support and trust issues.

### Async Processing

Use a queue such as Celery/RQ/Arq for:

- Exchange-rate refresh
- Email and notification jobs
- Fraud/risk scoring
- Webhook delivery
- Ledger reconciliation jobs
- Analytics projections

Critical money movement remains synchronous and transactional. Non-critical side effects happen after commit through an outbox table to avoid dropped events.

### Cost Optimisation

- Start with one regional PostgreSQL primary plus managed backups.
- Use autoscaling API containers with conservative minimums.
- Cache exchange rates to reduce provider calls.
- Keep frontend on static hosting/CDN.
- Use log sampling for high-volume successful requests while retaining full logs for errors and money movement.
- Introduce read replicas only when query patterns justify the cost.

### Exchange Provider Downtime

The platform continues using the most recent stored rate until a configured staleness threshold. If rates become too stale:

- Disable conversions and cross-currency transfers.
- Continue same-currency transfers.
- Surface a clear retryable error.
- Alert operations on provider outage and stale-rate age.

For resilience, support multiple exchange providers with priority order, circuit breakers, and provider-specific quality checks.
