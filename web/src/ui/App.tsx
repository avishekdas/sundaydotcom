import { useEffect, useState } from "react";
import { Api } from "../api";
import { acceptInvite, AuthError, forgotPassword, refresh, resetPassword, signIn, signOut, type Session } from "../auth";
import { loadConfig, type AppConfig } from "../config";
import { BoardView } from "./BoardView";
import { LeftNav } from "./LeftNav";
import { UsersAdmin } from "./UsersAdmin";

const DEFAULT_BOARD = "10";

export function App() {
  const [cfg, setCfg] = useState<AppConfig | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);
  const [invite, setInvite] = useState<{ email: string; session: string } | null>(null);

  useEffect(() => {
    loadConfig()
      .then(async (c) => {
        setCfg(c);
        if (c.auth === "dev" && c.devToken) setSession({ accessToken: c.devToken, expiresAt: Number.MAX_SAFE_INTEGER });
        else setSession(await refresh());
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBooting(false));
  }, []);

  if (booting) return <div className="center muted">Loading…</div>;
  if (!cfg) return <div className="center error">{error}</div>;
  if (!session && new URLSearchParams(location.search).has("reset")) {
    return <ResetPassword onDone={() => { history.replaceState(null, "", location.pathname); setError("Password changed — sign in with your new password."); setBooting(false); }} />;
  }
  if (!session && invite) {
    return <SetPassword email={invite.email} onSubmit={async (pw) => {
      setSession(await acceptInvite(invite.email, invite.session, pw));
      setInvite(null);
    }} />;
  }
  if (!session) {
    return <SignIn onSubmit={async (email, pw, onRetry) => {
      setError(null);
      try {
        const r = await signIn(email, pw, { onRetry });
        if ("challenge" in r) setInvite({ email, session: r.session });
        else setSession(r);
      } catch (e) { setError((e as Error).message); }
    }} error={error} />;
  }

  let current = session;
  const token = async () => {
    if (Date.now() > current.expiresAt) {
      const s = await refresh();
      if (!s) { setSession(null); throw new Error("Session expired"); }
      current = s;
      setSession(s);
    }
    return current.accessToken;
  };
  return <Shell cfg={cfg} token={token} onSignOut={() => { void signOut(); setSession(null); }} />;
}

function Shell({ cfg, token, onSignOut }: { cfg: AppConfig; token: () => Promise<string>; onSignOut: () => void }) {
  const [api] = useState(() => new Api(cfg, token));
  const [boardId, setBoardId] = useState(() => new URLSearchParams(location.search).get("board") ?? DEFAULT_BOARD);
  const [caps, setCaps] = useState<string[]>([]);
  const [page, setPage] = useState<"board" | "users">(() => (new URLSearchParams(location.search).get("page") === "users" ? "users" : "board"));
  useEffect(() => { api.me().then((m) => setCaps(m.capabilities ?? [])).catch(() => setCaps([])); }, [api]);
  const open = (id: string) => { history.pushState(null, "", `?board=${id}`); setBoardId(id); setPage("board"); };
  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">Tasklane</span>
        <span className="stage">{cfg.stage}</span>
        {caps.includes("manage_account") && (
          <button className="link" data-testid="nav-users" onClick={() => { history.pushState(null, "", "?page=users"); setPage("users"); }}>Users</button>
        )}
        <button className="link" data-testid="sign-out" onClick={onSignOut}>Sign out</button>
      </header>
      <div className="body">
        <LeftNav api={api} canCreateWorkspace={caps.includes("create_workspace")} onOpenBoard={open} currentBoard={boardId} />
        <main className="content">
          {page === "users" ? <UsersAdmin api={api} /> : <BoardView key={boardId} api={api} boardId={boardId} stage={cfg.stage} />}
        </main>
      </div>
    </div>
  );
}

function SignIn({ onSubmit, error }: {
  onSubmit: (e: string, p: string, onRetry: () => void) => Promise<void>;
  error: string | null;
}) {
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [retrying, setRetrying] = useState(false);
  return (
    <form className="signin" onSubmit={async (e) => {
      e.preventDefault(); setBusy(true); setRetrying(false);
      await onSubmit(email, pw, () => setRetrying(true));
      setBusy(false); setRetrying(false);
    }}>
      <h1>Sign in to Tasklane</h1>
      <label>Email<input data-testid="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
      <label>Password<input data-testid="password" type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} required /></label>
      {error && <p className="error" role="alert">{error}</p>}
      {retrying && <p className="muted" role="status">Signing you in…</p>}
      <button data-testid="sign-in" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      <a className="link" data-testid="forgot-link" href="?reset">Forgot password?</a>
    </form>
  );
}

/** K7.3 forgot → emailed code → new password → back to sign-in (all sessions are revoked by the server). */
function ResetPassword({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) {
      const f = e instanceof AuthError ? e.fields : undefined;
      setError(f ? Object.values(f).join(" ") : (e as Error).message);
    } finally { setBusy(false); }
  };
  if (step === "email") {
    return (
      <form className="signin" onSubmit={(e) => { e.preventDefault(); void run(async () => { await forgotPassword(email); setStep("code"); }); }}>
        <h1>Reset your password</h1>
        <label>Email<input data-testid="reset-email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        {error && <p className="error" role="alert">{error}</p>}
        <button data-testid="reset-send" disabled={busy}>Email me a code</button>
        <a className="link" href="/">Back to sign in</a>
      </form>
    );
  }
  return (
    <form className="signin" onSubmit={(e) => { e.preventDefault(); void run(async () => { await resetPassword(email, code, pw); onDone(); }); }}>
      <h1>Check your email</h1>
      <p className="muted">If an account exists for {email}, we sent it a code.</p>
      <label>Code<input data-testid="reset-code" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} required /></label>
      <label>New password<input data-testid="reset-password" type="password" autoComplete="new-password" minLength={12} value={pw} onChange={(e) => setPw(e.target.value)} required /></label>
      {error && <p className="error" role="alert">{error}</p>}
      <button data-testid="reset-submit" disabled={busy}>Set new password</button>
    </form>
  );
}

/** Invitation acceptance (F1.2): the invitee replaces the emailed temporary password. */
function SetPassword({ email, onSubmit }: { email: string; onSubmit: (pw: string) => Promise<void> }) {
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <form className="signin" onSubmit={async (e) => {
      e.preventDefault(); setBusy(true); setError(null);
      try { await onSubmit(pw); } catch (err) {
        const f = err instanceof AuthError ? err.fields : undefined;
        setError(f ? Object.values(f).join(" ") : (err as Error).message);
      } finally { setBusy(false); }
    }}>
      <h1>Welcome to Tasklane</h1>
      <p className="muted">Choose a password for {email}: at least 12 characters with upper and lower case and a digit.</p>
      <label>New password<input data-testid="new-password" type="password" autoComplete="new-password" minLength={12} value={pw} onChange={(e) => setPw(e.target.value)} required /></label>
      {error && <p className="error" role="alert">{error}</p>}
      <button data-testid="set-password" disabled={busy}>Set password</button>
    </form>
  );
}
