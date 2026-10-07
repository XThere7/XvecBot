/**
 * End-to-end smoke test for the XvecBot dashboard.
 *
 * Drives the real UI in Chromium against the mock backend in ./mock-api.mjs and
 * asserts the mandatory UX rules from frontendbot.md: the training poll, the
 * one-time token modal and its dismissal guard, the grounding warning, the
 * confirmation copy, the in-memory session and the ?redirect= back-link.
 *
 *   node e2e/smoke.mjs [appUrl] [mockPort]
 */
import { chromium } from "playwright-core";
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const APP = process.argv[2] ?? process.env.APP_URL ?? "http://localhost:3113";
const SHOTS = join(here, "shots");
mkdirSync(SHOTS, { recursive: true });

const results = [];
let browser;

function check(name, ok, extra = "") {
  results.push({ name, ok, extra });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? ` — ${extra}` : ""}`);
}

async function shot(page, name) {
  await page.screenshot({ path: join(SHOTS, `${name}.png`), fullPage: true });
}

try {
  browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH ?? "/usr/bin/chromium",
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    permissions: ["clipboard-read", "clipboard-write"],
  });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(`${msg.text()} @ ${JSON.stringify(msg.location())}`);
    }
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));
  page.on("response", (res) => {
    if (res.status() >= 400) consoleErrors.push(`HTTP ${res.status()} ${res.url()}`);
  });

  const email = `owner+${Date.now()}@acme.co.tz`;

  // ---- register ----
  await page.goto(`${APP}/register`, { waitUntil: "networkidle" });
  check(
    "register page renders",
    await page.getByRole("heading", { name: "Create your account" }).isVisible(),
  );
  await shot(page, "01-register");

  await page.getByRole("button", { name: "Create account" }).click();
  check(
    "register validates before sending",
    await page.getByText("Enter your email address.").isVisible(),
  );

  await page.getByLabel("Email address").fill(email);
  await page.getByRole("textbox", { name: "Password" }).fill("short");
  await page.getByText("I understand this dashboard").click();
  await page.getByRole("button", { name: "Create account" }).click();
  check(
    "password minimum length enforced",
    await page.getByText("Use at least 8 characters.").isVisible(),
  );

  await page.getByRole("textbox", { name: "Password" }).fill("supersecret123");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("**/dashboard", { timeout: 15000 });
  check("register redirects to dashboard", page.url().endsWith("/dashboard"));

  // ---- dashboard onboarding ----
  await page.getByRole("heading", { name: "Welcome to XvecBot" }).waitFor({ timeout: 10000 });
  check("onboarding checklist shown for a new account", true);
  check(
    "onboarding shows all three steps",
    (await page.getByText("Create a workspace").count()) > 0 &&
      (await page.getByText("Upload a document").count()) > 0 &&
      (await page.getByText("Create your first agent").count()) > 0,
  );
  const lockedUpload = page.getByRole("button", { name: "Upload document" });
  check("upload step is gated before a workspace exists", await lockedUpload.isDisabled());
  await shot(page, "02-dashboard-onboarding");

  // ---- create workspace ----
  await page.getByRole("link", { name: "Create workspace" }).first().click();
  await page.waitForURL("**/workspaces/new");
  await page.getByLabel("Name").fill("Acme Store");
  await page.getByLabel("Description").fill("Product catalogue and delivery policy.");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await page.waitForURL(/\/workspaces\/[0-9a-f-]+\?tab=documents/, { timeout: 15000 });
  const wsUrl = page.url();
  const wsId = wsUrl.match(/workspaces\/([0-9a-f-]+)/)[1];
  check("workspace created and redirect to documents tab", Boolean(wsId));

  await page.getByText("No documents yet").waitFor({ timeout: 10000 });
  check("documents empty state copy", true);
  await shot(page, "03-documents-empty");

  // ---- upload a document and watch training ----
  writeFileSync(join(here, "catalogue.txt"), "Acme Store catalogue\nShoes: 120000 TZS\n");
  await page.setInputFiles('input[type="file"]', join(here, "catalogue.txt"));
  await page.getByText("Training…").first().waitFor({ timeout: 15000 });
  check("upload auto-trains and shows the processing badge", true);
  await shot(page, "04-documents-processing");

  await page.getByText("12 chunks").first().waitFor({ timeout: 25000 });
  check("training completes and shows the chunk count", true);
  check(
    "a single training-complete toast is shown",
    await page.getByText("Training complete").isVisible(),
  );
  const bodyText = await page.locator("body").innerText();
  check("no fake percentage is rendered", !bodyText.includes("%"));
  await shot(page, "05-documents-ready");

  // ---- agents tab + gate now satisfied ----
  await page.getByRole("link", { name: "Agents" }).first().click();
  await page.waitForURL(/tab=agents/);
  check("agents empty state", (await page.getByText("No agents yet").count()) > 0);
  const newAgent = page.getByRole("link", { name: "New agent" }).first();
  check("New agent is enabled once a document is ready", await newAgent.isEnabled());
  await shot(page, "06-agents-empty");

  await newAgent.click();
  await page.waitForURL("**/agents/new");
  await page.getByLabel("Name").fill("Acme Support");
  await page
    .getByLabel("System prompt")
    .fill("You are Acme Store's support assistant. Answer only from the knowledge base.");
  await page.getByLabel("Welcome message").fill("Hi! Ask me about our products.");
  await page.getByRole("button", { name: "Create agent" }).click();
  await page.waitForURL(/\/agents\/[0-9a-f-]+\?tab=overview/, { timeout: 15000 });
  const agentUrl = page.url();
  const agentId = agentUrl.match(/agents\/([0-9a-f-]+)/)[1];
  check("agent created", Boolean(agentId));

  // ---- overview ----
  await page.getByText("Acme Support").first().waitFor();
  check(
    "overview definition list renders the config",
    (await page.getByText("Temperature").count()) > 0 &&
      (await page.getByText("System prompt").count()) > 0,
  );
  await shot(page, "07-agent-overview");

  // ---- test tab ----
  await page.getByRole("link", { name: "Test" }).click();
  await page.waitForURL(/tab=test/);
  const composer = page.getByPlaceholder("Ask a question about your documents…");
  await composer.waitFor({ timeout: 10000 });
  check(
    "welcome message renders as the first bubble",
    await page.getByText("Hi! Ask me about our products.").isVisible(),
  );
  await composer.fill("What are your prices?");
  await composer.press("Enter");
  await page.getByText("catalogue.txt").first().waitFor({ timeout: 15000 });
  check("grounded answer renders a source chip", true);

  await composer.fill("Do you sell hats?");
  await composer.press("Enter");
  await page.getByText("No sources found").first().waitFor({ timeout: 15000 });
  check("sources: [] renders the grounding warning, not an error", true);
  check(
    "model_used is visible only in the dashboard preview",
    (await page.getByText("llama-3.1-8b-instruct").count()) > 0,
  );
  await shot(page, "08-agent-test");

  // ---- embed tab: one-time token ----
  await page.getByRole("link", { name: "Embed" }).click();
  await page.waitForURL(/tab=embed/);
  await page.getByText("No embed tokens yet").waitFor({ timeout: 10000 });
  check("embed empty state", true);
  await page.getByRole("button", { name: "Create embed token" }).first().click();
  await page.getByLabel("Label").fill("acmestore.co.tz");
  await page.getByRole("button", { name: "Create token" }).click();

  const modal = page.getByRole("dialog");
  await modal.getByText("Copy this token now.").waitFor({ timeout: 15000 });
  check("one-time token modal opens immediately on 201", true);
  const fullToken = (await modal.locator("code").last().innerText()).trim();
  check("full token is shown once, 64 chars", fullToken.length === 64, fullToken.slice(0, 12));
  check(
    "snippet contains the full token",
    (await modal.locator("pre").innerText()).includes(fullToken),
  );
  await shot(page, "09-one-time-token");

  await page.keyboard.press("Escape");
  await page.waitForTimeout(400);
  check(
    "modal cannot be dismissed without copying",
    await page.getByText("This is your last chance to copy the token").isVisible(),
  );
  await shot(page, "10-one-time-token-guarded");

  await modal.getByRole("button", { name: "Copy snippet" }).click();
  await page.getByRole("button", { name: "I've copied it" }).click();
  await page.waitForTimeout(500);
  check(
    "modal closes after acknowledging the copy",
    (await page.getByRole("dialog").count()) === 0,
  );

  const rowText = await page.locator("table").first().innerText();
  check(
    "token list shows a masked token",
    rowText.includes("..."),
    rowText.split("\n").slice(0, 4).join(" | "),
  );
  check("token list never shows the full token", !rowText.includes(fullToken));
  await shot(page, "11-embed-tokens");

  await page.getByRole("button", { name: /Actions for acmestore/ }).click();
  await page.getByRole("menuitem", { name: "Copy snippet" }).click();
  await page.getByText("Embed snippet").first().waitFor({ timeout: 10000 });
  // The token sits inside a highlighted attribute span, so match on the
  // rendered text of the code block rather than an exact element text.
  const snippetText = await page.locator("pre").first().innerText();
  check("copy snippet reveals the full token again", snippetText.includes(fullToken));
  await shot(page, "12-snippet-view");

  await page.getByRole("button", { name: /Actions for acmestore/ }).click();
  await page.getByRole("menuitem", { name: "Revoke token" }).click();
  check(
    "revoke shows the mandated confirmation",
    await page
      .getByText("will stop responding immediately, for every visitor")
      .isVisible(),
  );
  await shot(page, "13-revoke-confirm");
  await page.getByRole("button", { name: "Revoke token" }).last().click();
  await page.getByText("Token revoked").waitFor({ timeout: 10000 });
  check("revoke toggles the row to Inactive", (await page.getByText("Inactive").count()) > 0);

  // ---- conversations ----
  await page.getByRole("link", { name: "Conversations" }).click();
  await page.waitForURL(/tab=conversations/);
  await page.getByText("Do you sell hats?").first().waitFor({ timeout: 10000 });
  check("conversation list renders", true);
  await shot(page, "14-conversations");
  await page
    .getByRole("link", { name: /Do you sell hats|What are your prices/ })
    .first()
    .click();
  await page.waitForURL(/conversations\/[0-9a-f-]+/);
  await page
    .getByText("This is a preview of a stored conversation.")
    .waitFor({ timeout: 10000 });
  check(
    "thread view is read-only",
    (await page.getByPlaceholder("Ask a question").count()) === 0,
  );
  await shot(page, "15-conversation-thread");

  // ---- settings + delete confirmation copy ----
  await page.getByRole("link", { name: "Settings" }).first().click();
  await page.waitForURL(/tab=settings/);
  await page.getByText("Danger zone").waitFor({ timeout: 10000 });
  check(
    "workspace settings has no 'last updated' field (the API has no updated_at)",
    !(await page.locator("body").innerText()).toLowerCase().includes("last updated"),
  );
  await page.getByRole("button", { name: "Delete workspace" }).first().click();
  check(
    "delete workspace copy lists every consequence",
    await page
      .getByText("every document, chunk and embedding, all agents", { exact: false })
      .first()
      .isVisible(),
  );
  await shot(page, "16-delete-workspace");
  await page.keyboard.press("Escape");

  // ---- delete document confirmation copy ----
  // Navigate in-app: a full page reload would wipe the in-memory JWT and
  // sign the user out, which is the specified behaviour.
  await page.getByRole("link", { name: "Documents" }).first().click();
  await page.waitForURL(/tab=documents/);
  await page.getByRole("button", { name: /Actions for catalogue/ }).click();
  await page.getByRole("menuitem", { name: "Delete document" }).click();
  check(
    "delete document copy is the mandated text",
    await page.getByText("and everything extracted from it").isVisible(),
  );
  await shot(page, "17-delete-document");
  await page.keyboard.press("Escape");

  // ---- account + the in-memory session ----
  await page.getByRole("link", { name: "Account" }).first().click();
  await page.waitForURL(/\/account/);
  await page.getByText("Your session lives in memory only").waitFor({ timeout: 10000 });
  check("account page explains the in-memory session", true);
  await shot(page, "18-account");

  await page.goto(`${APP}/dashboard`);
  // A full reload wipes the in-memory JWT, so the guard must send us to /login.
  await page.waitForURL("**/login?redirect=**", { timeout: 15000 });
  check("the session is lost on a hard reload (in-memory token only)", true);
  check("hard reload redirects to /login with ?redirect=", true);
  await shot(page, "19-login-after-reload");

  await page.getByLabel("Email address").fill(email);
  await page.getByRole("textbox", { name: "Password" }).fill("supersecret123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/dashboard", { timeout: 15000 });
  check("login honours ?redirect= back to the dashboard", true);

  // ---- mobile viewport spot checks ----
  const mobile = await browser.newContext({
    viewport: { width: 375, height: 812 },
    isMobile: true,
    hasTouch: true,
  });
  const mPage = await mobile.newPage();
  await mPage.goto(`${APP}/login`, { waitUntil: "networkidle" });
  await shot(mPage, "20-mobile-login");
  const touchTarget = await mPage
    .getByRole("button", { name: "Sign in" })
    .evaluate((el) => el.getBoundingClientRect().height);
  check("mobile touch target is at least 44px", touchTarget >= 44, `${touchTarget}px`);
  await mobile.close();

  const httpErrors = consoleErrors.filter((e) => e.startsWith("HTTP"));
  check(
    "no failed requests",
    httpErrors.length === 0,
    httpErrors.slice(0, 3).join(" / "),
  );
  check(
    "no console errors",
    consoleErrors.length === 0,
    consoleErrors.filter((e) => !e.startsWith("HTTP")).slice(0, 3).join(" / "),
  );
} catch (error) {
  check("test run completed", false, error.message);
} finally {
  await browser?.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
if (failed.length) {
  console.log("Failures:");
  for (const f of failed) console.log(` - ${f.name} ${f.extra}`);
  process.exitCode = 1;
}