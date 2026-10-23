const COVERAGE_JOBS = new Set(["pre-earnings", "pre-catchup", "post-bmo", "post-amc"]);

export function coverageFailureMessage(payload, job) {
  if (payload.draftOnly || !COVERAGE_JOBS.has(payload.jobName) || job?.status !== "failed") return null;
  const text = String(job.stdoutTail || "");
  const tickers = /failed tickers:\s*([A-Z0-9,.-]+)/u.exec(text)?.[1] || payload.watchlist || "See the earnings coverage run";
  const stage = payload.jobName.startsWith("pre") ? "Pre-earnings" : "Post-earnings";
  return { subject: `${stage} coverage needs attention`, text: `${stage} coverage did not finish successfully.\n\nAffected coverage: ${tickers}\nRun: ${payload.runId}\n\nA completed archive is not proof of email delivery. Missing reports require recovery; no empty earnings digest is being sent.` };
}

export async function alertCoverageFailure(env, payload, job) {
  const message = coverageFailureMessage(payload, job);
  if (!message) return { status: "skipped" };
  const to = String(env.DEAL_ALERT_EMAIL_TO || "").split(",").map(value => value.trim()).filter(Boolean);
  if (!to.length || !env.AGENTMAIL_API_KEY || !env.AGENTMAIL_INBOX_ID) throw new Error("Coverage failure alert credentials are not configured");
  const response = await fetch(`https://api.agentmail.to/v0/inboxes/${encodeURIComponent(env.AGENTMAIL_INBOX_ID)}/messages/send`, {
    method: "POST", headers: { authorization: `Bearer ${env.AGENTMAIL_API_KEY}`, "content-type": "application/json" },
    body: JSON.stringify({ to, ...message }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(`Coverage failure alert delivery failed (${response.status})`);
  return { status: "sent", messageId: result.message_id || "" };
}
