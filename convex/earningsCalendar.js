import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

function requireArchiveToken(adminToken) {
  const expected = process.env.EARNINGS_ARCHIVE_WRITE_TOKEN;
  if (!expected) throw new Error("EARNINGS_ARCHIVE_WRITE_TOKEN is not configured in Convex.");
  if (adminToken !== expected) throw new Error("Invalid archive write token.");
}

const calendarEvent = v.object({
  ticker: v.string(), company: v.string(), reportDate: v.string(), reportTime: v.string(),
  sector: v.optional(v.string()),
  epsEstimate: v.optional(v.union(v.float64(), v.null())),
  revenueEstimateUsd: v.optional(v.union(v.float64(), v.null())),
});

export const replaceWindow = mutation({
  args: { adminToken: v.string(), windowStart: v.string(), windowEnd: v.string(), events: v.array(calendarEvent) },
  handler: async (ctx, args) => {
    requireArchiveToken(args.adminToken);
    const existing = await ctx.db.query("earningsCalendarEvents").collect();
    const inWindow = existing.filter((row) => row.reportDate >= args.windowStart && row.reportDate <= args.windowEnd);
    for (const row of inWindow) await ctx.db.delete(row._id);
    const now = new Date().toISOString();
    for (const event of args.events) await ctx.db.insert("earningsCalendarEvents", { ...event, updatedAt: now });
    return { removed: inWindow.length, inserted: args.events.length };
  },
});

export const listWindow = query({
  args: { start: v.string(), end: v.string(), tickers: v.optional(v.array(v.string())) },
  handler: async (ctx, args) => {
    const allowed = args.tickers ? new Set(args.tickers.map((ticker) => ticker.toUpperCase())) : null;
    return (await ctx.db.query("earningsCalendarEvents").collect())
      .filter((row) => row.reportDate >= args.start && row.reportDate <= args.end && (!allowed || allowed.has(row.ticker)))
      .sort((left, right) => left.reportDate.localeCompare(right.reportDate) || left.reportTime.localeCompare(right.reportTime));
  },
});

export const reportingProgress = query({
  args: { start: v.string(), end: v.string(), tickers: v.optional(v.array(v.string())) },
  handler: async (ctx, args) => {
    const allowed = args.tickers ? new Set(args.tickers.map((ticker) => ticker.toUpperCase())) : null;
    const calendarRows = (await ctx.db.query("earningsCalendarEvents").collect()).filter(
      (row) => row.reportDate >= args.start && row.reportDate <= args.end && (!allowed || allowed.has(row.ticker))
    );
    const summaries = await ctx.db.query("postEarningsSummaries").collect();
    const reportedKeys = new Set(summaries.map((row) => `${row.ticker}:${row.reportDate}`));
    const reported = calendarRows.filter((row) => reportedKeys.has(`${row.ticker}:${row.reportDate}`));
    return { start: args.start, end: args.end, total: calendarRows.length, reported: reported.length, percent: calendarRows.length ? Math.round((reported.length / calendarRows.length) * 100) : 0, scheduled: calendarRows };
  },
});
