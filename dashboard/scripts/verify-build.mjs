import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const html = readFileSync(resolve("dist/index.html"), "utf8");
const universe = JSON.parse(readFileSync(resolve("src/data/neostellarEarningsUniverse.json"), "utf8"));

if (html.includes('/src/main.tsx')) {
  throw new Error("Production index still points at the Vite source entrypoint.");
}
if (!/\/assets\/index-[^\"']+\.js/.test(html)) {
  throw new Error("Production index does not reference a compiled JavaScript asset.");
}

const sp500 = new Set(universe.sp500);
const additions = new Set(universe.thematicAdditions);
const emailDeepDive = new Set(universe.emailDeepDive);
if (sp500.size !== 503 || sp500.size !== universe.sp500.length) {
  throw new Error(`Expected 503 unique S&P 500 securities; found ${sp500.size}.`);
}
if ([...additions].some((ticker) => sp500.has(ticker))) {
  throw new Error("Neostellar additions must not duplicate current S&P 500 constituents.");
}
if ([...emailDeepDive].some((ticker) => !sp500.has(ticker) && !additions.has(ticker))) {
  throw new Error("Every email deep-dive name must also be available on the website.");
}
if (emailDeepDive.size !== 88 || emailDeepDive.size !== universe.emailDeepDive.length) {
  throw new Error(`Expected 88 unique email deep-dive names; found ${emailDeepDive.size}.`);
}
if (emailDeepDive.size >= sp500.size + additions.size) {
  throw new Error("Email coverage must remain narrower than website coverage.");
}
for (const ticker of ["AAPL", "MU", "SNDK", "STX", "WDC", "CRM", "CRWD", "DDOG", "TSM", "ASML", "SNOW", "CRWV", "ALAB", "BRZE", "CLS", "CRDO", "IOT", "KVYO", "LITE", "PCOR", "PSTG", "RBRK", "ZETA"]) {
  if (!sp500.has(ticker) && !additions.has(ticker)) throw new Error(`Required coverage ticker missing: ${ticker}`);
}
for (const ticker of ["FLWS", "YI", "FEAM", "AAFR", "LONA", "ALLR"]) {
  if (sp500.has(ticker) || additions.has(ticker)) throw new Error(`Out-of-scope ticker leaked into coverage: ${ticker}`);
}

console.log(`[verify-build] compiled dashboard confirmed with ${sp500.size + additions.size} site securities and ${emailDeepDive.size} email names`);
