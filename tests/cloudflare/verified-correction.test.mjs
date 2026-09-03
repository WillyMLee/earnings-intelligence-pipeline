import assert from "node:assert/strict";
import test from "node:test";

import catalog from "../../cloudflare/verified-post-corrections.json" with { type: "json" };
import { __test, hasVerifiedCorrection } from "../../cloudflare/verified-correction-delivery.mjs";

test("verified correction catalog contains substantive issuer-sourced briefs", () => {
  assert.equal(hasVerifiedCorrection("2026-09-02"), true);
  assert.equal(hasVerifiedCorrection("2026-09-01"), false);
  const batch = catalog["2026-09-02"];
  assert.deepEqual(Object.keys(batch), ["AVGO", "HPE", "SNOW"]);
  for (const item of Object.values(batch)) {
    assert.ok(item.financialHighlights.length >= 3);
    assert.ok(item.sections.some((section) => section.bullets.length));
    assert.ok(item.keyMetrics.length >= 3);
    assert.match(item.officialLinks.press_release, /^https:\/\//u);
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
  assert.match(html, /product revenue was \$1\.492 billion/u);
  assert.match(html, /Guidance and operating leverage/u);
  assert.match(text, /RPO: \$9\.00B/u);
  assert.match(text, /Correction: Post-Earnings Summary/u);
});
