export type CoverageGroup = {
  id: string;
  name: string;
  shortName: string;
  description: string;
  icon: "cloud" | "stars" | "chip" | "layers" | "shield" | "database" | "bolt";
  tickers: Set<string>;
};

export const COVERAGE_GROUPS: CoverageGroup[] = [
  {
    id: "hyperscalers",
    name: "Hyperscalers + Meta",
    shortName: "Hyperscalers + Meta",
    description: "Cloud demand, AI infrastructure spend, capacity and monetization across the largest platforms, with Meta included as a peer-scale AI infrastructure buyer.",
    icon: "cloud",
    tickers: new Set(["MSFT", "AMZN", "GOOGL", "META", "ORCL"]),
  },
  {
    id: "mag7",
    name: "Magnificent Seven",
    shortName: "Mag 7",
    description: "The market's most influential technology platforms, viewed as one reporting cohort.",
    icon: "stars",
    tickers: new Set(["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]),
  },
  {
    id: "ai-infrastructure",
    name: "AI Infrastructure",
    shortName: "AI infrastructure",
    description: "Compute, networking, memory and storage companies carrying the AI capital cycle.",
    icon: "chip",
    tickers: new Set(["NVDA", "AMD", "AVGO", "ANET", "ARM", "MU", "LRCX", "KLAC", "WDC", "STX", "SNDK", "DELL"]),
  },
  {
    id: "saas",
    name: "SaaS",
    shortName: "SaaS",
    description: "Seat growth, retention, bookings, margins and AI monetization across application software.",
    icon: "layers",
    tickers: new Set(["CRM", "NOW", "SNOW", "ADBE", "TEAM", "HUBS", "WDAY", "GTLB", "MNDY", "BILL", "SHOP", "TOST"]),
  },
  {
    id: "cybersecurity",
    name: "Cybersecurity",
    shortName: "Cybersecurity",
    description: "Platform consolidation, ARR, billings and security-spend durability across major vendors.",
    icon: "shield",
    tickers: new Set(["PANW", "CRWD", "ZS", "FTNT", "OKTA", "NET", "S"]),
  },
  {
    id: "data-platforms",
    name: "Data & AI Software",
    shortName: "Data & AI software",
    description: "Consumption, developer activity and production AI workloads across data and observability platforms.",
    icon: "database",
    tickers: new Set(["PLTR", "DDOG", "MDB", "CFLT", "ESTC", "APP", "TTD"]),
  },
  {
    id: "power-data-centers",
    name: "Power & Data Centers",
    shortName: "Power & data centers",
    description: "Power availability, equipment demand and data-center buildout read-throughs.",
    icon: "bolt",
    tickers: new Set(["VST", "CEG", "ETN", "NRG", "OKLO", "GEV"]),
  },
];

export function getCoverageGroup(id: string) {
  return COVERAGE_GROUPS.find((group) => group.id === id) ?? COVERAGE_GROUPS[0];
}
