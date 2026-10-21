import assert from "node:assert/strict";
import test from "node:test";
import { coverageFailureMessage } from "../../cloudflare/coverage-failure-alert.mjs";

test("only actual coverage failures generate actionable alerts", () => {
  const payload = { jobName: "pre-earnings", runId: "test" };
  assert.equal(coverageFailureMessage(payload, { status: "succeeded", stdoutTail: "No reporters" }), null);
  assert.equal(coverageFailureMessage({ ...payload, draftOnly: true }, { status: "failed" }), null);
  const result = coverageFailureMessage(payload, { status: "failed", stdoutTail: "Completed 2/3 reporter(s); failed tickers: META" });
  assert.match(result.text, /META/u);
  assert.match(result.subject, /needs attention/u);
});
