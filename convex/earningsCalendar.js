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

function eventMatches(row, event) {
  return row.ticker === event.ticker
    && row.company === event.company
    && row.reportDate === event.reportDate
    && row.reportTime === event.reportTime
    && row.sector === event.sector
    && row.epsEstimate === event.epsEstimate
    && row.revenueEstimateUsd === event.revenueEstimateUsd;
}

export const replaceWindow = mutation({
  args: { adminToken: v.string(), windowStart: v.string(), windowEnd: v.string(), contentHash: v.optional(v.string()), events: v.array(calendarEvent) },
  handler: async (ctx, args) => {
    requireArchiveToken(args.adminToken);
    const syncState = await ctx.db
      .query("earningsCalendarSyncState")
      .withIndex("by_key", (q) => q.eq("key", "primary"))
      .unique();
    if (args.contentHash && syncState?.contentHash === args.contentHash) {
      return { unchanged: true, removed: 0, inserted: 0, updated: 0, retained: args.events.length };
    }

    const existing = await ctx.db
      .query("earningsCalendarEvents")
      .withIndex("by_report_date", (q) => q.gte("reportDate", args.windowStart).lte("reportDate", args.windowEnd))
      .collect();
    const existingByKey = new Map();
    for (const row of existing) {
      const key = `${row.ticker}:${row.reportDate}`;
      const duplicates = existingByKey.get(key) ?? [];
      duplicates.push(row);
      existingByKey.set(key, duplicates);
    }

    const now = new Date().toISOString();
    let inserted = 0;
    let updated = 0;
    let retained = 0;
    for (const event of args.events) {
      const key = `${event.ticker}:${event.reportDate}`;
      const matches = existingByKey.get(key) ?? [];
      const current = matches.shift();
      if (matches.length) existingByKey.set(key, matches);
      else existingByKey.delete(key);
      if (!current) {
        await ctx.db.insert("earningsCalendarEvents", { ...event, updatedAt: now });
        inserted += 1;
      } else if (eventMatches(current, event)) {
        retained += 1;
      } else {
        await ctx.db.patch(current._id, { ...event, updatedAt: now });
        updated += 1;
      }
    }

    let removed = 0;
    for (const duplicates of existingByKey.values()) {
      for (const row of duplicates) {
        await ctx.db.delete(row._id);
        removed += 1;
      }
    }

    if (args.contentHash) {
      const nextState = {
        key: "primary",
        contentHash: args.contentHash,
        windowStart: args.windowStart,
        windowEnd: args.windowEnd,
        eventCount: args.events.length,
        updatedAt: now,
      };
      if (syncState) await ctx.db.patch(syncState._id, nextState);
      else await ctx.db.insert("earningsCalendarSyncState", nextState);
    }
    return { unchanged: false, removed, inserted, updated, retained };
  },
});

export const listWindow = query({
  args: { start: v.string(), end: v.string(), tickers: v.optional(v.array(v.string())) },
  handler: async (ctx, args) => {
    const allowed = args.tickers ? new Set(args.tickers.map((ticker) => ticker.toUpperCase())) : null;
    return (await ctx.db
      .query("earningsCalendarEvents")
      .withIndex("by_report_date", (q) => q.gte("reportDate", args.start).lte("reportDate", args.end))
      .collect())
      .filter((row) => !allowed || allowed.has(row.ticker))
      .sort((left, right) => left.reportDate.localeCompare(right.reportDate) || left.reportTime.localeCompare(right.reportTime));
  },
});

export const reportingProgress = query({
  args: { start: v.string(), end: v.string(), tickers: v.optional(v.array(v.string())) },
  handler: async (ctx, args) => {
    const allowed = args.tickers ? new Set(args.tickers.map((ticker) => ticker.toUpperCase())) : null;
    const calendarRows = (await ctx.db
      .query("earningsCalendarEvents")
      .withIndex("by_report_date", (q) => q.gte("reportDate", args.start).lte("reportDate", args.end))
      .collect()).filter((row) => !allowed || allowed.has(row.ticker));
    const summaries = await ctx.db
      .query("postEarningsSummaries")
      .withIndex("by_report_date", (q) => q.gte("reportDate", args.start).lte("reportDate", args.end))
      .collect();
    const reportedKeys = new Set(summaries.map((row) => `${row.ticker}:${row.reportDate}`));
    const reported = calendarRows.filter((row) => reportedKeys.has(`${row.ticker}:${row.reportDate}`));
    return { start: args.start, end: args.end, total: calendarRows.length, reported: reported.length, percent: calendarRows.length ? Math.round((reported.length / calendarRows.length) * 100) : 0, scheduled: calendarRows };
  },
});
