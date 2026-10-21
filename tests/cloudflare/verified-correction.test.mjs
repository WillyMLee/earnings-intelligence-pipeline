import assert from "node:assert/strict";
import test from "node:test";

import catalog from "../../cloudflare/verified-post-corrections.json" with { type: "json" };
import { __test, hasVerifiedCorrection, deliverVerifiedCorrection } from "../../cloudflare/verified-correction-delivery.mjs";

test("recovery archives both missed reports and quarantines late consensus without sending", async () => {
  const original = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, init) => {
    requests.push({ url, body: JSON.parse(init.body) });
    const body = JSON.parse(init.body);
    const value = body.path === "preEarningsSnapshots:getSnapshot" && body.args.ticker === "NFLX"
      ? { capturedAt: "2026-10-21T10:00:00", revenueConsensusUsd: 13_400_000_000 } : null;
    return Response.json({ status: "success", value });
  };
  try {
    const step = { do: async (...args) => args.at(-1)() };
    const result = await deliverVerifiedCorrection({ CONVEX_URL: "https://example.convex.cloud", EARNINGS_ARCHIVE_TOKEN: "test" }, step, "2026-10-20", "NFLX,SPCX", false);
    assert.deepEqual(result.archived, ["NFLX", "SPCX"]);
    assert.deepEqual(result.delivered, []);
    const quarantine = requests.find((request) => request.body.path === "preEarningsSnapshots:upsertSnapshot");
    assert.equal(quarantine.body.args.revenueConsensusUsd, null);
    assert.equal(quarantine.body.args.capturedAt, "2026-10-21T10:00:00");
    assert.ok(requests.every((request) => !request.url.includes("agentmail")));
  } finally { globalThis.fetch = original; }
});

test("verified correction catalog contains substantive issuer-sourced briefs", () => {
  assert.equal(hasVerifiedCorrection("2026-09-02"), true);
  assert.equal(hasVerifiedCorrection("2026-09-10"), true);
  assert.equal(hasVerifiedCorrection("2026-09-01"), false);
  assert.deepEqual(Object.keys(catalog["2026-09-02"]), ["AVGO", "HPE", "SNOW"]);
  assert.deepEqual(Object.keys(catalog["2026-09-10"]), ["ORCL", "ADBE"]);
  for (const batch of Object.values(catalog)) {
    for (const item of Object.values(batch)) {
      assert.ok(item.financialHighlights.length >= 3);
      assert.ok(item.sections.some((section) => section.bullets.length));
      assert.ok(item.keyMetrics.length >= 3);
      assert.match(item.officialLinks.press_release, /^https:\/\//u);
    }
  }
});

test("correction renderer includes analysis rather than an empty shell", () => {
  const item = catalog["2026-09-02"].SNOW;
  const html = __test.renderHtml(item);
  const text = __test.renderText(item);
  assert.match(html, /Financial highlights/u);
  assert.match(html, /Earnings intelligence/u);
  assert.match(html, /Executive read/u);
  assert.match(html, /Positive reaction/u);
  assert.match(html, /metric-cell/u);
  assert.match(html, /Estimate scoreboard/u);
  assert.match(html, /class="comparison-values"/u);
  assert.match(html, /table-layout:fixed/u);
  assert.match(html, /bgcolor="#e3f5ee"/u);
  assert.match(html, /<wbr>/u);
  assert.match(html, /FactSet consensus/u);
  assert.match(html, /Valuation reference/u);
  assert.match(html, /17\.8x close/u);
  assert.match(html, /product revenue was \$1\.492 billion/u);
  assert.match(html, /Guidance and operating leverage/u);
  assert.match(text, /RPO: \$9\.00B/u);
  assert.match(text, /Correction: Post-Earnings Summary/u);
  assert.match(text, /EV \/ CY revenue: 17\.8x close/u);
});
