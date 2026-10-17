#!/usr/bin/env node
// shot.mjs — drive the dev web app through a JSON list of steps in headless
// Chromium, for before/after screenshots and DOM checks.
//
//   node shot.mjs steps.json
//
// Env: T3_CHECKOUT (default ~/w/t3code; playwright-core is loaded from its
// node_modules), PROFILE (Chromium profile dir, default /tmp/t3dev/chrome),
// PAIR_URL (visited first, so a fresh profile gets credentials; take it from
// `t3dev pair-url`), CHROMIUM (default /usr/bin/chromium).
//
// Steps run in order; each object may hold one or more of:
//   goto, wait (ms), waitFor (selector), click, button, hover, fill+text,
//   type+text (click then type), keys, press, eval (JS, result is printed),
//   shot (path) with optional clip {x,y,width,height}, required (stop on failure)
// Selectors are Playwright's, e.g. "a:has-text('recording.mp3') >> nth=-1".
// Console errors and failed steps are printed, with pairing tokens redacted.
// Exits 1 if any step failed, so a broken check can't pass as a screenshot.
import { readFileSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const checkout = process.env.T3_CHECKOUT ?? join(homedir(), "w/t3code");
const pnpmDir = join(checkout, "node_modules/.pnpm");
const playwrightDir = readdirSync(pnpmDir)
  .filter((name) => name.startsWith("playwright-core@"))
  .sort()
  .at(-1);
if (!playwrightDir) throw new Error(`no playwright-core under ${pnpmDir}; run pnpm install there`);
const { chromium } = await import(
  pathToFileURL(join(pnpmDir, playwrightDir, "node_modules/playwright-core/index.mjs")).href
);

const steps = JSON.parse(readFileSync(process.argv[2], "utf8"));
if (process.env.PAIR_URL) steps.unshift({ goto: process.env.PAIR_URL }, { wait: 8000 });
const context = await chromium.launchPersistentContext(process.env.PROFILE ?? "/tmp/t3dev/chrome", {
  executablePath: process.env.CHROMIUM ?? "/usr/bin/chromium",
  headless: true,
  viewport: { width: 1400, height: 900 },
  args: ["--autoplay-policy=no-user-gesture-required"],
});
const page = context.pages()[0] ?? (await context.newPage());
const log = [];
let failed = false;
const redact = (text) => String(text).replace(/token=[^\s"'&]+/g, "token=REDACTED");
page.on("console", (message) => {
  if (message.type() !== "error") return;
  const line = `console: ${redact(message.text()).slice(0, 300)}`;
  if (!log.includes(line)) log.push(line);
});
for (const step of steps) {
  try {
    if (step.goto) await page.goto(step.goto, { waitUntil: "domcontentloaded" });
    if (step.wait) await page.waitForTimeout(step.wait);
    if (step.waitFor) await page.locator(step.waitFor).first().waitFor({ timeout: step.timeout ?? 30000 });
    if (step.click)
      await page
        .locator(step.click)
        .first()
        .click({ timeout: 15000, ...(step.button ? { button: step.button } : {}) });
    if (step.hover) await page.locator(step.hover).first().hover({ timeout: 15000 });
    if (step.fill) await page.locator(step.fill).first().fill(step.text);
    if (step.type) {
      await page.locator(step.type).first().click();
      await page.keyboard.type(step.text);
    }
    if (step.keys) await page.keyboard.type(step.keys);
    if (step.press) await page.keyboard.press(step.press);
    if (step.eval) log.push(`eval: ${JSON.stringify(await page.evaluate(step.eval)).slice(0, 4000)}`);
    if (step.shot)
      await page.screenshot({ path: step.shot, fullPage: false, ...(step.clip ? { clip: step.clip } : {}) });
  } catch (error) {
    failed = true;
    log.push(`step ${redact(JSON.stringify(step)).slice(0, 120)} failed: ${redact(error).slice(0, 300)}`);
    if (step.required) break;
  }
}
console.log(log.join("\n"));
await context.close();
process.exitCode = failed ? 1 : 0;
