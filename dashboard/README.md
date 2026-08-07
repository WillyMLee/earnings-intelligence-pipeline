# Earnings Intelligence Dashboard

A small, public, read-only dashboard for browsing the earnings results the
rest of this repo's pipeline archives to Convex — grouped by sector, with
each report's actual-vs-consensus figures and a short "what mattered"
summary.

Built as a static site (Vite + React + Tailwind) that talks to Convex's
HTTP query API directly — no server of its own, and no write/admin token
is ever used or shipped to the client. Deployed as a Cloudflare Worker with
static assets and an edge proxy for intraday index data.

## Run locally

```bash
npm install
cp .env.example .env.local   # point VITE_CONVEX_URL at your deployment
npm run dev
```

## Deploy

```bash
npm run build
npx wrangler deploy
```

This deploys the SPA and its `/api/indices` edge proxy together and prints the
`*.workers.dev` URL.
Set `VITE_CONVEX_URL` at build time (or in `.env.production`) so production
builds point at your Convex deployment.

## Porting this to your own data

This dashboard expects three read-only Convex queries with the shapes
defined in `../convex/postEarningsSummaries.js`:

- `postEarningsSummaries:listRecent({ limit, sector? })` — most recent
  results across all tickers, optionally filtered by sector.
- `postEarningsSummaries:listCompanies()` — latest identity row per ticker.
- `postEarningsSummaries:listByTicker({ ticker, limit })` — a single
  ticker's history.
- `earningsCalendar:reportingProgress({ start, end, tickers? })` — scheduled
  versus archived reports for the reporting-progress tiles.

Point `VITE_CONVEX_URL` at any Convex deployment exposing the same query
names/shapes and the dashboard works unmodified.
