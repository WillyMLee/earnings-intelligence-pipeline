import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

function requireArchiveToken(adminToken) {
  const expected = process.env.EARNINGS_ARCHIVE_WRITE_TOKEN;
  if (!expected) throw new Error("EARNINGS_ARCHIVE_WRITE_TOKEN is not configured in Convex.");
  if (adminToken !== expected) throw new Error("Invalid archive write token.");
}

export const upsertArtifact = mutation({
  args: { adminToken: v.string(), kind: v.string(), ticker: v.string(), reportDate: v.string(), url: v.optional(v.string()), title: v.optional(v.string()), text: v.string(), provider: v.optional(v.string()) },
  handler: async (ctx, args) => {
    requireArchiveToken(args.adminToken);
    const now = new Date().toISOString();
    const { adminToken: _adminToken, ...artifact } = args;
    const existing = await ctx.db.query("researchArtifacts").withIndex("by_kind_ticker_date", (q) => q.eq("kind", artifact.kind).eq("ticker", artifact.ticker).eq("reportDate", artifact.reportDate)).unique();
    if (existing) { await ctx.db.patch(existing._id, { ...artifact, updatedAt: now }); return { id: existing._id, updated: true }; }
    const id = await ctx.db.insert("researchArtifacts", { ...artifact, createdAt: now, updatedAt: now });
    return { id, updated: false };
  },
});

export const getArtifact = query({
  args: { kind: v.string(), ticker: v.string(), reportDate: v.string() },
  handler: async (ctx, args) => await ctx.db.query("researchArtifacts").withIndex("by_kind_ticker_date", (q) => q.eq("kind", args.kind).eq("ticker", args.ticker).eq("reportDate", args.reportDate)).unique(),
});
