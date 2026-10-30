// Screenshot every chapter for review. Usage: node scripts/shoot.js [outDir] [baseUrl]
const { chromium } = require("playwright");
const path = require("path");
(async () => {
  const out = process.argv[2] || "/tmp/claude-0/-home-claude/2f035585-2158-5302-a9a4-4641ba856826/scratchpad/shots";
  const base = process.argv[3] || "http://127.0.0.1:8000/";
  require("fs").mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on("console", m => { if (["error", "warning"].includes(m.type()) && !/TUNNEL|GL Driver/.test(m.text())) errors.push(m.type() + ": " + m.text()); });
  page.on("pageerror", e => errors.push("pageerror: " + e.message));
  await page.goto(base, { waitUntil: "load" });
  await page.waitForTimeout(1500);
  await page.evaluate(() => window.__reach && window.__reach.stopAutopilot());
  const slides = await page.$$eval(".slide", els => els.map(e => e.dataset.slide));
  for (let i = 0; i < slides.length; i++) {
    await page.evaluate(i => document.querySelectorAll(".slide")[i].scrollIntoView({ behavior: "auto" }), i);
    await page.waitForTimeout(4500);
    if (slides[i] === "app") { await page.click("#compose"); await page.waitForTimeout(6500); await page.click("#play").catch(() => {}); await page.waitForTimeout(1500); }
    if (slides[i] === "trust") { await page.click("#verify"); await page.waitForTimeout(1200); }
    await page.screenshot({ path: path.join(out, `${i}-${slides[i]}.png`) });
    console.log("shot", slides[i]);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => document.querySelector('[data-lang="fa"]').click());
  await page.evaluate(() => document.querySelectorAll(".slide")[6].scrollIntoView({ behavior: "auto" }));
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(out, `m-app-fa.png`) });
  await page.evaluate(() => document.querySelectorAll(".slide")[0].scrollIntoView({ behavior: "auto" }));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(out, `m-human-fa.png`) });
  console.log(errors.slice(0, 20).join("\n") || "no console errors");
  await browser.close();
})();
