/**
 * Tier B north star — M1 step 1a (contracts/north_star.yaml): the admin signs in through the auth proxy with
 * a password (MFA deferred to M9, D-045) and creates a workspace (A2).
 * Written first as an expected failure at M1 kickoff; flipped when the auth proxy and workspaces landed.
 * The workspace it creates is deleted again (soft delete, A2.3) so dev's nav does not fill up. Credentials come from the test-identity fixtures (PE-17, D-049): E2E_ADMIN_EMAIL / _PASSWORD.
 */
import { expect, test } from "@playwright/test";

const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "";

test("@ns:1a.sign_in_create_workspace admin signs in with password and creates a workspace", async ({ page }) => {
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

  // clean up through the same API the SPA uses (the access token lives in memory, so ask the page for it)
  const id = await page.evaluate(async (wsName) => {
    const r = await fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" });
    const { access_token } = await r.json();
    const nav = await (await fetch("/api/v1/nav", { headers: { authorization: `Bearer ${access_token}` } })).json();
    const ws = nav.workspaces.find((w: { name: string }) => w.name === wsName);
    if (ws) await fetch(`/api/v1/workspaces/${ws.id}`, { method: "DELETE", headers: { authorization: `Bearer ${access_token}` } });
    return ws?.id ?? null;
  }, name);
  expect(id).toBeTruthy();
});
