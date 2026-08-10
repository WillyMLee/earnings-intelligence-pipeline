export type CoverageGroup = {
  id: string;
  name: string;
  shortName: string;
  description: string;
  icon: "cloud" | "stars" | "chip" | "layers" | "shield" | "database" | "megaphone" | "bolt" | "bank" | "cart" | "factory" | "health" | "portfolio";
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
    tickers: new Set(["PLTR", "DDOG", "MDB", "ESTC"]),
  },
  {
    id: "ad-marketing-tech",
    name: "Ad & Marketing Tech",
    shortName: "Ad & marketing tech",
    description: "Ad buying, measurement, monetization and customer-engagement signals across independent platforms and marketing software.",
    icon: "megaphone",
    tickers: new Set(["APP", "TTD", "ZETA", "BRZE", "KVYO", "MGNI", "PUBM", "RDDT"]),
  },
  {
    id: "neostellar-portcos",
    name: "Neostellar Portcos",
    shortName: "Neostellar",
    description: "Portfolio-level earnings coverage across Lime, GrabAGun, CoreWeave, PSQ Holdings and Skillsoft.",
    icon: "portfolio",
    tickers: new Set(["LIME", "PEW", "CRWV", "PSQH", "SKIL"]),
  },
  {
    id: "power-data-centers",
    name: "Power & Data Centers",
    shortName: "Power & data centers",
    description: "Power availability, equipment demand and data-center buildout read-throughs.",
    icon: "bolt",
    tickers: new Set(["VST", "CEG", "ETN", "NRG", "OKLO", "GEV"]),
  },
  {
    id: "financials-payments",
    name: "Financials & Payments",
    shortName: "Financials",
    description: "Credit, capital markets, transaction volumes and consumer-spending read-throughs.",
    icon: "bank",
    tickers: new Set(["JPM", "BAC", "WFC", "C", "GS", "MS", "AXP", "V", "MA", "PYPL", "COF", "SCHW", "BLK"]),
  },
  {
    id: "consumer-commerce",
    name: "Consumer & Commerce",
    shortName: "Consumer",
    description: "Household demand, travel, advertising and digital-commerce signals across major platforms.",
    icon: "cart",
    tickers: new Set(["WMT", "COST", "HD", "LOW", "MCD", "SBUX", "NKE", "DIS", "NFLX", "UBER", "DASH", "ABNB", "BKNG"]),
  },
  {
    id: "industrials-aerospace",
    name: "Industrials & Aerospace",
    shortName: "Industrials",
    description: "Order books, freight, construction, defense and manufacturing-cycle indicators.",
    icon: "factory",
    tickers: new Set(["BA", "CAT", "HON", "GE", "RTX", "LMT", "NOC", "UPS", "FDX", "UNP", "DE", "ETN", "GEV"]),
  },
  {
    id: "healthcare",
    name: "Healthcare",
    shortName: "Healthcare",
    description: "Drug launches, procedure volumes, managed-care trends and R&D productivity.",
    icon: "health",
    tickers: new Set(["LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ISRG", "AMGN", "GILD", "PFE"]),
  },
];

export function getCoverageGroup(id: string) {
  return COVERAGE_GROUPS.find((group) => group.id === id) ?? COVERAGE_GROUPS[0];
}
