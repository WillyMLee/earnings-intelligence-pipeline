function ItemText({ text }: { text: string }) {
  const separator = text.indexOf(":");
  if (separator <= 0 || separator > 42) return <>{text}</>;
  return <><strong className="font-semibold text-[#15171c] dark:text-[#e7e8ea]">{text.slice(0, separator + 1)}</strong>{text.slice(separator + 1)}</>;
}

export function StepList({ items }: { items: string[]; isLastGroup?: boolean }) {
  if (items.length === 0) return null;
  return (
    <ul className="space-y-2.5">
      {items.map((item, index) => (
        <li key={index} className="flex gap-2.5 text-[13px] leading-relaxed text-[#454951] dark:text-[#c4c7ce]">
          <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-accent/80" />
          <span><ItemText text={item} /></span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Several StepLists (e.g. "Financial highlights" then a handful of
 * thematic sections) rendered as ONE continuous numbered flow -- the
 * connecting line runs through each heading rather than stopping and
 * restarting in a separate boxed card per section, so the whole brief
 * reads as a single connected sequence. Numbering itself still restarts
 * per group (each group is its own short, ordered list); only the visual
 * connector is continuous.
 */
export function ConnectedStepGroups({ groups }: { groups: { heading: string; items: string[] }[] }) {
  const nonEmpty = groups.filter((g) => g.items.length > 0);
  if (nonEmpty.length === 0) return null;
  return (
    <div className="flex flex-col gap-3">
      {nonEmpty.map((group, gi) => {
        const isPrimary = gi === 0;
        return (
          <details key={gi} open={isPrimary} className="group rounded-xl border border-black/[0.06] bg-black/[0.015] px-4 py-3 dark:border-white/[0.07] dark:bg-white/[0.02]">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-[11px] font-semibold uppercase tracking-[0.1em] text-[#717681] marker:hidden dark:text-[#8f949f]">
              <span>{group.heading}</span>
              <span className="flex items-center gap-2 normal-case tracking-normal text-[#9a9ea8]">
                {group.items.length} point{group.items.length === 1 ? "" : "s"}
                <span className="text-[14px] transition-transform group-open:rotate-45">＋</span>
              </span>
            </summary>
            <div className="mt-3 border-t border-black/[0.05] pt-3 dark:border-white/[0.06]">
              <StepList items={group.items} />
            </div>
          </details>
        );
      })}
    </div>
  );
}
