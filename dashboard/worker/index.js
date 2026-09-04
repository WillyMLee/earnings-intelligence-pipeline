/**
 * Worker entrypoint sitting in front of the static dashboard build.
 * Handles /api/* itself (currently just /api/indices, a same-origin proxy
 * for Yahoo Finance's public intraday chart endpoint -- a browser can't
 * call it directly due to CORS, but a Worker fetching server-to-server
 * has no such restriction); everything else falls through to the static
 * assets binding, same as before this file existed.
 */

import companyIdentities from "../src/data/companyIdentities.json" with { type: "json" };

const INDEX_SYMBOLS = [
  { symbol: "^GSPC", name: "S&P 500 Index" },
  { symbol: "^IXIC", name: "NASDAQ" },
  { symbol: "^DJI", name: "Dow Jones" },
];

const CONVEX_QUERY_PATHS = new Set([
  "earningsCalendar:listWindow",
  "earningsCalendar:reportingProgress",
  "postEarningsSummaries:listByTicker",
  "postEarningsSummaries:listRecent",
]);
const CONVEX_CACHE_SECONDS = 300;

function normalizeTicker(value) {
  return String(value ?? "").trim().toUpperCase().replaceAll(".", "-");
}

export function companyIdentity(ticker) {
  const normalizedTicker = normalizeTicker(ticker);
  const identity = companyIdentities[normalizedTicker];
  if (!identity) return null;
  return {
    ticker: normalizedTicker,
    name: identity.name,
    domain: identity.domain,
    logoUrl: `https://www.google.com/s2/favicons?domain_url=${encodeURIComponent(`https://${identity.domain}`)}&sz=128`,
  };
}

async function fetchIndex({ symbol, name }) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=5m&range=1d`;
  const res = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 (compatible; earnings-dashboard/1.0)" },
  });
  if (!res.ok) throw new Error(`Yahoo chart fetch failed for ${symbol}: HTTP ${res.status}`);
  const payload = await res.json();
  const result = payload?.chart?.result?.[0];
  if (!result) throw new Error(`No chart result for ${symbol}`);

  const meta = result.meta ?? {};
  const timestamps = result.timestamp ?? [];
  const closes = result.indicators?.quote?.[0]?.close ?? [];
  const previousClose = meta.chartPreviousClose ?? meta.previousClose ?? null;
  const price = meta.regularMarketPrice ?? null;

  const series = [];
  for (let i = 0; i < timestamps.length; i++) {
    const close = closes[i];
    if (close === null || close === undefined) continue;
    series.push({ t: timestamps[i] * 1000, price: close });
  }

  const change = price !== null && previousClose ? price - previousClose : null;
  const changePct = price !== null && previousClose ? (change / previousClose) * 100 : null;

  return { symbol, name, price, previousClose, change, changePct, series };
}

function hexDigest(buffer) {
  return [...new Uint8Array(buffer)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function proxyConvexQuery(request, env, ctx) {
  const contentLength = Number.parseInt(request.headers.get("content-length") ?? "0", 10);
  if (contentLength > 32_768) {
    return new Response(JSON.stringify({ error: "Query request is too large." }), {
      status: 413,
      headers: { "Content-Type": "application/json" },
    });
  }

  const body = await request.text();
  let query;
  try {
    query = JSON.parse(body);
  } catch {
    return new Response(JSON.stringify({ error: "Invalid JSON request." }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }
  if (!CONVEX_QUERY_PATHS.has(query?.path) || !query?.args || query?.format !== "json") {
    return new Response(JSON.stringify({ error: "Query is not allowed." }), {
      status: 403,
      headers: { "Content-Type": "application/json" },
    });
  }
  if (!env.CONVEX_URL) {
    return new Response(JSON.stringify({ error: "Convex is not configured." }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });
  }

  const digest = hexDigest(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(body)));
  const cacheKey = new Request(`${new URL(request.url).origin}/__cache/convex/${digest}`);
  const cache = caches.default;
  const cached = await cache.match(cacheKey);
  if (cached) {
    const response = new Response(cached.body, cached);
    response.headers.set("X-Earnings-Cache", "HIT");
    return response;
  }

  const upstream = await fetch(`${env.CONVEX_URL.replace(/\/$/, "")}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  const response = new Response(upstream.body, upstream);
  response.headers.set("Cache-Control", `public, max-age=${CONVEX_CACHE_SECONDS}`);
  response.headers.set("X-Earnings-Cache", "MISS");
  if (upstream.ok) {
    ctx.waitUntil(cache.put(cacheKey, response.clone()));
  }
  return response;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/api/convex-query" && request.method === "POST") {
      return proxyConvexQuery(request, env, ctx);
    }

    if (url.pathname === "/api/indices") {
      try {
        const indices = await Promise.all(INDEX_SYMBOLS.map(fetchIndex));
        return new Response(JSON.stringify({ indices, fetchedAt: Date.now() }), {
          headers: {
            "Content-Type": "application/json",
            // Short cache -- the frontend polls this on an interval, no
            // need for every browser tab to hit Yahoo independently within
            // the same few seconds.
            "Cache-Control": "public, max-age=15",
          },
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: String(err) }), {
          status: 502,
          headers: { "Content-Type": "application/json" },
        });
      }
    }

    if (url.pathname === "/api/company-identity") {
      const requested = (url.searchParams.get("tickers") ?? "")
        .split(",")
        .map(normalizeTicker)
        .filter(Boolean);
      const tickers = requested.length ? [...new Set(requested)].slice(0, 100) : Object.keys(companyIdentities);
      const companies = tickers.map(companyIdentity).filter(Boolean);
      return new Response(JSON.stringify({ companies }), {
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "public, max-age=3600",
          "Access-Control-Allow-Origin": "*",
        },
      });
    }

    return env.ASSETS.fetch(request);
  },
};
