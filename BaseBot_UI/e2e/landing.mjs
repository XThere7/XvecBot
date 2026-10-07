/**
 * Landing page checks: sticky header nav, scroll blur, hero, how-it-works,
 * footer and the mobile menu.
 *
 * Usage: node e2e/landing.mjs [appUrl] (default http://localhost:3113)
 */
import { chromium } from "playwright-core";

const APP = process.argv[2] ?? process.env.APP_URL ?? "http://localhost:3113";

const browser = await chromium.launch({
  executablePath: "/usr/bin/chromium",
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await (
  await browser.newContext({ viewport: { width: 1440, height: 1000 } })
).newPage();
const errors = [];
page.on("console", (m) => {
  if (m.type() === "error") {
    errors.push(`${m.text().slice(0, 120)} @ ${JSON.stringify(m.location())}`);
  }
});
page.on("pageerror", (e) => errors.push(`PAGEERROR ${e.message.slice(0, 200)}`));

await page.goto(`${APP}/`, { waitUntil: "networkidle" });
await page.waitForTimeout(800);
await page.screenshot({ path: "e2e/landing-01-desktop.png", fullPage: true });
console.log(
  "header nav:",
  await page.locator('header nav a[href="/dashboard"]').count(),
  await page.locator('header nav a[href="/workspaces"]').count(),
  await page.locator('header nav a[href="/account"]').count(),
);

// Sticky header gains border + blur on scroll.
await page.evaluate(() => window.scrollTo(0, 400));
await page.waitForTimeout(400);
await page.screenshot({ path: "e2e/landing-02-scrolled.png" });

// Mobile menu.
const m = await browser.newContext({
  viewport: { width: 375, height: 812 },
  isMobile: true,
  hasTouch: true,
});
const mp = await m.newPage();
await mp.goto(`${APP}/`, { waitUntil: "networkidle" });
await mp.getByRole("button", { name: "Open menu" }).click();
await mp.waitForTimeout(300);
await mp.screenshot({ path: "e2e/landing-03-mobile-menu.png", fullPage: true });
console.log("mobile menu links:", await mp.locator('nav[aria-label="Mobile"] a').count());
await m.close();

// Marquee: caption + duplicated wordmark loop, verified in both themes.
await page.getByText("Trusted by growing businesses across Tanzania").scrollIntoViewIfNeeded();
await page.waitForTimeout(500);
console.log(
  "marquee wordmarks:",
  await page.locator('section[aria-label="Trusted by businesses across Tanzania"] span.whitespace-nowrap').count(),
);
await page.evaluate(() => {
  document.documentElement.dataset.theme = "light";
});
await page.waitForTimeout(400);
await page.screenshot({ path: "e2e/landing-04-light-marquee.png", fullPage: false });

console.log("ERRORS:", errors.length ? errors : "none");
await browser.close();
