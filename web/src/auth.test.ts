/**
 * SPA sign-in through the auth proxy only (07 §7.1, 09 §9.3, D-043, D-048, D-052): no Cognito calls from the
 * browser, access token in memory only, refresh token only in the HttpOnly cookie (never in web storage).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { acceptInvite, AuthError, forgotPassword, refresh, resetPassword, signIn, signOut } from "./auth";

type Reply = { status: number; body?: unknown; headers?: Record<string, string> };

function mockFetch(...replies: Reply[]) {
  const calls: { url: string; init: RequestInit }[] = [];
  const f = vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    const r = replies.shift() ?? { status: 500 };
    return new Response(r.body === undefined ? null : JSON.stringify(r.body), { status: r.status, headers: r.headers });
  });
  vi.stubGlobal("fetch", f);
  return calls;
}

const ok = { status: 200, body: { access_token: "at-1", expires_in: 1800, token_type: "Bearer" } };
const generic401 = (retry?: number) => ({
  status: 401,
  body: { error: { code: "unauthenticated", message: "Email or password is incorrect", ...(retry ? { retry_after_s: retry } : {}) } },
});

describe("auth via /api/auth", () => {
  beforeEach(() => sessionStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it("signs in through the proxy and keeps the token in memory only", async () => {
    const calls = mockFetch(ok);
    const s = await signIn("raj@example.com", "Correct-Horse-9");
    expect(s.accessToken).toBe("at-1");
    expect(s.expiresAt).toBeGreaterThan(Date.now());
    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe("/api/auth/sign-in");
    expect(calls[0]!.init.method).toBe("POST");
    expect(calls[0]!.init.credentials).toBe("same-origin");
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ email: "raj@example.com", password: "Correct-Horse-9" });
    expect(calls.every((c) => !c.url.includes("cognito"))).toBe(true);
    expect(sessionStorage.length).toBe(0);
  });

  it("retries once after retry_after_s (D-043) and tells the UI", async () => {
    const calls = mockFetch(generic401(2), ok);
    const sleeps: number[] = [];
    const onRetry = vi.fn();
    const s = await signIn("raj@example.com", "pw-pw-pw-pw-1", { sleep: async (ms) => { sleeps.push(ms); }, onRetry });
    expect(s.accessToken).toBe("at-1");
    expect(calls).toHaveLength(2);
    expect(sleeps).toEqual([2000]);
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("gives up after one retry with the generic message", async () => {
    mockFetch(generic401(1), generic401(1));
    await expect(signIn("raj@example.com", "bad", { sleep: async () => {} })).rejects.toMatchObject({
      status: 401, message: "Email or password is incorrect",
    });
  });

  it("does not retry a plain 401 or a 429", async () => {
    let calls = mockFetch(generic401());
    await expect(signIn("a@example.com", "bad", { sleep: async () => {} })).rejects.toBeInstanceOf(AuthError);
    expect(calls).toHaveLength(1);
    calls = mockFetch({ status: 429, body: { error: { code: "rate_limited", message: "Too many attempts; try again later", retry_after_s: 600 } } });
    await expect(signIn("a@example.com", "x", { sleep: async () => {} })).rejects.toMatchObject({ status: 429, retryAfterS: 600 });
    expect(calls).toHaveLength(1);
  });

  it("refreshes from the cookie, or reports no session", async () => {
    let calls = mockFetch(ok);
    expect((await refresh())?.accessToken).toBe("at-1");
    expect(calls[0]!.url).toBe("/api/auth/refresh");
    expect(calls[0]!.init.credentials).toBe("same-origin");
    mockFetch({ status: 401, body: { error: { code: "unauthenticated", message: "Sign in required" } } });
    expect(await refresh()).toBeNull();
    calls = mockFetch({ status: 503 });
    expect(await refresh()).toBeNull();
  });

  it("signs out this browser through the proxy", async () => {
    const calls = mockFetch({ status: 204 });
    await signOut();
    expect(calls[0]!.url).toBe("/api/auth/sign-out");
    expect(calls[0]!.init.method).toBe("POST");
  });

  it("requests a reset code (always accepted)", async () => {
    const calls = mockFetch({ status: 202 });
    await forgotPassword("raj@example.com");
    expect(calls[0]!.url).toBe("/api/auth/forgot");
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ email: "raj@example.com" });
  });

  it("resets the password, surfacing field errors", async () => {
    let calls = mockFetch({ status: 204 });
    await resetPassword("raj@example.com", "123456", "Brand-New-Password-7");
    expect(calls[0]!.url).toBe("/api/auth/reset");
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({
      email: "raj@example.com", code: "123456", new_password: "Brand-New-Password-7",
    });
    calls = mockFetch({ status: 400, body: { error: { code: "validation_error", message: "Invalid request",
                                                       fields: { code: "Invalid or expired code" } } } });
    await expect(resetPassword("raj@example.com", "0", "x")).rejects.toMatchObject({
      status: 400, fields: { code: "Invalid or expired code" },
    });
  });

  it("returns the new-password challenge for an invitee, then accepts the invite (F1.2)", async () => {
    let calls = mockFetch({ status: 200, body: { challenge: "new_password_required", session: "sess-1" } });
    const r = await signIn("new@example.com", "Temp-Password-1");
    expect(r).toEqual({ challenge: "new_password_required", session: "sess-1" });
    calls = mockFetch(ok);
    const s = await acceptInvite("new@example.com", "sess-1", "Brand-New-Password-7");
    expect(s.accessToken).toBe("at-1");
    expect(calls[0]!.url).toBe("/api/auth/accept-invite");
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({
      email: "new@example.com", session: "sess-1", new_password: "Brand-New-Password-7",
    });
  });
});
