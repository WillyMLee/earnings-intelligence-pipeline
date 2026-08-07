import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

function requireArchiveToken(adminToken) {
  const expected = process.env.EARNINGS_ARCHIVE_WRITE_TOKEN;
  if (!expected) throw new Error("EARNINGS_ARCHIVE_WRITE_TOKEN is not configured in Convex.");
  if (adminToken !== expected) throw new Error("Invalid archive write token.");
}

export const upsertSnapshot = mutation({
  args: {
    adminToken: v.string(), ticker: v.string(), reportDate: v.string(),
    revenueConsensusUsd: v.optional(v.union(v.float64(), v.null())),
    revenueConsensusYoyPct: v.optional(v.union(v.float64(), v.null())),
    fyRevenueConsensusUsd: v.optional(v.union(v.float64(), v.null())),
    fyRevenueConsensusYoyPct: v.optional(v.union(v.float64(), v.null())),
    epsConsensus: v.optional(v.union(v.float64(), v.null())),
    consensusSource: v.optional(v.string()),
    capturedAt: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    requireArchiveToken(args.adminToken);
    const now = new Date().toISOString();
    const { adminToken: _adminToken, ...raw } = args;
    const snapshot = Object.fromEntries(Object.entries(raw).filter(([, value]) => value !== undefined));
    const existing = await ctx.db.query("preEarningsSnapshots").withIndex("by_ticker_report_date", (q) => q.eq("ticker", args.ticker).eq("reportDate", args.reportDate)).unique();
    if (existing) { await ctx.db.patch(existing._id, { ...snapshot, updatedAt: now }); return { id: existing._id, updated: true }; }
    const id = await ctx.db.insert("preEarningsSnapshots", { ticker: args.ticker, reportDate: args.reportDate, ...snapshot, createdAt: now, updatedAt: now });
    return { id, updated: false };
  },
});

export const getSnapshot = query({
  args: { ticker: v.string(), reportDate: v.string() },
  handler: async (ctx, args) => await ctx.db.query("preEarningsSnapshots").withIndex("by_ticker_report_date", (q) => q.eq("ticker", args.ticker).eq("reportDate", args.reportDate)).unique(),
});
