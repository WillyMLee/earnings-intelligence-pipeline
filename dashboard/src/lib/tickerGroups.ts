import { NEOSTELLAR_ADDITIONS, SP500_TICKERS } from "./earningsUniverse";
import { COVERAGE_GROUPS } from "./coverageGroups";

export const MAG7_TICKERS = new Set([
  "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
]);

export const NEOSTELLAR_THEME_TICKERS = new Set([
  ...NEOSTELLAR_ADDITIONS,
  ...COVERAGE_GROUPS.flatMap((group) => Array.from(group.tickers)),
]);

export type TickerFilter = "all" | "sp500" | "themes" | "mag7";

export const TICKER_FILTER_LABEL: Record<TickerFilter, string> = {
  all: "All tracked",
  sp500: "S&P 500",
  themes: "Neostellar themes",
  mag7: "Mag 7",
};

export { NEOSTELLAR_ADDITIONS, SP500_TICKERS };
