// No ticker->domain mapping is archived anywhere in this pipeline, so this
// is a best-effort guess (strip legal suffixes, lowercase, append .com) fed
// to Clearbit's free public logo API. It's wrong often enough on purpose --
// callers must render a fallback (e.g. the ticker-initial badge already
// used in EarningsCard) on image error, never assume this resolves.
const LEGAL_SUFFIXES = / (inc|incorporated|corp|corporation|co|company|group|holdings|holding|ltd|limited|plc|llc|technologies|financial)\.?$/i;

export function guessLogoUrl(company: string): string {
  const cleaned = company.replace(LEGAL_SUFFIXES, "").trim();
  const slug = cleaned
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
  return `https://logo.clearbit.com/${slug}.com`;
}
