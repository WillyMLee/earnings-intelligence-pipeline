import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { JOB_NAMES, jobsForEasternSlot, scheduledRunId } from "../../cloudflare/schedule.mjs";

test("summer schedule maps New York business slots to isolated jobs", () => {
  assert.deepEqual(jobsForEasternSlot("2026-08-20T12:00:00Z"), ["input-prefetch"]);
  assert.deepEqual(jobsForEasternSlot("2026-08-20T13:30:00Z"), ["daily-radar", "post-bmo"]);
  assert.deepEqual(jobsForEasternSlot("2026-08-20T14:00:00Z"), ["post-digest-bmo"]);
  assert.deepEqual(jobsForEasternSlot("2026-08-20T21:00:00Z"), ["pre-earnings"]);
  assert.deepEqual(jobsForEasternSlot("2026-08-20T22:00:00Z"), ["post-amc"]);
  assert.deepEqual(jobsForEasternSlot("2026-08-20T23:30:00Z"), ["post-digest-amc"]);
  assert.deepEqual(jobsForEasternSlot("2026-08-22T06:30:00Z"), ["transcript-cache"]);
  assert.deepEqual(jobsForEasternSlot("2026-08-23T21:00:00Z"), ["weekly-radar"]);
});

test("winter schedule stays on the same New York clock slots", () => {
  assert.deepEqual(jobsForEasternSlot("2026-01-08T13:00:00Z"), ["input-prefetch"]);
  assert.deepEqual(jobsForEasternSlot("2026-01-08T14:30:00Z"), ["daily-radar", "post-bmo"]);
  assert.deepEqual(jobsForEasternSlot("2026-01-08T22:00:00Z"), ["pre-earnings"]);
});

test("schedule covers every production job and deterministic IDs fit Workflow limits", () => {
  const observed = new Set([
    ...jobsForEasternSlot("2026-08-20T12:00:00Z"),
    ...jobsForEasternSlot("2026-08-20T13:30:00Z"),
    ...jobsForEasternSlot("2026-08-20T14:00:00Z"),
    ...jobsForEasternSlot("2026-08-20T21:00:00Z"),
    ...jobsForEasternSlot("2026-08-20T22:00:00Z"),
    ...jobsForEasternSlot("2026-08-20T23:30:00Z"),
    ...jobsForEasternSlot("2026-08-22T06:30:00Z"),
    ...jobsForEasternSlot("2026-08-23T21:00:00Z"),
  ]);
  assert.deepEqual([...observed].sort(), [...JOB_NAMES].sort());
  const runId = scheduledRunId("post-digest-amc", Date.parse("2026-08-20T23:30:00Z"));
  assert.ok(runId.length <= 100);
  assert.equal(runId, scheduledRunId("post-digest-amc", Date.parse("2026-08-20T23:30:00Z")));
});

test("Wrangler config is production, scheduled, and has no Render dependency", async () => {
  const configText = await readFile(new URL("../../wrangler.earnings.jsonc", import.meta.url), "utf8");
  const config = JSON.parse(configText);
  const worker = await readFile(new URL("../../cloudflare/worker.mjs", import.meta.url), "utf8");
  assert.deepEqual(config.triggers.crons, ["*/30 * * * *"]);
  assert.equal(config.vars.ENVIRONMENT, "production");
  assert.equal(config.vars.DRY_RUN, "false");
  assert.equal(config.vars.NATIVE_SENDS_ENABLED, "true");
  assert.equal(config.workflows[0].class_name, "EarningsJobWorkflow");
  assert.equal(config.containers[0].class_name, "EarningsContainer");
  assert.match(worker, /createBatch/u);
  assert.doesNotMatch(`${configText}\n${worker}`, /onrender\.com|RENDER_FALLBACK|MIGRATION_ADAPTER_URL/iu);
});

