import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}-${path}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(new Request(`http://localhost${path}`, { headers: { accept: "text/html" } }), { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } }, { waitUntil() {}, passThroughOnException() {} });
}

test("server-renders the standalone master dashboard and complete ranking", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Backtest Intelligence/);
  assert.match(html, /Every strategy\. One evidence trail\./);
  assert.match(html, /Backtest rankings/);
  assert.match(html, /Historical excess/);
  assert.match(html, /Buy &amp; hold horizons/);
  assert.match(html, /Search name or code/);
  assert.match(html, /Columns \([^)]*7[^)]*\)/);
  assert.match(html, /Switch to dark mode/);
  assert.equal((html.match(/class="fund-identity"/g) ?? []).length, 11);
  assert.equal((html.match(/class="mobile-result"/g) ?? []).length, 11);
  assert.doesNotMatch(html, /Daily Monitoring|Fund Signal/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/);
});

test("server-renders a shareable fund detail with all chart modes", async () => {
  const response = await render("/funds/makgcf");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Greater China/);
  assert.match(html, /Master dashboard/);
  assert.match(html, /Parameters and run quality/);
  assert.match(html, /Latest technical/);
  assert.match(html, /Source technical/);
  assert.match(html, /Simple comparison/);
  assert.match(html, /MAKGCF[\s\S]*Data through/);
  assert.match(html, /\/backtests\/makgcf-latest-technical\.png/);
});

test("keeps theme, responsive cards, generated data, and metadata isolated", async () => {
  const [page, css, layout, generated, pkg] = await Promise.all([
    readFile(new URL("../app/backtest-dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/backtest-data.generated.ts", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);
  assert.match(page, /type SortKey = "latest" \| "annualized" \| "buyHold" \| "excess" \| "drawdown"/);
  assert.match(page, /localStorage\.setItem\("backtest-theme"/);
  assert.match(page, /role="tablist"/);
  assert.match(page, /Chart unavailable/);
  assert.match(css, /@media\(max-width:760px\)/);
  assert.match(css, /\.mobile-results\{display:none\}/);
  assert.match(css, /:root\[data-theme="dark"\]/);
  assert.match(layout, /\/og\.png/);
  assert.match(layout, /metadataBase/);
  assert.match(generated, /export const backtestSnapshot/);
  assert.equal((generated.match(/"id":/g) ?? []).length, 11);
  assert.match(pkg, /"name": "backtest-intelligence-dashboard"/);
  assert.doesNotMatch(pkg, /react-loading-skeleton/);
});
