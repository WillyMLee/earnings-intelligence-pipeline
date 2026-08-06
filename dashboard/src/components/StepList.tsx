/**
 * A numbered, connected step list -- rounded number badge + connecting
 * line on the left, plain text (no per-item box) on the right, marked with
 * a small accent-colored bullet dot for scannability. Mirrors the "Live
 * process" reference card's badge/connector, but each item reads as a
 * normal readable line instead of its own bordered card -- the boxed-per-
 * bullet look got noisy once a section had more than 3-4 items.
 */
export function StepList({ items, isLastGroup = true }: { items: string[]; isLastGroup?: boolean }) {
  if (items.length === 0) return null;
  return (
    <ol className="flex flex-col">
      {items.map((item, index) => {
        const isLastItem = index === items.length - 1;
        const showConnector = !isLastItem || !isLastGroup;
        return (
          <li key={index} className="flex gap-3">
            <div className="flex flex-col items-center">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-[13px] font-bold text-accent dark:bg-accent/20">
                {index + 1}
              </div>
              {showConnector && <div className="my-0.5 w-px flex-1 bg-black/10 dark:bg-white/10" />}
            </div>
            <div className={`flex flex-1 gap-2 py-1 text-[13px] leading-snug text-[#2b2e35] dark:text-[#dcdee2] ${isLastItem ? "pb-2.5" : "pb-4"}`}>
              <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
              <span>{item}</span>
            </div>
          </li>
        );
      })}
    </ol>
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
    <div className="flex flex-col">
      {nonEmpty.map((group, gi) => {
        const isLastGroup = gi === nonEmpty.length - 1;
        return (
          <div key={gi}>
            {gi > 0 && (
              <div className="flex gap-3">
                <div className="flex w-7 shrink-0 justify-center">
                  <div className="my-0.5 w-px flex-1 bg-black/10 dark:bg-white/10" />
                </div>
                <div className="flex-1" />
              </div>
            )}
            <div className="mb-2 flex gap-3">
              <div className="w-7 shrink-0" />
              <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99] dark:text-[#7d818c]">
                {group.heading}
              </div>
            </div>
            <StepList items={group.items} isLastGroup={isLastGroup} />
          </div>
        );
      })}
    </div>
  );
}
