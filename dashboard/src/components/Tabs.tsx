export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: string[];
  active: string;
  onChange: (tab: string) => void;
}) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-black/[0.06] dark:border-white/[0.08]">
      {tabs.map((tab) => (
        <button
          key={tab}
          onClick={() => onChange(tab)}
          className={`shrink-0 border-b-2 px-3.5 py-2.5 text-[13px] font-semibold transition-colors ${
            active === tab
              ? "border-accent text-[#15171c] dark:text-[#e7e8ea]"
              : "border-transparent text-[#8b8f99] hover:text-[#5b5f6b] dark:hover:text-[#b5b8c0]"
          }`}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}
