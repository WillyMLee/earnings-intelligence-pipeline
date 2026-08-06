# Earnings Intelligence Dashboard

A small, public, read-only dashboard for browsing the earnings results the
rest of this repo's pipeline archives to Convex — grouped by sector, with
each report's actual-vs-consensus figures and a short "what mattered"
summary.

Built as a static site (Vite + React + Tailwind) that talks to Convex's
HTTP query API directly — no server of its own, and no write/admin token
is ever used or shipped to the client. Deployed to Cloudflare Pages.

## Run locally

```bash
npm install
cp .env.example .env.local   # point VITE_CONVEX_URL at your deployment
npm run dev
```

## Deploy

```bash
npm run build
npx wrangler pages deploy dist --project-name=earnings-intelligence
```

First deploy creates the Pages project and prints a `*.pages.dev` URL.
Set `VITE_CONVEX_URL` as a build-time environment variable in the Cloudflare
Pages project settings (or bake it into `.env.production` before building)
so production builds point at your Convex deployment.

## Porting this to your own data

This dashboard expects three read-only Convex queries with the shapes
defined in `../convex/postEarningsSummaries.js`:

- `postEarningsSummaries:listRecent({ limit, sector? })` — most recent
  results across all tickers, optionally filtered by sector.
- `postEarningsSummaries:listSectors()` — distinct sector values, for the
  filter pills.
- `postEarningsSummaries:listByTicker({ ticker, limit })` — a single
  ticker's history (not yet used in the UI, wired for a future per-ticker
  trend view).

Point `VITE_CONVEX_URL` at any Convex deployment exposing the same query
names/shapes and the dashboard works unmodified.
