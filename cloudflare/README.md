# Cloudflare earnings runtime

Cloudflare is the sole production scheduler and compute runtime for the earnings pipeline.

- `worker.mjs` converts one half-hour UTC Cron Trigger into DST-safe New York schedule slots and creates one durable Workflow instance per job.
- `EarningsJobWorkflow` dispatches a named Cloudflare Container and polls it to a terminal result.
- `container_server.py` runs the existing Python commands without a Render adapter or public origin.
- `wrangler.earnings.jsonc` is the production scheduler/runtime source of truth. The root `wrangler.jsonc` remains the separate dashboard Worker.

The production config pins the Container by immutable Cloudflare Registry digest. `Dockerfile.earnings` and the one-day GitHub build artifact provide a reproducible release path without exposing the private image.

The pre-earnings job runs at 5:00 p.m. New York time for the next business day's reporters. Weekly radar runs Sunday at 5:00 p.m. New York time. All scheduled instance IDs are deterministic, and `createBatch` makes duplicate cron delivery idempotent.

Useful commands:

```bash
npm run test:cloudflare
npm run cloudflare:types
npm run cloudflare:dry-run
npm run cloudflare:deploy
```

The protected manual API accepts `POST /api/jobs/run` with a bearer token equal to the existing archive admin secret. Example body:

```json
{
  "jobName": "post-bmo",
  "runId": "manual-post-bmo-2026-08-20-wmt",
  "forDate": "2026-08-20",
  "watchlist": "WMT"
}
```

Use `GET /api/jobs/status?runId=...` with the same authorization to inspect the Workflow output.
