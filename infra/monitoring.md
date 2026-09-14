# Monitoring and Alerting

## Signals

- API request rate, latency, and error rate by route.
- 4XX and 5XX counts grouped by deployment version.
- Exchange-rate freshness and refresh failures.
- Transfer failure rate and insufficient-funds rate.
- PostgreSQL CPU, locks, deadlocks, connections, replication lag, and slow queries.

## Example Alerts

- 5XX rate above 1% for 5 minutes.
- 4XX rate doubles compared with the same hour's 7-day baseline.
- p95 API latency above 500 ms for 10 minutes.
- Exchange rates older than the configured maximum age.
- Database connection pool saturation above 85%.

## Runbook

1. Check dashboard by route and deployment version.
2. Inspect structured logs using request id and user id.
3. Compare error spike with the latest deployment.
4. Check database health, locks, and slow queries.
5. Roll back if a release-correlated 5XX spike persists.
6. Disable cross-currency operations if exchange rates are stale.
