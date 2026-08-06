import { useEffect, useState } from "react";

// Deliberately dependency-free: this app has exactly two views (feed,
// company profile), so a small hash-based router covers it without pulling
// in react-router. Hash routing also means the Workers static-asset SPA
// fallback (wrangler.jsonc's not_found_handling) never has to deal with
// nested real paths at all -- every route is the same index.html.
export type Route = { name: "feed" } | { name: "company"; ticker: string };

function parseHash(hash: string): Route {
  const path = hash.replace(/^#\/?/, "");
  const [segment, ticker] = path.split("/");
  if (segment === "company" && ticker) {
    return { name: "company", ticker: ticker.toUpperCase() };
  }
  return { name: "feed" };
}

export function useRoute(): [Route, (route: Route) => void] {
  const [route, setRouteState] = useState<Route>(() => parseHash(window.location.hash));

  useEffect(() => {
    const onHashChange = () => setRouteState(parseHash(window.location.hash));
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const setRoute = (next: Route) => {
    window.location.hash = next.name === "company" ? `/company/${next.ticker}` : "/";
  };

  return [route, setRoute];
}
