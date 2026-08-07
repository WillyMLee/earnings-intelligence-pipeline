import type { CoverageGroup } from "../lib/coverageGroups";

const PATHS: Record<CoverageGroup["icon"], React.ReactNode> = {
  cloud: <><path d="M6.5 18a4.5 4.5 0 0 1-.5-8.97A6 6 0 0 1 17.6 7.5 4 4 0 1 1 18 18H6.5Z" /></>,
  stars: <><path d="m12 3 1.4 4.1L17.5 8.5l-4.1 1.4L12 14l-1.4-4.1-4.1-1.4 4.1-1.4L12 3Z" /><path d="m18.5 14 .7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7.7-2.3Z" /></>,
  chip: <><rect x="7" y="7" width="10" height="10" rx="2" /><path d="M9 1v3m6-3v3M9 20v3m6-3v3M1 9h3m-3 6h3m16-6h3m-3 6h3M10 10h4v4h-4z" /></>,
  layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5M3 16l9 5 9-5" /></>,
  shield: <><path d="M12 3 4.5 6v5.5c0 4.8 3.1 7.9 7.5 9.5 4.4-1.6 7.5-4.7 7.5-9.5V6L12 3Z" /><path d="m9 12 2 2 4-4" /></>,
  database: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></>,
  bolt: <><path d="m13 2-8 12h7l-1 8 8-12h-7l1-8Z" /></>,
};

export function CoverageGroupIcon({ icon, size = 36 }: { icon: CoverageGroup["icon"]; size?: number }) {
  return (
    <span className="grid shrink-0 place-items-center rounded-xl bg-accent-soft text-accent dark:bg-accent/15" style={{ width: size, height: size }}>
      <svg width={Math.round(size * 0.56)} height={Math.round(size * 0.56)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {PATHS[icon]}
      </svg>
    </span>
  );
}
