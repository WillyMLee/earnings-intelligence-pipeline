import assert from "node:assert/strict";
import test from "node:test";

import worker, { companyIdentity } from "../../dashboard/worker/index.js";

const expectedDomains = {
  ADSK: "autodesk.com",
  BBY: "bestbuy.com",
  DG: "dollargeneral.com",
  DLTR: "dollartree.com",
  VEEV: "veeva.com",
  OKTA: "okta.com",
  NVDA: "nvidia.com",
};

test("resolves canonical domains for the earnings names missing logos", () => {
  for (const [ticker, domain] of Object.entries(expectedDomains)) {
    const identity = companyIdentity(ticker.toLowerCase());
    assert.equal(identity?.ticker, ticker);
    assert.equal(identity?.domain, domain);
    assert.match(identity?.logoUrl ?? "", new RegExp(encodeURIComponent(domain)));
  }
});

test("company identity endpoint normalizes, deduplicates, and omits unknown tickers", async () => {
  const response = await worker.fetch(
    new Request("https://example.com/api/company-identity?tickers=adsk,ADSK,BBY,unknown"),
    { ASSETS: { fetch: () => assert.fail("static assets should not handle the identity endpoint") } },
  );
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "public, max-age=3600");
  const payload = await response.json();
  assert.deepEqual(payload.companies.map(({ ticker, domain }) => ({ ticker, domain })), [
    { ticker: "ADSK", domain: "autodesk.com" },
    { ticker: "BBY", domain: "bestbuy.com" },
  ]);
});
