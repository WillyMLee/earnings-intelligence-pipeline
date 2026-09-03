import { Container } from "@cloudflare/containers";
import { WorkflowEntrypoint } from "cloudflare:workers";
import { NonRetryableError } from "cloudflare:workflows";

import { JOB_NAMES, jobsForEasternSlot, scheduledRunId } from "./schedule.mjs";
import { deliverVerifiedCorrection, hasVerifiedCorrection } from "./verified-correction-delivery.mjs";

const JOB_NAME_SET = new Set(JOB_NAMES);
const VERIFIED_CORRECTION_JOB = "verified-post-correction";
const POLL_LIMIT = 240;
const POLL_DELAY = "30 seconds";

export class EarningsContainer extends Container {
  defaultPort = 8080;
  sleepAfter = "2m";

  async onActivityExpired() {
    let health = null;
    try {
      const response = await this.containerFetch("http://container/health");
      health = await response.json().catch(() => null);
    } catch (error) {
      console.error(JSON.stringify({ event: "idle_health_failed", message: error instanceof Error ? error.message : String(error) }));
    }
    if (health?.currentJob) {
      this.renewActivityTimeout();
      return;
    }
    console.log(JSON.stringify({ event: "idle_container_destroyed" }));
    await this.destroy();
  }
}

function json(body, status = 200) {
  return Response.json(body, { status });
}

function containerEnvironment(env) {
  const values = {
    AGENTMAIL_API_KEY: env.AGENTMAIL_API_KEY,
    AGENTMAIL_INBOX_ID: env.AGENTMAIL_INBOX_ID,
    DEAL_ALERT_EMAIL_TO: env.DEAL_ALERT_EMAIL_TO,
    WEEKLY_BRIEFING_EMAIL_TO: env.WEEKLY_BRIEFING_EMAIL_TO || env.DEAL_ALERT_EMAIL_TO,
    EARNINGS_ARCHIVE_TOKEN: env.EARNINGS_ARCHIVE_TOKEN,
    EXA_API_KEY: env.EXA_API_KEY,
    LLMLAYER_API_KEY: env.LLMLAYER_API_KEY,
    OPENAI_API_KEY: env.OPENAI_API_KEY,
    TAVILY_API_KEY: env.TAVILY_API_KEY,
    TINYFISH_API_KEY: env.TINYFISH_API_KEY,
    ALPHA_VANTAGE_API_KEY: env.ALPHA_VANTAGE_API_KEY,
    CONVEX_URL: env.CONVEX_URL,
    EMAIL_PROVIDER: env.EMAIL_PROVIDER,
    TINYFISH_LANGUAGE: env.TINYFISH_LANGUAGE,
    TINYFISH_LOCATION: env.TINYFISH_LOCATION,
    OPENAI_WEB_SEARCH_MODEL: env.OPENAI_WEB_SEARCH_MODEL,
    EARNINGS_TIME_ZONE: env.EARNINGS_TIME_ZONE,
    ENVIRONMENT: env.ENVIRONMENT,
    NATIVE_SENDS_ENABLED: env.NATIVE_SENDS_ENABLED,
    RELEASE_TAG: env.RELEASE_TAG,
  };
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value !== undefined && value !== null && value !== ""));
}

function containerForJob(env, jobName) {
  const release = String(env.RELEASE_TAG || "default").replaceAll(/[^A-Za-z0-9_-]/gu, "-").slice(0, 48);
  return env.EARNINGS_CONTAINER.getByName(`earnings-${release}-${jobName}`);
}

async function startContainer(env, jobName) {
  const container = containerForJob(env, jobName);
  await container.startAndWaitForPorts({
    ports: [8080],
    startOptions: { envVars: containerEnvironment(env) },
  });
  return container;
}

async function containerRequest(env, jobName, path, init = {}) {
  const container = await startContainer(env, jobName);
  const headers = new Headers(init.headers);
  headers.set("x-automation-token", env.EARNINGS_ARCHIVE_TOKEN);
  return container.fetch(`http://container${path}`, { ...init, headers });
}

function validateJobPayload(value) {
  if (!value || typeof value !== "object") throw new Error("JSON object required");
  const jobName = String(value.jobName || "");
  if (!JOB_NAME_SET.has(jobName) && jobName !== VERIFIED_CORRECTION_JOB) throw new Error(`Unknown job: ${jobName}`);
  const runId = String(value.runId || "");
  if (!runId || runId.length > 100) throw new Error("runId is required and must be at most 100 characters");
  const forDate = value.forDate ? String(value.forDate) : "";
  if (forDate && !/^\d{4}-\d{2}-\d{2}$/u.test(forDate)) throw new Error("forDate must use YYYY-MM-DD");
  const watchlist = value.watchlist ? String(value.watchlist).toUpperCase() : "";
  if (watchlist && !/^[A-Z0-9.,-]+$/u.test(watchlist)) throw new Error("watchlist contains invalid characters");
  const correctionId = value.correctionId ? String(value.correctionId) : "";
  if (jobName === VERIFIED_CORRECTION_JOB && !hasVerifiedCorrection(correctionId)) {
    throw new Error(`Unknown verified correction: ${correctionId || "missing"}`);
  }
  return {
    jobName,
    runId,
    forDate,
    watchlist,
    draftOnly: value.draftOnly === true,
    correction: value.correction === true,
    correctionId,
  };
}

async function dispatchJob(env, payload) {
  const response = await containerRequest(env, payload.jobName, "/internal/run", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(`Container rejected ${payload.jobName}: ${response.status} ${body.reason || "unknown"}`);
  return body;
}

async function jobStatus(env, jobName, runId) {
  const response = await containerRequest(env, jobName, `/internal/job?runId=${encodeURIComponent(runId)}`);
  const body = await response.json();
  if (!response.ok) throw new Error(`Container status failed: ${response.status}`);
  return body.job || null;
}

export class EarningsJobWorkflow extends WorkflowEntrypoint {
  async run(event, step) {
    let payload;
    try {
      payload = validateJobPayload(event.payload);
    } catch (error) {
      throw new NonRetryableError(error instanceof Error ? error.message : "Invalid workflow payload");
    }

    if (payload.jobName === VERIFIED_CORRECTION_JOB) {
      return deliverVerifiedCorrection(this.env, step, payload.correctionId, payload.watchlist);
    }

    await step.do(
      `dispatch ${payload.jobName}`,
      { retries: { limit: 5, delay: "15 seconds", backoff: "exponential" }, timeout: "10 minutes" },
      async () => dispatchJob(this.env, payload),
    );

    for (let attempt = 1; attempt <= POLL_LIMIT; attempt += 1) {
      await step.sleep(`wait for ${payload.jobName} ${attempt}`, POLL_DELAY);
      const job = await step.do(
        `check ${payload.jobName} ${attempt}`,
        { retries: { limit: 3, delay: "10 seconds", backoff: "linear" }, timeout: "5 minutes" },
        async () => jobStatus(this.env, payload.jobName, payload.runId),
      );
      if (job?.status === "succeeded") return job;
      if (job?.status === "failed") {
        const stderr = String(job.stderrTail || "no stderr").slice(-4_000);
        throw new NonRetryableError(`${payload.jobName} failed with exit code ${job.exitCode ?? "unknown"}: ${stderr}`);
      }
    }
    throw new Error(`${payload.jobName} did not finish within ${POLL_LIMIT * 30} seconds`);
  }
}

async function authorized(request, env) {
  const supplied = request.headers.get("authorization")?.replace(/^Bearer\s+/iu, "") || "";
  const encoder = new TextEncoder();
  const [left, right] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(supplied)),
    crypto.subtle.digest("SHA-256", encoder.encode(env.EARNINGS_ARCHIVE_TOKEN || "")),
  ]);
  return Boolean(env.EARNINGS_ARCHIVE_TOKEN) && crypto.subtle.timingSafeEqual(left, right);
}

async function createJobs(env, payloads) {
  return env.EARNINGS_JOB_WORKFLOW.createBatch(payloads.map((payload) => ({
    id: payload.runId,
    params: payload,
  })));
}

async function handleApi(request, env) {
  const url = new URL(request.url);
  if (url.pathname === "/health") {
    return json({
      ok: true,
      environment: env.ENVIRONMENT,
      dryRun: env.DRY_RUN === "true",
      nativeSendsEnabled: env.NATIVE_SENDS_ENABLED === "true",
      timeZone: env.EARNINGS_TIME_ZONE,
      scheduleVersion: env.SCHEDULE_VERSION,
      releaseTag: env.RELEASE_TAG,
      scheduler: "*/30 * * * *",
      jobs: JOB_NAMES,
    });
  }

  if (!url.pathname.startsWith("/api/jobs/")) return json({ ok: false, reason: "not_found" }, 404);
  if (!(await authorized(request, env))) return json({ ok: false, reason: "unauthorized" }, 401);

  if (url.pathname === "/api/jobs/run" && request.method === "POST") {
    try {
      const raw = await request.json();
      const payload = validateJobPayload({ ...raw, runId: raw.runId || `manual-${raw.jobName}-${crypto.randomUUID()}` });
      const instances = await createJobs(env, [payload]);
      return json({ ok: true, accepted: instances.length === 1, duplicate: instances.length === 0, runId: payload.runId }, 202);
    } catch (error) {
      return json({ ok: false, reason: "invalid_request", message: error instanceof Error ? error.message : String(error) }, 400);
    }
  }

  if (url.pathname === "/api/jobs/status" && request.method === "GET") {
    const runId = url.searchParams.get("runId") || "";
    try {
      const instance = await env.EARNINGS_JOB_WORKFLOW.get(runId);
      return json({ ok: true, runId, details: await instance.status() });
    } catch (error) {
      return json({ ok: false, reason: "not_found", message: error instanceof Error ? error.message : String(error) }, 404);
    }
  }
  return json({ ok: false, reason: "not_found" }, 404);
}

export default {
  async fetch(request, env) {
    try {
      return await handleApi(request, env);
    } catch (error) {
      console.error(JSON.stringify({ event: "request_failed", message: error instanceof Error ? error.message : String(error) }));
      return json({ ok: false, reason: "internal_error" }, 500);
    }
  },

  async scheduled(controller, env, ctx) {
    const jobs = jobsForEasternSlot(controller.scheduledTime);
    if (!jobs.length) {
      console.log(JSON.stringify({ event: "cron_idle", scheduledTime: controller.scheduledTime }));
      return;
    }
    const scheduledAt = new Date(controller.scheduledTime).toISOString();
    const payloads = jobs.map((jobName) => ({
      jobName,
      runId: scheduledRunId(jobName, controller.scheduledTime),
      forDate: "",
      watchlist: "",
      draftOnly: false,
      correction: false,
    }));
    ctx.waitUntil(createJobs(env, payloads).then((instances) => {
      console.log(JSON.stringify({ event: "cron_dispatched", scheduledAt, jobs, created: instances.map((instance) => instance.id) }));
    }));
  },
};
