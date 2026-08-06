// Color is reserved for genuine beat/miss/reaction sentiment throughout
// this dashboard -- everything else (sector tags, labels) stays neutral
// gray, matching the guardrail already applied in the pipeline's own email
// templates: color that doesn't mean anything just adds noise.
type Tone = "positive" | "negative" | "neutral";

const TONE_CLASSES: Record<Tone, string> = {
  positive: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400",
  negative: "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400",
  neutral: "bg-black/[0.04] text-[#5b5f6b] dark:bg-white/[0.06] dark:text-[#9a9ea8]",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}

export function ReactionBadge({ pct }: { pct: number | null }) {
  if (pct === null || !Number.isFinite(pct)) return <Badge tone="neutral">No reaction data</Badge>;
  const positive = pct >= 0;
  return (
    <Badge tone={positive ? "positive" : "negative"}>
      <span aria-hidden>{positive ? "▲" : "▼"}</span>
      {Math.abs(pct).toFixed(1)}%
    </Badge>
  );
}
