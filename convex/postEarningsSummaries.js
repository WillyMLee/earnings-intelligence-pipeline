import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

const optionalString = v.optional(v.union(v.string(), v.null()));

function requireArchiveToken(adminToken) {
  const expected = process.env.EARNINGS_ARCHIVE_WRITE_TOKEN;
  if (!expected) {
    throw new Error("EARNINGS_ARCHIVE_WRITE_TOKEN is not configured in Convex.");
  }
  if (adminToken !== expected) {
    throw new Error("Invalid archive write token.");
  }
}

export const upsertSummary = mutation({
  args: {
    adminToken: v.string(),
    ticker: v.string(),
    company: v.string(),
    quarter: v.string(),
    reportDate: v.string(),
    reportTime: v.string(),
    reactionPct: v.optional(v.union(v.float64(), v.null())),
    reactionLine: optionalString,
    keyMetrics: v.array(v.string()),
    sector: v.optional(v.string()),
    isPortco: v.optional(v.boolean()),
    revenueActualUsd: v.optional(v.union(v.float64(), v.null())),
    revenueConsensusUsd: v.optional(v.union(v.float64(), v.null())),
    revenueYoyPct: v.optional(v.union(v.float64(), v.null())),
    netIncomeActualUsd: v.optional(v.union(v.float64(), v.null())),
    epsActual: v.optional(v.union(v.float64(), v.null())),
    epsConsensus: v.optional(v.union(v.float64(), v.null())),
    epsSurprisePct: v.optional(v.union(v.float64(), v.null())),
    capexActualUsd: v.optional(v.union(v.float64(), v.null())),
    capexGuidancePriorUsd: v.optional(v.union(v.float64(), v.null())),
    capexGuidanceUpdatedUsd: v.optional(v.union(v.float64(), v.null())),
  },
  handler: async (ctx, args) => {
    requireArchiveToken(args.adminToken);
    const now = new Date().toISOString();
    const { adminToken: _adminToken, ...summary } = args;

    const existing = await ctx.db
      .query("postEarningsSummaries")
      .withIndex("by_ticker_report_date", (q) =>
        q.eq("ticker", summary.ticker).eq("reportDate", summary.reportDate)
      )
      .unique();

    if (existing) {
      await ctx.db.patch(existing._id, { ...summary, updatedAt: now });
      return { id: existing._id, updated: true };
    }

    const id = await ctx.db.insert("postEarningsSummaries", {
      ...summary,
      createdAt: now,
      updatedAt: now,
    });
    return { id, updated: false };
  },
});

export const getSummary = query({
  args: { ticker: v.string(), reportDate: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("postEarningsSummaries")
      .withIndex("by_ticker_report_date", (q) =>
        q.eq("ticker", args.ticker).eq("reportDate", args.reportDate)
      )
      .unique();
  },
});

export const listByReportDate = query({
  args: { reportDate: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("postEarningsSummaries")
      .withIndex("by_report_date", (q) => q.eq("reportDate", args.reportDate))
      .collect();
  },
});

export const removeSummary = mutation({
  args: { adminToken: v.string(), ticker: v.string(), reportDate: v.string() },
  handler: async (ctx, args) => {
    requireArchiveToken(args.adminToken);
    const existing = await ctx.db
      .query("postEarningsSummaries")
      .withIndex("by_ticker_report_date", (q) =>
        q.eq("ticker", args.ticker).eq("reportDate", args.reportDate)
      )
      .unique();
    if (!existing) {
      return { deleted: false };
    }
    await ctx.db.delete(existing._id);
    return { deleted: true };
  },
});

export const listByTicker = query({
  args: { ticker: v.string(), limit: v.optional(v.float64()) },
  handler: async (ctx, args) => {
    const limit = Math.max(1, Math.min(args.limit ?? 20, 100));
    const rows = await ctx.db
      .query("postEarningsSummaries")
      .withIndex("by_ticker_report_date", (q) => q.eq("ticker", args.ticker))
      .order("desc")
      .take(limit);
    return rows;
  },
});

export const listRecent = query({
  args: { limit: v.optional(v.float64()), sector: v.optional(v.string()) },
  handler: async (ctx, args) => {
    const limit = Math.max(1, Math.min(args.limit ?? 50, 200));
    if (args.sector) {
      return await ctx.db
        .query("postEarningsSummaries")
        .withIndex("by_sector_report_date", (q) => q.eq("sector", args.sector))
        .order("desc")
        .take(limit);
    }
    return await ctx.db
      .query("postEarningsSummaries")
      .withIndex("by_report_date")
      .order("desc")
      .take(limit);
  },
});

export const listSectors = query({
  args: {},
  handler: async (ctx) => {
    const rows = await ctx.db.query("postEarningsSummaries").collect();
    return Array.from(new Set(rows.map((row) => row.sector).filter(Boolean))).sort();
  },
});

export const listCompanies = query({
  args: {},
  handler: async (ctx) => {
    const rows = await ctx.db.query("postEarningsSummaries").collect();
    const byTicker = new Map();
    for (const row of rows) {
      const existing = byTicker.get(row.ticker);
      if (!existing || String(row.reportDate) > String(existing.reportDate)) {
        byTicker.set(row.ticker, {
          ticker: row.ticker,
          company: row.company,
          sector: row.sector ?? null,
          reportDate: row.reportDate,
        });
      }
    }
    return Array.from(byTicker.values()).sort((a, b) => a.company.localeCompare(b.company));
  },
});
