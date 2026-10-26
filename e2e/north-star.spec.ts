/**
 * Tier B north star — M0b walking skeleton (plan §3 M0b system test):
 *   two sessions on the same board; A edits a status, B converges;
 *   B is disconnected, misses 10 edits, reconnects and converges.
 * Runs against the deployed dev stage with test user A (credentials from Secrets Manager in CI).
 */
import { expect, test, type Browser, type Page } from "@playwright/test";

const EMAIL = process.env.E2E_EMAIL ?? "";
const PASSWORD = process.env.E2E_PASSWORD ?? "";
const ITEM = "1001";

async function session(browser: Browser): Promise<Page> {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto("/?board=10");
  await page.getByTestId("email").fill(EMAIL);
  await page.getByTestId("password").fill(PASSWORD);
  await page.getByTestId("sign-in").click();
  await expect(page.getByTestId("live")).toHaveClass(/live/, { timeout: 30_000 });
  await expect(page.getByTestId(`row-${ITEM}`)).toBeVisible();
  return page;
}

test.beforeAll(() => {
  expect(EMAIL && PASSWORD, "E2E_EMAIL / E2E_PASSWORD must be set").toBeTruthy();
});

test("@ns:skeleton.converge M0b: A edits a status, B converges; B misses 10 edits while offline and converges", async ({ browser }) => {
  const a = await session(browser);
  const b = await session(browser);

  // 1. A changes the status to a label different from the current one
  const cell = `cell-${ITEM}-status`;
  const current = await a.getByTestId(cell).getAttribute("data-label");
  const target = current === "Done" ? { id: 2, text: "Stuck" } : { id: 1, text: "Done" };
  await a.getByTestId(cell).click();
  await a.getByTestId(`${cell}-opt-${target.id}`).click();
  await expect(a.getByTestId(cell)).toHaveAttribute("data-label", target.text);
  const t0 = Date.now();
  await expect(b.getByTestId(cell)).toHaveAttribute("data-label", target.text, { timeout: 10_000 });
  console.log(`B converged on A's status edit in ${Date.now() - t0} ms`);

  // 2. B goes offline (socket dropped, no reconnect); A makes 10 edits
  await b.evaluate(() => (window as any).__tl.pause());
  const note = `${ITEM}`;
  let last = "";
  for (let k = 1; k <= 10; k++) {
    last = `edit ${k} @ ${Date.now()}`;
    const input = a.getByTestId(`cell-${note}-note`);
    await input.fill(last);
    await input.press("Enter");
    await expect(a.locator(`[data-testid="row-${ITEM}"] .cell.pending`)).toHaveCount(0, { timeout: 10_000 });
  }
  await expect.poll(async () => a.getByTestId(`cell-${note}-note`).inputValue()).toBe(last);
  await expect(b.getByTestId(`cell-${note}-note`)).not.toHaveValue(last);

  // 3. B reconnects → gap sync via /changes → converges to A's state (value and version)
  await b.evaluate(() => (window as any).__tl.resume());
  await expect(b.getByTestId(`cell-${note}-note`)).toHaveValue(last, { timeout: 15_000 });
  const va = await a.getByTestId(`row-${ITEM}`).getAttribute("data-version");
  await expect(b.getByTestId(`row-${ITEM}`)).toHaveAttribute("data-version", va!, { timeout: 15_000 });
});
