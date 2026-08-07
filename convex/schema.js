import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

const optionalString = v.optional(v.union(v.string(), v.null()));

export default defineSchema({
  preEarningsSnapshots: defineTable({
    ticker: v.string(), reportDate: v.string(),
    revenueConsensusUsd: v.optional(v.union(v.float64(), v.null())),
    revenueConsensusYoyPct: v.optional(v.union(v.float64(), v.null())),
    fyRevenueConsensusUsd: v.optional(v.union(v.float64(), v.null())),
    fyRevenueConsensusYoyPct: v.optional(v.union(v.float64(), v.null())),
    epsConsensus: v.optional(v.union(v.float64(), v.null())),
    createdAt: v.string(), updatedAt: v.string(),
  }).index("by_ticker_report_date", ["ticker", "reportDate"]),

  researchArtifacts: defineTable({
    kind: v.string(), ticker: v.string(), reportDate: v.string(), url: v.optional(v.string()), title: v.optional(v.string()), text: v.string(), provider: v.optional(v.string()), createdAt: v.string(), updatedAt: v.string(),
  }).index("by_kind_ticker_date", ["kind", "ticker", "reportDate"]),

  earningsCalendarEvents: defineTable({
    ticker: v.string(),
    company: v.string(),
    reportDate: v.string(),
    reportTime: v.string(),
    sector: v.optional(v.string()),
    epsEstimate: v.optional(v.union(v.float64(), v.null())),
    revenueEstimateUsd: v.optional(v.union(v.float64(), v.null())),
    updatedAt: v.string(),
  })
    .index("by_report_date", ["reportDate"])
    .index("by_ticker_report_date", ["ticker", "reportDate"]),

  earningsBriefs: defineTable({
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
    createdAt: v.string(),
    updatedAt: v.string(),
  })
    .index("by_run_key", ["runKey"])
    .index("by_mode", ["mode"])
    .index("by_period_start", ["periodStart"])
    .index("by_generated_at", ["generatedAt"]),

  postEarningsSummaries: defineTable({
    ticker: v.string(),
    company: v.string(),
    quarter: v.string(),
    reportDate: v.string(),
    reportTime: v.string(),
    reactionPct: v.optional(v.union(v.float64(), v.null())),
    reactionLine: optionalString,
    keyMetrics: v.array(v.string()),
    // Sector/portfolio tagging and structured comparable financials, added
    // for historical tracking -- all optional so existing rows (written
    // before this field set existed) remain valid without a migration.
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
    createdAt: v.string(),
    updatedAt: v.string(),
  })
    .index("by_ticker_report_date", ["ticker", "reportDate"])
    .index("by_report_date", ["reportDate"])
    .index("by_ticker", ["ticker"]),
});
