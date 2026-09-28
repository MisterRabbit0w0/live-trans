// Visual QA capture: drives the browser-mock frontend through every page,
// theme, material mode and state, saving screenshots to QA_OUT.
// Usage: QA_OUT=<dir> QA_BASE=http://localhost:5173 node scripts/visual-qa.mjs
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { chromium } from "playwright";

const OUT =
  process.env.QA_OUT ??
  join(process.env.TEMP ?? ".", "livetrans-ui", "b2");
const BASE = process.env.QA_BASE ?? "http://localhost:5173";
const SETTLE = Number(process.env.QA_SETTLE ?? 450);

await mkdir(OUT, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1040, height: 720 },
  deviceScaleFactor: 1.5,
});
const page = await context.newPage();
page.on("pageerror", (err) => console.error("PAGEERROR:", err.message));
page.on("console", (msg) => {
  if (msg.type() === "error") console.error("CONSOLE:", msg.text());
});

async function shot(name, url, wait = SETTLE) {
  await page.goto(`${BASE}/${url}`, { waitUntil: "load" });
  await page.waitForTimeout(wait);
  await page.screenshot({ path: join(OUT, `${name}.png`) });
  console.log("saved", name);
}

const PAGES = [
  "overview",
  "audio",
  "asr",
  "translate",
  "subtitle",
  "records",
  "general",
];

for (const theme of ["light", "dark"]) {
  for (let i = 0; i < PAGES.length; i++) {
    await shot(
      `p${i}-${PAGES[i]}-${theme}`,
      `index.html?page=${i}&theme=${theme}&material=css`,
    );
  }
}

await shot(
  "overview-live",
  "index.html?page=0&theme=light&material=css&running=1&notice=1&dirty=1",
);
// ASR page with advanced section open + field error — scrolled to the bottom
// so the VAD controls and the error hint are actually in frame.
await page.goto(
  `${BASE}/index.html?page=2&adv=1&err=vad_silence_ms&theme=light&material=css`,
  { waitUntil: "load" },
);
await page.waitForTimeout(SETTLE);
await page.locator(".scroll").evaluate((el) => (el.scrollTop = el.scrollHeight));
await page.waitForTimeout(250);
await page.screenshot({ path: join(OUT, "asr-advanced-error.png") });
console.log("saved asr-advanced-error");

// Select popup open on the ASR page (源语言 combobox).
await page.goto(`${BASE}/index.html?page=2&theme=light&material=css`, {
  waitUntil: "load",
});
await page.waitForTimeout(SETTLE);
await page.locator('[data-path="asr.language"]').click();
await page.waitForTimeout(250);
await page.screenshot({ path: join(OUT, "select-popup.png") });
console.log("saved select-popup");

// Quit dialog via Ctrl+Q with a dirty draft.
await page.goto(`${BASE}/index.html?dirty=1&theme=light&material=css`, {
  waitUntil: "load",
});
await page.waitForTimeout(SETTLE);
await page.keyboard.press("Control+q");
await page.waitForTimeout(300);
await page.screenshot({ path: join(OUT, "quit-dialog.png") });
console.log("saved quit-dialog");

await shot(
  "general-dark-accent",
  "index.html?page=6&theme=dark&accent=%23c0265e&material=css",
);
await shot(
  "overview-solid",
  "index.html?page=0&theme=light&material=solid",
);
await shot(
  "subtitle-page-solid",
  "index.html?page=4&theme=dark&material=solid",
);

// Forced colors (Windows high-contrast) emulation.
const hc = await browser.newContext({
  viewport: { width: 1040, height: 720 },
  deviceScaleFactor: 1.5,
  forcedColors: "active",
});
const hcPage = await hc.newPage();
await hcPage.goto(`${BASE}/index.html?page=0&theme=light`, {
  waitUntil: "load",
});
await hcPage.waitForTimeout(SETTLE);
await hcPage.screenshot({ path: join(OUT, "overview-forced.png") });
console.log("saved overview-forced");
await hc.close();

// Subtitle overlay on a busy backdrop.
await page.goto(`${BASE}/subtitle.html?running=1&subs=3`, {
  waitUntil: "load",
});
await page.evaluate(() => {
  const behind = document.createElement("div");
  behind.style.cssText =
    "position:fixed;inset:0;z-index:-1;background:" +
    "radial-gradient(60% 80% at 20% 20%, #d9480f 0%, transparent 60%)," +
    "radial-gradient(50% 70% at 80% 30%, #1c7ed6 0%, transparent 65%)," +
    "radial-gradient(70% 60% at 50% 90%, #2f9e44 0%, transparent 60%)," +
    "linear-gradient(135deg,#868e96,#343a40)";
  document.body.appendChild(behind);
});
await page.waitForTimeout(SETTLE);
await page.screenshot({ path: join(OUT, "overlay-busy.png") });
console.log("saved overlay-busy");

await browser.close();
console.log("done ->", OUT);
