import assert from "node:assert/strict";
import test from "node:test";

import { proxyConvexQuery } from "../../dashboard/worker/index.js";

test("the earnings edge proxy shares cached Convex query responses", async () => {
  const stored = new Map();
  const originalCaches = globalThis.caches;
  const originalFetch = globalThis.fetch;
  let upstreamCalls = 0;
  const pending = [];

  globalThis.caches = {
    default: {
      async match(request) {
        return stored.get(request.url)?.clone();
      },
      async put(request, response) {
        stored.set(request.url, response.clone());
      },
    },
  };
  globalThis.fetch = async () => {
    upstreamCalls += 1;
    return new Response(JSON.stringify({ status: "success", value: [{ ticker: "MSFT" }] }), {
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    const body = JSON.stringify({
      path: "postEarningsSummaries:listRecent",
      args: { limit: 200 },
      format: "json",
    });
    const request = () => new Request("https://earnings.example/api/convex-query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    const ctx = { waitUntil(promise) { pending.push(promise); } };

    const first = await proxyConvexQuery(request(), { CONVEX_URL: "https://convex.example" }, ctx);
    assert.equal(first.headers.get("X-Earnings-Cache"), "MISS");
    await Promise.all(pending);

    const second = await proxyConvexQuery(request(), { CONVEX_URL: "https://convex.example" }, ctx);
    assert.equal(second.headers.get("X-Earnings-Cache"), "HIT");
    assert.equal(upstreamCalls, 1);
    assert.deepEqual((await second.json()).value, [{ ticker: "MSFT" }]);
  } finally {
    globalThis.caches = originalCaches;
    globalThis.fetch = originalFetch;
  }
});
