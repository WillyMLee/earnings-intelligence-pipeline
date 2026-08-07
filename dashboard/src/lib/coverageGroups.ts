export type CoverageGroup = {
  id: string;
  name: string;
  shortName: string;
  description: string;
  tickers: Set<string>;
};

export const COVERAGE_GROUPS: CoverageGroup[] = [
  {
    id: "hyperscalers",
    name: "Hyperscalers",
    shortName: "Hyperscalers",
    description: "Cloud demand, AI infrastructure spend, capacity and monetization across the largest platforms.",
    tickers: new Set(["MSFT", "AMZN", "GOOGL", "META", "ORCL"]),
  },
  {
    id: "mag7",
    name: "Magnificent Seven",
    shortName: "Mag 7",
    description: "The market's most influential technology platforms, viewed as one reporting cohort.",
    tickers: new Set(["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]),
  },
  {
    id: "ai-infrastructure",
    name: "AI Infrastructure",
    shortName: "AI infrastructure",
    description: "Compute, networking, memory and storage companies carrying the AI capital cycle.",
    tickers: new Set(["NVDA", "AMD", "AVGO", "ANET", "ARM", "MU", "LRCX", "KLAC", "WDC", "STX", "SNDK", "DELL"]),
  },
  {
    id: "software-cloud",
    name: "Software & Cloud",
    shortName: "Software & cloud",
    description: "Growth, consumption, seat expansion and AI monetization across enterprise software.",
    tickers: new Set(["PLTR", "DDOG", "NET", "TEAM", "HUBS", "CRM", "APP", "TTD"]),
  },
  {
    id: "power-data-centers",
    name: "Power & Data Centers",
    shortName: "Power & data centers",
    description: "Power availability, equipment demand and data-center buildout read-throughs.",
    tickers: new Set(["VST", "CEG", "ETN", "NRG", "OKLO", "GEV"]),
  },
];

export function getCoverageGroup(id: string) {
  return COVERAGE_GROUPS.find((group) => group.id === id) ?? COVERAGE_GROUPS[0];
}
