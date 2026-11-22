import { chromium } from "playwright"; import fs from "node:fs";
const [inp, out] = process.argv.slice(2);
const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1.5 });
await p.setContent(`<html><body style="margin:0">${fs.readFileSync(inp, "utf8")}</body></html>`);
await p.locator("svg").screenshot({ path: out }); await b.close();
