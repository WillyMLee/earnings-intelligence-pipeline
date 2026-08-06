export function StatCell({
  label,
  value,
  sublabel,
}: {
  label: string;
  value: string;
  sublabel?: string;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-[#8b8f99] dark:text-[#7d818c]">
        {label}
      </div>
      <div className="mt-0.5 truncate text-[14px] font-semibold text-[#15171c] dark:text-[#e7e8ea]">{value}</div>
      {sublabel && <div className="text-[11px] text-[#9a9ea8]">{sublabel}</div>}
    </div>
  );
}
