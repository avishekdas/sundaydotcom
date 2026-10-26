/**
 * Tier B north star — M1 step 1a (contracts/north_star.yaml): the admin signs in through the auth proxy with
 * a password (MFA deferred to M9, D-045) and creates a workspace (A2).
 * M1 kickoff: written first as an expected failure (test.fail) — it flips when M1 delivers the auth proxy
 * and workspaces. Credentials come from the test-identity fixtures (PE-17, D-049): E2E_ADMIN_EMAIL / _PASSWORD.
 */
import { expect, test } from "@playwright/test";

const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "";

test("@ns:1a.sign_in_create_workspace admin signs in with password and creates a workspace", async ({ page }) => {
  test.fail(true, "M1 kickoff: auth proxy and workspaces not delivered yet");
  expect(EMAIL && PASSWORD, "E2E_ADMIN_* must be set").toBeTruthy();

  await page.goto("/");
  await page.getByTestId("email").fill(EMAIL);
  await page.getByTestId("password").fill(PASSWORD);
  await page.getByTestId("sign-in").click();
  await expect(page.getByTestId("left-nav")).toBeVisible({ timeout: 30_000 });

  const name = `NS workspace ${Date.now()}`;
  await page.getByTestId("new-workspace").click();
  await page.getByTestId("workspace-name").fill(name);
  await page.getByTestId("workspace-create").click();
  await expect(page.getByTestId("left-nav").getByText(name)).toBeVisible();
});
