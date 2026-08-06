// Mirrors render_pre_earnings_deep_dive_email.py's _CITATION_RE / strip
// helpers -- the archived brief text still has raw inline citations like
// "([reuters.com](https://...))" embedded (the Python email renderer
// strips these at render time, but the archived Convex row is the
// pre-stripped brief object). Strip the same way here so the dashboard's
// detailed view reads as clean prose with a separate sources list, not
// raw markdown-ish citation syntax inline.
const CITATION_RE = /\s*\(\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)\)/g;

export function stripCitations(text: string | null | undefined): { text: string; urls: string[] } {
  if (!text) return { text: "", urls: [] };
  const urls: string[] = [];
  let match: RegExpExecArray | null;
  const re = new RegExp(CITATION_RE);
  while ((match = re.exec(text)) !== null) {
    urls.push(match[2]);
  }
  return { text: text.replace(CITATION_RE, "").trim(), urls };
}

export function stripCitationsFromAll(texts: (string | null | undefined)[]): { texts: string[]; urls: string[] } {
  const urls = new Set<string>();
  const stripped = texts.map((t) => {
    const { text, urls: found } = stripCitations(t);
    found.forEach((u) => urls.add(u));
    return text;
  });
  return { texts: stripped, urls: Array.from(urls) };
}
