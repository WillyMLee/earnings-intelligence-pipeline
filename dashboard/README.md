# Earnings Intelligence Dashboard

A small, public, read-only dashboard for browsing the earnings results the
rest of this repo's pipeline archives to Convex — grouped by sector, with
each report's actual-vs-consensus figures and a short "what mattered"
summary.

Built as a static site (Vite + React + Tailwind) backed by read-only Convex
queries — no write/admin token is ever used or shipped to the client. In
production, the Cloudflare Worker holds identical query responses at the edge
for five minutes so visitors share one Convex read. The browser also deduplicates
overlapping page requests during navigation.

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

This deploys the SPA, its `/api/indices` market proxy, and the cached
`/api/convex-query` read proxy together and prints the
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
