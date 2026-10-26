/**
 * Sign-in through the auth proxy only (/api/auth/*, arch 07 §7.1, 09 §9.3). The browser never talks to Cognito:
 * the access token lives in memory, the refresh token only in the HttpOnly cookie scoped to /api/auth (D-048).
 * On a generic 401 carrying retry_after_s (a Cognito lock the proxy could not wait out, D-043) the SPA waits and
 * retries once while showing "Signing you in…".
 */
const AUTH_BASE = "/api/auth";

export interface Session {
  accessToken: string;
  expiresAt: number;
}

export class AuthError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryAfterS?: number,
    readonly fields?: Record<string, string>,
  ) {
    super(message);
  }
}

export interface SignInOptions {
  sleep?: (ms: number) => Promise<void>;
  onRetry?: () => void;
}

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

async function post(path: string, body?: unknown): Promise<Response> {
  return fetch(`${AUTH_BASE}${path}`, {
    method: "POST",
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function toSession(r: Response): Promise<Session> {
  const data = await r.json();
  return { accessToken: data.access_token, expiresAt: Date.now() + (Number(data.expires_in) - 60) * 1000 };
}

async function toError(r: Response): Promise<AuthError> {
  const e = (await r.json().catch(() => null))?.error ?? {};
  return new AuthError(r.status, e.code ?? "error", e.message ?? "Sign-in failed", e.retry_after_s, e.fields);
}

export async function signIn(email: string, password: string, opts: SignInOptions = {}): Promise<Session> {
  const sleep = opts.sleep ?? wait;
  for (let attempt = 0; ; attempt++) {
    const r = await post("/sign-in", { email, password });
    if (r.ok) return toSession(r);
    const err = await toError(r);
    if (attempt === 0 && r.status === 401 && err.retryAfterS) {
      opts.onRetry?.();
      await sleep(err.retryAfterS * 1000);
      continue;
    }
    throw err;
  }
}

export async function refresh(): Promise<Session | null> {
  try {
    const r = await post("/refresh");
    return r.ok ? await toSession(r) : null;
  } catch {
    return null;
  }
}

export async function signOut(): Promise<void> {
  try {
    await post("/sign-out");
  } catch {
    /* the cookie expires anyway; the UI signs out locally */
  }
}

/** K7.3: always accepted (SEC-5); Cognito emails a code when the account exists. */
export async function forgotPassword(email: string): Promise<void> {
  const r = await post("/forgot", { email });
  if (!r.ok) throw await toError(r);
}

/** Sets the new password with the emailed code; every existing session is signed out (AC-K7-3). */
export async function resetPassword(email: string, code: string, newPassword: string): Promise<void> {
  const r = await post("/reset", { email, code, new_password: newPassword });
  if (!r.ok) throw await toError(r);
}
