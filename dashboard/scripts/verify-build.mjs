import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const html = readFileSync(resolve("dist/index.html"), "utf8");

if (html.includes('/src/main.tsx')) {
  throw new Error("Production index still points at the Vite source entrypoint.");
}
if (!/\/assets\/index-[^\"']+\.js/.test(html)) {
  throw new Error("Production index does not reference a compiled JavaScript asset.");
}

console.log("[verify-build] compiled dashboard entrypoint confirmed");
