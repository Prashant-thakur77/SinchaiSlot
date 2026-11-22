import { chromium } from "playwright"; import path from "node:path";
const deck = path.resolve(process.argv[2]); const out = path.resolve(process.argv[3]);
const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
await p.goto("file://" + deck, { waitUntil: "networkidle" }); await p.waitForTimeout(1500);
await p.pdf({ path: out, width: "1920px", height: "1080px", printBackground: true });
const n = await p.locator("section.s").count();
for (const i of [0, 5, 9, 10]) await p.locator("section.s").nth(i).screenshot({ path: out.replace(".pdf", `-slide${i + 1}.png`) });
console.log("slides", n); await b.close();
