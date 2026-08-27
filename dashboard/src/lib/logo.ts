import companyIdentities from "../data/companyIdentities.json";

type CompanyIdentity = { domain: string; name: string };

const LEGAL_SUFFIXES = / (inc|incorporated|corp|corporation|co|company|group|holdings|holding|ltd|limited|plc|llc|technologies|financial)\.?$/i;

export function companyDomain(ticker: string, company: string): string {
  const normalizedTicker = ticker.trim().toUpperCase().replace(/\./g, "-");
  const identity = (companyIdentities as Record<string, CompanyIdentity>)[normalizedTicker];
  if (identity) return identity.domain;

  const cleaned = company.replace(LEGAL_SUFFIXES, "").trim();
  const slug = cleaned
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
  return `${slug}.com`;
}

export function logoUrl(ticker: string, company: string): string {
  const domain = companyDomain(ticker, company);
  return `https://www.google.com/s2/favicons?domain_url=${encodeURIComponent(`https://${domain}`)}&sz=128`;
}
