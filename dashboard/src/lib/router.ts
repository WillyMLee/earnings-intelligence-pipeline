import { useEffect, useState } from "react";

// Deliberately dependency-free: this app has three views (dashboard, feed,
// company profile), so a small hash-based router covers it without pulling
// in react-router. Hash routing also means the Workers static-asset SPA
// fallback (wrangler.jsonc's not_found_handling) never has to deal with
// nested real paths at all -- every route is the same index.html.
export type Route =
  | { name: "dashboard" }
  | { name: "calendar" }
  | { name: "feed" }
  | { name: "sectors"; groupId: string }
  | { name: "company"; ticker: string };

function parseHash(hash: string): Route {
  const path = hash.replace(/^#\/?/, "");
  const [segment, ticker] = path.split("/");
  if (segment === "company" && ticker) {
    return { name: "company", ticker: ticker.toUpperCase() };
  }
  if (segment === "sectors") return { name: "sectors", groupId: ticker || "hyperscalers" };
  if (segment === "calendar") return { name: "calendar" };
  if (segment === "feed") return { name: "feed" };
  return { name: "dashboard" };
}

export function useRoute(): [Route, (route: Route) => void] {
  const [route, setRouteState] = useState<Route>(() => parseHash(window.location.hash));

  useEffect(() => {
    const onHashChange = () => setRouteState(parseHash(window.location.hash));
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const setRoute = (next: Route) => {
    if (next.name === "company") window.location.hash = `/company/${next.ticker}`;
    else if (next.name === "sectors") window.location.hash = `/sectors/${next.groupId}`;
    else if (next.name === "calendar") window.location.hash = "/calendar";
    else if (next.name === "feed") window.location.hash = "/feed";
    else window.location.hash = "/";
  };

  return [route, setRoute];
}
