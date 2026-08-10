const DISPLAY_NAMES: Record<string, string> = {
  AAL: "American Airlines", AAPL: "Apple", ABBV: "AbbVie", ABNB: "Airbnb", ABT: "Abbott",
  ADBE: "Adobe", AMD: "AMD", AMGN: "Amgen", AMZN: "Amazon", ANET: "Arista Networks",
  APP: "AppLovin", ARM: "Arm", ASML: "ASML", AVGO: "Broadcom", AXON: "Axon Enterprise",
  BA: "Boeing", BAC: "Bank of America", BILL: "BILL", BKNG: "Booking Holdings", BLK: "BlackRock", BRZE: "Braze",
  BRK_B: "Berkshire Hathaway", C: "Citi", CBRS: "Cerebras", CFLT: "Confluent", COF: "Capital One",
  COP: "ConocoPhillips", COST: "Costco", CRWD: "CrowdStrike", CRWV: "CoreWeave", CSCO: "Cisco",
  CVX: "Chevron", DAL: "Delta Air Lines", DASH: "DoorDash", DE: "Deere", DELL: "Dell", DHR: "Danaher",
  EMR: "Emerson", ESTC: "Elastic", ETN: "Eaton", FDX: "FedEx", FIS: "FIS", GE: "GE Aerospace",
  GEV: "GE Vernova", GOOG: "Alphabet", GOOGL: "Alphabet", GS: "Goldman Sachs", GTLB: "GitLab",
  HD: "Home Depot", HON: "Honeywell", HUBS: "HubSpot", IBM: "IBM", INTC: "Intel",
  IAS: "Integral Ad Science", ISRG: "Intuitive Surgical", JNJ: "Johnson & Johnson", JPM: "JPMorgan", KLAC: "KLA", KVYO: "Klaviyo", LLY: "Eli Lilly",
  LMT: "Lockheed Martin", LOW: "Lowe's", LRCX: "Lam Research", MA: "Mastercard", MCD: "McDonald's",
  META: "Meta", MGNI: "Magnite", MNDY: "monday.com", MRK: "Merck", MS: "Morgan Stanley", MSFT: "Microsoft",
  MU: "Micron", NFLX: "Netflix", NKE: "Nike", NOC: "Northrop Grumman", NOW: "ServiceNow",
  NRG: "NRG Energy", NVDA: "NVIDIA", OKLO: "Oklo", ORCL: "Oracle", PANW: "Palo Alto Networks",
  PFE: "Pfizer", PG: "P&G", PLTR: "Palantir", PUBM: "PubMatic", PYPL: "PayPal", QCOM: "Qualcomm", RDDT: "Reddit", RTX: "RTX",
  S: "SentinelOne", SBUX: "Starbucks", SCHW: "Charles Schwab", SHOP: "Shopify", SNDK: "Sandisk",
  SNOW: "Snowflake", STX: "Seagate", T: "AT&T", TEAM: "Atlassian", TMO: "Thermo Fisher Scientific",
  TMUS: "T-Mobile US", TOST: "Toast", TSLA: "Tesla", TTD: "The Trade Desk", UNH: "UnitedHealth Group",
  UNP: "Union Pacific", UPS: "UPS", V: "Visa", VST: "Vistra", WDAY: "Workday",
  WDC: "Western Digital", WFC: "Wells Fargo", WMT: "Walmart", XOM: "ExxonMobil", ZETA: "Zeta Global", ZS: "Zscaler",
};

const LEGAL_SUFFIX = /(?:,?\s+(?:incorporated|inc\.?|corporation|corp\.?|company|co\.?|holdings?|limited|ltd\.?|plc|llc|public))+(?:\s+class\s+[a-z])?$/i;

export function displayCompanyName(ticker: string, rawName: string): string {
  const symbol = ticker.trim().toUpperCase().replace(".", "_");
  if (DISPLAY_NAMES[symbol]) return DISPLAY_NAMES[symbol];
  const cleaned = String(rawName || ticker).replace(LEGAL_SUFFIX, "").trim();
  if (!cleaned) return ticker.toUpperCase();
  if (cleaned === cleaned.toUpperCase()) {
    return cleaned.toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase()).replace(/'S\b/g, "'s");
  }
  return cleaned;
}
