/**
 * Walking-skeleton sign-in straight against Cognito (USER_PASSWORD_AUTH, D-036). M1 replaces this with the
 * auth proxy (/api/auth/*) and required MFA. Tokens live in memory; the refresh token in sessionStorage.
 */
import type { AppConfig } from "./config";

export interface Session {
  accessToken: string;
  expiresAt: number;
  refreshToken?: string;
}

async function cognito(cfg: AppConfig, target: string, body: unknown): Promise<Record<string, any>> {
  const r = await fetch(`https://cognito-idp.${cfg.region}.amazonaws.com/`, {
    method: "POST",
    headers: { "content-type": "application/x-amz-json-1.1", "x-amz-target": `AWSCognitoIdentityProviderService.${target}` },
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.message ?? "Sign-in failed");
  return data;
}

function toSession(res: Record<string, any>, refresh?: string): Session {
  const a = res.AuthenticationResult;
  if (!a) throw new Error(res.ChallengeName ? `Unsupported challenge ${res.ChallengeName}` : "Sign-in failed");
  return { accessToken: a.AccessToken, expiresAt: Date.now() + (a.ExpiresIn - 60) * 1000,
           refreshToken: a.RefreshToken ?? refresh };
}

export async function signIn(cfg: AppConfig, email: string, password: string): Promise<Session> {
  const res = await cognito(cfg, "InitiateAuth", { AuthFlow: "USER_PASSWORD_AUTH", ClientId: cfg.clientId,
                                                  AuthParameters: { USERNAME: email, PASSWORD: password } });
  const s = toSession(res);
  try { if (s.refreshToken) sessionStorage.setItem("tl.rt", s.refreshToken); } catch { /* storage unavailable */ }
  return s;
}

export async function refresh(cfg: AppConfig): Promise<Session | null> {
  let rt: string | null = null;
  try { rt = sessionStorage.getItem("tl.rt"); } catch { return null; }
  if (!rt) return null;
  try {
    return toSession(await cognito(cfg, "InitiateAuth", { AuthFlow: "REFRESH_TOKEN_AUTH", ClientId: cfg.clientId,
                                                          AuthParameters: { REFRESH_TOKEN: rt } }), rt);
  } catch {
    return null;
  }
}

export function signOut(): void {
  try { sessionStorage.removeItem("tl.rt"); } catch { /* ignore */ }
}
