/**
 * Tier B — auth proxy on the deployed stage (07 §7.1, D-046…D-052): CloudFront forwards the viewer address and the
 * origin secret, the api λ calls real Cognito, and the refresh token lands in an HttpOnly cookie.
 * The lockout check uses a fresh unknown email per run (unknown emails are counted exactly like real ones, SEC-5),
 * so it never locks a test user and repeated runs do not collide.
 */
import { expect, test } from "@playwright/test";

const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "";

test("auth proxy: admin signs in through CloudFront; refresh cookie is HttpOnly, scoped and refreshes", async ({ request }) => {
  expect(EMAIL && PASSWORD, "E2E_ADMIN_* must be set").toBeTruthy();
  const res = await request.post("/api/auth/sign-in", { data: { email: EMAIL, password: PASSWORD } });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.access_token).toBeTruthy();
  expect(body.refresh_token).toBeUndefined();
  const cookie = res.headers()["set-cookie"] ?? "";
  for (const attr of ["tl_rt=", "HttpOnly", "Secure", "SameSite=Strict", "Path=/api/auth"]) expect(cookie).toContain(attr);
  const refreshed = await request.post("/api/auth/refresh");
  expect(refreshed.status()).toBe(200);
  expect((await refreshed.json()).access_token).toBeTruthy();
  const out = await request.post("/api/auth/sign-out");
  expect(out.status()).toBe(204);
  expect((await request.post("/api/auth/refresh")).status()).toBe(401);
});

test("@ac:AC-K7-2 IP A: the 6th attempt within 15 min is refused (429) without reaching Cognito", async ({ request }) => {
  const ghost = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  for (let i = 0; i < 5; i++) {
    const r = await request.post("/api/auth/sign-in", { data: { email: ghost, password: "Wrong-password-123" } });
    expect(r.status()).toBe(401);
  }
  const sixth = await request.post("/api/auth/sign-in", { data: { email: ghost, password: "Wrong-password-123" } });
  expect(sixth.status()).toBe(429);
  expect(Number(sixth.headers()["retry-after"])).toBeGreaterThan(0);
});

test("forgot password answers 202 for an unknown email (no email sent; reset code path is Tier A, D-053)", async ({ request }) => {
  const ghost = `e2e-forgot-${Date.now()}@example.com`;
  const res = await request.post("/api/auth/forgot", { data: { email: ghost } });
  expect(res.status()).toBe(202);
});
