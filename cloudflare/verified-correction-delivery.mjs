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
  const rows = items.slice(0, limit).map((item) => (
    `<tr><td valign="top" style="width:12px;padding:3px 9px 7px 0;color:#3454f4;font-size:10px;line-height:21px;">&#9632;</td>` +
    `<td valign="top" style="padding:0 0 9px;color:#0b0d12;font-size:13px;line-height:21px;">${escapeHtml(item.text)}</td></tr>`
  )).join("");
  return `<table role="presentation" width="100%" cellpadding="0" cellspacing="0">${rows}</table>`;
}

function sectionHeading(title) {
  return `<div style="padding:0 0 11px;margin-bottom:14px;border-bottom:1px solid #e3e5ea;"><span style="font-size:11px;line-height:16px;color:#63697a;text-transform:uppercase;font-weight:800;letter-spacing:.8px;">${escapeHtml(title)}</span></div>`;
}

function sectionCard(title, body, accent = "#3454f4") {
  return `<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;border:1px solid #e3e5ea;border-radius:14px;background:#fff;"><tr><td style="padding:20px 22px 11px;border-left:4px solid ${accent};border-radius:14px;">${sectionHeading(title)}${body}</td></tr></table>`;
}

function estimateScoreboardHtml(items = []) {
  if (!items.length) return "";
  const rows = items.slice(0, 5).map((item) => {
    const varianceLower = String(item.variance || "").trim().toLowerCase();
    const varianceColor = varianceLower.startsWith("-") || varianceLower.includes("miss") || varianceLower.includes("below")
      ? "#c23b4b"
      : varianceLower.includes("inline") || varianceLower.includes("in line") || varianceLower.includes("flat")
        ? "#a56b00"
        : "#12805c";
    return (
    `<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;background:#f7f8fa;border:1px solid #e3e5ea;border-radius:11px;">` +
    `<tr><td colspan="3" style="padding:13px 14px 8px;font-size:13px;line-height:18px;color:#0b0d12;font-weight:800;">${escapeHtml(item.metric)} <span style="font-size:10px;color:#63697a;font-weight:600;">&nbsp;&middot;&nbsp; ${escapeHtml(item.period)} &nbsp;&middot;&nbsp; ${escapeHtml(item.estimate_as_of)}</span></td></tr>` +
    `<tr><td class="comparison-cell" width="34%" valign="top" style="padding:5px 14px 13px;"><div style="font-size:9px;color:#63697a;font-weight:800;text-transform:uppercase;letter-spacing:.5px;">Reported / guide</div><div style="padding-top:4px;font-size:16px;line-height:21px;font-weight:800;">${escapeHtml(item.reported)}</div></td>` +
    `<td class="comparison-cell" width="33%" valign="top" style="padding:5px 14px 13px;border-left:1px solid #e3e5ea;"><div style="font-size:9px;color:#63697a;font-weight:800;text-transform:uppercase;letter-spacing:.5px;">Estimate</div><div style="padding-top:4px;font-size:16px;line-height:21px;font-weight:800;">${escapeHtml(item.estimate)}</div></td>` +
    `<td class="comparison-cell" width="33%" valign="top" style="padding:5px 14px 13px;border-left:1px solid #e3e5ea;"><div style="font-size:9px;color:#63697a;font-weight:800;text-transform:uppercase;letter-spacing:.5px;">Variance</div><div style="padding-top:4px;font-size:16px;line-height:21px;color:${varianceColor};font-weight:800;">${escapeHtml(item.variance)}</div></td></tr>` +
    `<tr><td colspan="3" style="padding:0 14px 12px;font-size:10px;line-height:15px;color:#63697a;">Source: <a href="${escapeHtml(item.source_url)}" style="color:#3454f4;text-decoration:none;font-weight:750;">${escapeHtml(item.estimate_source)}</a></td></tr></table>`
    );
  }).join("");
  return sectionCard("Estimate scoreboard", rows);
}

function valuationReferenceHtml(item = {}) {
  if (!item.ev_cy_revenue) return "";
  const fields = [
    ["Enterprise value", item.enterprise_value],
    ["CY revenue estimate", item.cy_revenue],
    ["EV / CY revenue", item.ev_cy_revenue],
  ];
  const cells = fields.map(([label, value]) => (
    `<td class="valuation-cell" width="33.33%" valign="top" style="padding:0 6px 10px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#e8ecfe;border-radius:10px;"><tr><td style="height:64px;padding:13px 12px;"><div style="font-size:9px;line-height:13px;color:#3454f4;font-weight:800;text-transform:uppercase;letter-spacing:.5px;">${label}</div><div style="padding-top:5px;font-size:16px;line-height:21px;font-weight:800;">${escapeHtml(value)}</div></td></tr></table></td>`
  )).join("");
  const body = `<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 -6px;"><tr>${cells}</tr></table><div style="padding:2px 0 3px;font-size:11px;line-height:17px;color:#63697a;"><strong style="color:#0b0d12;">Basis:</strong> ${escapeHtml(item.basis)}</div><div style="padding:3px 0 4px;font-size:10px;line-height:15px;color:#63697a;">As of ${escapeHtml(item.as_of)} &nbsp;&middot;&nbsp; <a href="${escapeHtml(item.source_url)}" style="color:#3454f4;text-decoration:none;font-weight:750;">${escapeHtml(item.source)}</a></div>`;
  return sectionCard("Valuation reference", body, "#a56b00");
}

function renderHtml(item) {
  const figures = (item.keyFigures || []).slice(0, 6).map((figure) => (
    `<td class="metric-cell" width="33.33%" valign="top" style="padding:0 6px 12px;">` +
    `<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f7f8fa;border:1px solid #e3e5ea;border-radius:12px;"><tr><td valign="top" style="height:76px;padding:15px 14px 13px;">` +
    `<div style="font-size:10px;line-height:14px;color:#63697a;text-transform:uppercase;font-weight:800;letter-spacing:.5px;">${escapeHtml(figure.label)}</div>` +
    `<div style="padding-top:7px;font-size:18px;line-height:23px;font-weight:750;color:#0b0d12;letter-spacing:-.2px;">${escapeHtml(figure.value)}</div></td></tr></table></td>`
  ));
  const figureRows = [];
  for (let index = 0; index < figures.length; index += 3) {
    const row = figures.slice(index, index + 3);
    while (row.length < 3) row.push('<td width="33%"></td>');
    figureRows.push(`<tr>${row.join("")}</tr>`);
  }
  const sections = item.sections.slice(0, 3).map((section) => (
    `<div style="height:14px;line-height:14px;">&nbsp;</div>${sectionCard(section.heading, bulletHtml(section.bullets, 4))}`
  )).join("");
  const links = Object.entries(item.officialLinks).map(([key, url]) => {
    const label = key === "investor_deck" ? "Investor Deck" : "Press Release";
    return `<a href="${escapeHtml(url)}" style="display:inline-block;margin:0 7px 7px 0;padding:8px 12px;border:1px solid #e3e5ea;border-radius:8px;background:#fff;color:#3454f4;text-decoration:none;font-size:12px;line-height:16px;font-weight:750;">${label} &nbsp;&#8594;</a>`;
  }).join("");
  const reaction = Number(item.reactionPct);
  const reactionStyle = reaction >= 2
    ? { label: "Positive reaction", color: "#12805c", soft: "#e3f5ee" }
    : reaction <= -2
      ? { label: "Negative reaction", color: "#c23b4b", soft: "#fbe9ec" }
      : { label: "Muted reaction", color: "#a56b00", soft: "#faf1de" };
  const reactionHtml = `<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:${reactionStyle.soft};border-radius:12px;"><tr><td style="padding:15px 18px;border-left:4px solid ${reactionStyle.color};border-radius:12px;"><div style="font-size:10px;line-height:14px;color:${reactionStyle.color};font-weight:800;text-transform:uppercase;letter-spacing:.6px;">${reactionStyle.label}</div><div style="padding-top:4px;font-size:14px;line-height:21px;color:#0b0d12;font-weight:750;">${escapeHtml(item.reactionLine)}</div></td></tr></table>`;
  const metricsHtml = figures.length
    ? `${sectionHeading("Key figures")}<table class="metric-grid" role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 -6px;">${figureRows.join("")}</table>`
    : "";
  const estimateHtml = estimateScoreboardHtml(item.estimateComparisons || []);
  const valuationHtml = valuationReferenceHtml(item.valuationReference || {});

  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
  @media only screen and (max-width:620px){.email-shell{width:100%!important}.outer-pad{padding:0!important}.header-pad{padding:24px 20px 22px!important}.body-pad{padding:22px 16px 24px!important}.metric-cell,.valuation-cell{display:block!important;width:100%!important;box-sizing:border-box!important;border-left:0!important}.comparison-cell{padding-left:8px!important;padding-right:8px!important}.metric-grid{margin:0!important}.email-title{font-size:25px!important;line-height:30px!important}}
  </style></head><body style="margin:0;padding:0;background:#f5f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:13px;color:#0b0d12;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"><tr><td class="outer-pad" align="center" style="padding:24px 12px 32px;">
  <table class="email-shell" role="presentation" align="center" width="680" cellpadding="0" cellspacing="0" style="width:680px;max-width:680px;margin:0 auto;">
  <tr><td class="header-pad" style="background:#0b0d12;border-radius:16px 16px 0 0;padding:28px 32px 25px;"><div style="font-size:10px;line-height:16px;color:#9aa3b2;text-transform:uppercase;font-weight:800;letter-spacing:1px;">Earnings intelligence &nbsp;&middot;&nbsp; Post-earnings <span style="display:inline-block;margin-left:8px;padding:3px 8px;border-radius:999px;background:#3454f4;color:#fff;font-size:9px;line-height:13px;font-weight:800;letter-spacing:.6px;vertical-align:middle;">CORRECTION</span></div><div class="email-title" style="padding-top:9px;font-size:30px;line-height:36px;color:#fff;font-weight:800;letter-spacing:-.45px;">${escapeHtml(item.company)}</div><div style="padding-top:8px;font-size:13px;line-height:20px;color:#9aa3b2;"><span style="color:#fff;font-weight:750;">${escapeHtml(item.ticker)}</span> &nbsp;&middot;&nbsp; ${escapeHtml(item.quarter)} &nbsp;&middot;&nbsp; Reported ${escapeHtml(item.reportDate)} -- ${escapeHtml(item.reportTime)}</div></td></tr>
  <tr><td class="body-pad" style="background:#fff;padding:24px 28px 30px;">${reactionHtml}<div style="height:14px;line-height:14px;">&nbsp;</div><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#e8ecfe;border-radius:12px;"><tr><td style="padding:17px 19px;"><div style="font-size:10px;line-height:14px;color:#3454f4;font-weight:800;text-transform:uppercase;letter-spacing:.7px;">Executive read</div><div style="padding-top:6px;font-size:14px;line-height:22px;color:#0b0d12;">${escapeHtml(item.intro)}</div></td></tr></table><div style="padding-top:14px;">${links}</div><div style="height:20px;line-height:20px;">&nbsp;</div>${metricsHtml}${estimateHtml ? `<div style="height:12px;line-height:12px;">&nbsp;</div>${estimateHtml}` : ""}${valuationHtml ? `<div style="height:14px;line-height:14px;">&nbsp;</div>${valuationHtml}` : ""}<div style="height:12px;line-height:12px;">&nbsp;</div>${sectionCard("Financial highlights", bulletHtml(item.financialHighlights))}${sections}<div style="height:14px;line-height:14px;">&nbsp;</div>${sectionCard("Key highlights", bulletHtml(item.keyMetrics.map((text) => ({ text }))))}</td></tr>
  <tr><td style="background:#f7f8fa;border-radius:0 0 16px 16px;padding:17px 28px 19px;border-top:1px solid #e3e5ea;"><div style="font-size:11px;line-height:18px;color:#63697a;">Earnings Intelligence &middot; Figures are reported by the company unless noted otherwise. This is not investment advice.</div></td></tr>
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
  if ((item.estimateComparisons || []).length) {
    lines.push("", "## Estimate scoreboard");
    for (const comparison of item.estimateComparisons.slice(0, 5)) {
      lines.push(`- ${comparison.metric}: ${comparison.reported} vs. ${comparison.estimate}; ${comparison.variance} (${comparison.estimate_source}, ${comparison.estimate_as_of})`);
    }
  }
  if (item.valuationReference?.ev_cy_revenue) {
    lines.push(
      "", "## Valuation reference",
      `- Enterprise value: ${item.valuationReference.enterprise_value}`,
      `- CY revenue estimate: ${item.valuationReference.cy_revenue}`,
      `- EV / CY revenue: ${item.valuationReference.ev_cy_revenue}`,
      `- Basis: ${item.valuationReference.basis}`,
    );
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
