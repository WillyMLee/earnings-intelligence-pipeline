/**
 * A numbered, connected step list -- rounded number badge, connecting line,
 * label in its own rounded row. Directly mirrors the "Live process" card
 * pattern used as the visual reference for this dashboard: each earnings
 * report's key metrics read as a short, ordered sequence rather than a
 * flat bullet list.
 */
export function StepList({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <ol className="flex flex-col">
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        return (
          <li key={index} className="flex gap-3">
            <div className="flex flex-col items-center">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-[13px] font-bold text-accent dark:bg-accent/20">
                {index + 1}
              </div>
              {!isLast && <div className="my-0.5 w-px flex-1 bg-black/10 dark:bg-white/10" />}
            </div>
            <div
              className={`flex-1 rounded-xl border border-black/[0.06] bg-white px-3.5 py-2.5 text-[13px] leading-snug text-[#2b2e35] dark:border-white/[0.08] dark:bg-white/[0.03] dark:text-[#dcdee2] ${
                isLast ? "mb-0" : "mb-2"
              }`}
            >
              {item}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
