/**
 * Tier B — Admin users page (F1, K1) on the deployed stage: the scripted admin sees the scripted users with their
 * roles; a Member gets no Users entry. Invites themselves are Tier A (test addresses cannot receive mail, D-054).
 */
import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/");
  await page.getByTestId("email").fill(email);
  await page.getByTestId("password").fill(password);
  await page.getByTestId("sign-in").click();
  await expect(page.getByTestId("left-nav")).toBeVisible({ timeout: 30_000 });
}

test("admin sees every scripted user on the Users page", async ({ page }) => {
  await signIn(page, process.env.E2E_ADMIN_EMAIL ?? "", process.env.E2E_ADMIN_PASSWORD ?? "");
  await page.getByTestId("nav-users").click();
  for (const name of ["admin", "member", "viewer", "outsider"]) {
    await expect(page.getByText(`tasklane-test-${name}@example.com`)).toBeVisible();
  }
});

test("a member has no Users entry", async ({ page }) => {
  await signIn(page, process.env.E2E_MEMBER_EMAIL ?? "", process.env.E2E_MEMBER_PASSWORD ?? "");
  await expect(page.getByTestId("nav-users")).toHaveCount(0);
});
