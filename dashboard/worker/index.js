/**
 * Worker entrypoint sitting in front of the static dashboard build.
 * Handles /api/* itself (currently just /api/indices, a same-origin proxy
 * for Yahoo Finance's public intraday chart endpoint -- a browser can't
 * call it directly due to CORS, but a Worker fetching server-to-server
 * has no such restriction); everything else falls through to the static
 * assets binding, same as before this file existed.
 */

const INDEX_SYMBOLS = [
  { symbol: "^GSPC", name: "S&P 500 Index" },
  { symbol: "^IXIC", name: "NASDAQ" },
  { symbol: "^DJI", name: "Dow Jones" },
];

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

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

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

    return env.ASSETS.fetch(request);
  },
};
