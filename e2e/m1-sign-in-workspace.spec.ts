/**
 * Tier B north star — M1 step 1a (contracts/north_star.yaml): the admin signs in through the auth proxy with
 * password + TOTP (MFA required, K7) and creates a workspace (A2).
 * M1 kickoff: written first as an expected failure (test.fail) — it flips when M1 delivers the auth proxy, MFA
 * and workspaces. Credentials come from the test-identity fixtures (PE-17): E2E_ADMIN_EMAIL / _PASSWORD / _TOTP.
 */
import { expect, test } from "@playwright/test";
import { totp } from "./totp";

const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "";
const TOTP_SECRET = process.env.E2E_ADMIN_TOTP ?? "";

test("@ns:1a.sign_in_create_workspace admin signs in with password + TOTP and creates a workspace", async ({ page }) => {
  test.fail(true, "M1 kickoff: auth proxy, MFA and workspaces not delivered yet");
  expect(EMAIL && PASSWORD && TOTP_SECRET, "E2E_ADMIN_* must be set").toBeTruthy();

  await page.goto("/");
  await page.getByTestId("email").fill(EMAIL);
  await page.getByTestId("password").fill(PASSWORD);
  await page.getByTestId("sign-in").click();
  await page.getByTestId("mfa-code").fill(totp(TOTP_SECRET));
  await page.getByTestId("mfa-submit").click();
  await expect(page.getByTestId("left-nav")).toBeVisible({ timeout: 30_000 });

  const name = `NS workspace ${Date.now()}`;
  await page.getByTestId("new-workspace").click();
  await page.getByTestId("workspace-name").fill(name);
  await page.getByTestId("workspace-create").click();
  await expect(page.getByTestId("left-nav").getByText(name)).toBeVisible();
});
