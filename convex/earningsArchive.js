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

function briefArgs() {
  return {
    adminToken: v.string(),
    runKey: v.string(),
    mode: v.string(),
    generatedAt: v.string(),
    periodStart: v.string(),
    periodEnd: v.string(),
    title: v.string(),
    subject: optionalString,
    deliveryStatus: v.string(),
    recipients: v.array(v.string()),
    eventCount: v.float64(),
    marketSignalCount: v.float64(),
    coverageThemes: v.array(v.string()),
    coverageUniverse: v.array(v.string()),
    summaryMarkdown: v.string(),
    emailHtml: v.string(),
    manifest: v.any(),
    events: v.any(),
    notableEvents: v.any(),
    research: v.any(),
  };
}

function listProjection(row) {
  return {
    _id: row._id,
    runKey: row.runKey,
    mode: row.mode,
    generatedAt: row.generatedAt,
    periodStart: row.periodStart,
    periodEnd: row.periodEnd,
    title: row.title,
    subject: row.subject,
    deliveryStatus: row.deliveryStatus,
    recipients: row.recipients,
    eventCount: row.eventCount,
    marketSignalCount: row.marketSignalCount,
    coverageThemes: row.coverageThemes,
    coverageUniverse: row.coverageUniverse,
    events: row.events,
    notableEvents: row.notableEvents,
    research: row.research,
    updatedAt: row.updatedAt,
  };
}

export const upsertBrief = mutation({
  args: briefArgs(),
  handler: async (ctx, args) => {
    requireArchiveToken(args.adminToken);
    const now = new Date().toISOString();
    const { adminToken: _adminToken, ...brief } = args;
    const existing = await ctx.db
      .query("earningsBriefs")
      .withIndex("by_run_key", (q) => q.eq("runKey", brief.runKey))
      .unique();

    if (existing) {
      await ctx.db.patch(existing._id, {
        ...brief,
        updatedAt: now,
      });
      return { id: existing._id, runKey: brief.runKey, updated: true };
    }

    const id = await ctx.db.insert("earningsBriefs", {
      ...brief,
      createdAt: now,
      updatedAt: now,
    });
    return { id, runKey: brief.runKey, updated: false };
  },
});

export const listBriefs = query({
  args: {
    mode: v.optional(v.string()),
    limit: v.optional(v.float64()),
  },
  handler: async (ctx, args) => {
    const limit = Math.max(1, Math.min(args.limit ?? 50, 200));
    let rows = await ctx.db.query("earningsBriefs").withIndex("by_generated_at").collect();
    if (args.mode) {
      rows = rows.filter((row) => row.mode === args.mode);
    }
    rows.sort((left, right) => String(right.generatedAt).localeCompare(String(left.generatedAt)));
    return rows.slice(0, limit).map(listProjection);
  },
});

export const getBrief = query({
  args: { runKey: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("earningsBriefs")
      .withIndex("by_run_key", (q) => q.eq("runKey", args.runKey))
      .unique();
  },
});
