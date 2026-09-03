import correctionCatalog from "./verified-post-corrections.json" with { type: "json" };

const AGENTMAIL_API = "https://api.agentmail.to/v0";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function bulletHtml(items, limit = 6) {
  return `<ul style="margin:0;padding-left:22px;">${items.slice(0, limit).map((item) => `<li style="padding:0 0 7px 0;">${escapeHtml(item.text)}</li>`).join("")}</ul>`;
}

function renderHtml(item) {
  const figures = (item.keyFigures || []).slice(0, 6).map((figure) => (
    `<td width="33%" valign="top" style="padding:10px 12px;border:1px solid #e3e5ea;">` +
    `<div style="font-size:9pt;color:#4b4f58;text-transform:uppercase;">${escapeHtml(figure.label)}</div>` +
    `<div style="padding-top:3px;font-weight:700;white-space:nowrap;">${escapeHtml(figure.value)}</div></td>`
  ));
  const figureRows = [];
  for (let index = 0; index < figures.length; index += 3) {
    const row = figures.slice(index, index + 3);
    while (row.length < 3) row.push('<td width="33%"></td>');
    figureRows.push(`<tr>${row.join("")}</tr>`);
  }
  const sections = item.sections.slice(0, 3).map((section) => (
    `<div style="margin-top:18px;padding:14px 0 6px;border-top:1px solid #e3e5ea;font-weight:700;">${escapeHtml(section.heading)}</div>` +
    bulletHtml(section.bullets, 4)
  )).join("");
  const links = Object.entries(item.officialLinks).map(([key, url]) => {
    const label = key === "investor_deck" ? "Investor Deck" : "Press Release";
    return `<a href="${escapeHtml(url)}" style="color:#3454f4;text-decoration:none;font-weight:700;">${label}</a>`;
  }).join(" &nbsp;&middot;&nbsp; ");

  return `<!doctype html><html><body style="margin:0;background:#fff;font-family:Aptos,Calibri,'Segoe UI',Arial,sans-serif;font-size:11pt;color:#0b0d12;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:20px 16px;">
  <table role="presentation" width="640" cellpadding="0" cellspacing="0" style="width:640px;max-width:640px;">
  <tr><td style="padding-bottom:8px;font-weight:700;">${escapeHtml(item.ticker)} ${escapeHtml(item.quarter)} Correction: Post-Earnings Summary</td></tr>
  <tr><td style="padding-bottom:10px;color:#4b4f58;">Reported ${escapeHtml(item.reportDate)} -- ${escapeHtml(item.reportTime)}</td></tr>
  <tr><td style="padding-bottom:10px;">${links}</td></tr>
  <tr><td style="padding-bottom:14px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">${figureRows.join("")}</table></td></tr>
  <tr><td style="padding-bottom:7px;font-weight:700;">${escapeHtml(item.reactionLine)}</td></tr>
  <tr><td style="padding-bottom:4px;line-height:16pt;">${escapeHtml(item.intro)}</td></tr>
  <tr><td><div style="margin-top:18px;padding:14px 0 6px;border-top:1px solid #e3e5ea;font-weight:700;">Financial highlights</div>${bulletHtml(item.financialHighlights)}</td></tr>
  <tr><td>${sections}</td></tr>
  <tr><td><div style="margin-top:18px;padding:14px 0 6px;border-top:1px solid #e3e5ea;font-weight:700;">Key highlights</div>${bulletHtml(item.keyMetrics.map((text) => ({ text })))}</td></tr>
  <tr><td style="padding-top:18px;margin-top:12px;border-top:1px solid #e3e5ea;color:#4b4f58;">Figures are reported by the company unless noted otherwise. This is not investment advice.</td></tr>
  </table></td></tr></table></body></html>`;
}

function renderText(item) {
  const lines = [
    `# ${item.ticker} ${item.quarter} Correction: Post-Earnings Summary`,
    "",
    `Reported ${item.reportDate} -- ${item.reportTime}`,
    "",
    `**${item.reactionLine}**`,
    "",
    item.intro,
    "",
    "## Financial highlights",
    ...item.financialHighlights.map((row) => `- ${row.text}`),
  ];
  for (const section of item.sections.slice(0, 3)) {
    lines.push("", `## ${section.heading}`, ...section.bullets.slice(0, 4).map((row) => `- ${row.text}`));
  }
  lines.push("", "## Key highlights", ...item.keyMetrics.slice(0, 6).map((metric) => `- ${metric}`));
  lines.push("", `Press release: ${item.officialLinks.press_release}`);
  if (item.officialLinks.investor_deck) lines.push(`Investor deck: ${item.officialLinks.investor_deck}`);
  lines.push("", "Figures are reported by the company unless noted otherwise. This is not investment advice.", "");
  return lines.join("\n");
}

async function agentMailRequest(env, method, path, body) {
  const response = await fetch(`${AGENTMAIL_API}${path}`, {
    method,
    headers: {
      authorization: `Bearer ${env.AGENTMAIL_API_KEY}`,
      accept: "application/json",
      ...(body ? { "content-type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`AgentMail ${method} ${path} failed: ${response.status} ${JSON.stringify(payload).slice(0, 500)}`);
  return payload;
}

async function resolveInbox(env) {
  if (!env.AGENTMAIL_API_KEY) throw new Error("AGENTMAIL_API_KEY is not configured");
  const payload = await agentMailRequest(env, "GET", "/inboxes");
  const inboxes = payload.inboxes || [];
  const configured = String(env.AGENTMAIL_INBOX_ID || "").trim();
  const inbox = configured
    ? inboxes.find((candidate) => candidate.inbox_id === configured || candidate.email === configured)
    : (inboxes.length === 1 ? inboxes[0] : null);
  if (!inbox) throw new Error(`Configured AgentMail inbox was not found (${configured || "no unique inbox"})`);
  return String(inbox.inbox_id || inbox.email);
}

async function archiveSummary(env, item) {
  if (!env.CONVEX_URL || !env.EARNINGS_ARCHIVE_TOKEN) throw new Error("Convex archive credentials are not configured");
  const financials = item.financials || {};
  const args = {
    adminToken: env.EARNINGS_ARCHIVE_TOKEN,
    ticker: item.ticker,
    company: item.company,
    quarter: item.quarter,
    reportDate: item.reportDate,
    reportTime: item.reportTime,
    reactionPct: item.reactionPct,
    reactionLine: item.reactionLine,
    keyMetrics: item.keyMetrics,
    revenueActualUsd: financials.revenue_actual_usd,
    revenueConsensusUsd: financials.revenue_consensus_usd,
    revenueYoyPct: financials.revenue_yoy_pct,
    netIncomeActualUsd: financials.net_income_actual_usd,
    epsActual: financials.eps_actual,
    epsConsensus: financials.eps_consensus,
    epsSurprisePct: financials.eps_surprise_pct,
    capexActualUsd: financials.capex_actual_usd,
  };
  const response = await fetch(`${String(env.CONVEX_URL).replace(/\/$/u, "")}/api/mutation`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ path: "postEarningsSummaries:upsertSummary", args }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.status === "error") throw new Error(`Convex correction archive failed: ${response.status} ${JSON.stringify(payload).slice(0, 500)}`);
  return payload;
}

async function sendCorrection(env, inboxId, item) {
  const recipients = String(env.DEAL_ALERT_EMAIL_TO || "").split(",").map((value) => value.trim()).filter(Boolean);
  if (!recipients.length) throw new Error("DEAL_ALERT_EMAIL_TO is not configured");
  const body = {
    to: recipients,
    subject: `${item.company} (${item.ticker}) ${item.quarter} | Correction: Post-Earnings Summary`,
    text: renderText(item),
    html: renderHtml(item),
  };
  if (env.EARNINGS_EMAIL_REPLY_TO) body.reply_to = env.EARNINGS_EMAIL_REPLY_TO;
  return agentMailRequest(env, "POST", `/inboxes/${encodeURIComponent(inboxId)}/messages/send`, body);
}

export function hasVerifiedCorrection(correctionId) {
  const batch = correctionCatalog[correctionId];
  return Boolean(batch && Object.keys(batch).length);
}

export async function deliverVerifiedCorrection(env, step, correctionId, watchlist = "", sendEmails = true) {
  const batch = correctionCatalog[correctionId];
  if (!batch) throw new Error(`Unknown verified correction: ${correctionId}`);
  const requested = new Set(String(watchlist || "").split(",").map((value) => value.trim()).filter(Boolean));
  const items = Object.values(batch).filter((item) => !requested.size || requested.has(item.ticker));
  if (!items.length) throw new Error("Verified correction watchlist matched no companies");

  const inboxId = sendEmails
    ? await step.do("resolve correction inbox", async () => resolveInbox(env))
    : "";
  const delivered = [];
  for (const item of items) {
    await step.do(`archive corrected ${item.ticker}`, async () => archiveSummary(env, item));
    if (!sendEmails) continue;
    const result = await step.do(
      `send corrected ${item.ticker}`,
      { retries: { limit: 0, delay: "1 second", backoff: "constant" }, timeout: "2 minutes" },
      async () => sendCorrection(env, inboxId, item),
    );
    delivered.push({ ticker: item.ticker, messageId: result.message_id || result.id || "" });
  }
  return { status: "succeeded", correctionId, archived: items.map((item) => item.ticker), delivered };
}

export const __test = { renderHtml, renderText };
