import { useEffect, useState } from "react";
import { Api } from "../api";
import { refresh, signIn, signOut, type Session } from "../auth";
import { loadConfig, type AppConfig } from "../config";
import { BoardView } from "./BoardView";

const DEFAULT_BOARD = "10";

export function App() {
  const [cfg, setCfg] = useState<AppConfig | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    loadConfig()
      .then(async (c) => {
        setCfg(c);
        if (c.auth === "dev" && c.devToken) setSession({ accessToken: c.devToken, expiresAt: Number.MAX_SAFE_INTEGER });
        else setSession(await refresh(c));
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBooting(false));
  }, []);

  if (booting) return <div className="center muted">Loading…</div>;
  if (!cfg) return <div className="center error">{error}</div>;
  if (!session) {
    return <SignIn onSubmit={async (email, pw) => {
      setError(null);
      try { setSession(await signIn(cfg, email, pw)); } catch (e) { setError((e as Error).message); }
    }} error={error} />;
  }

  let current = session;
  const token = async () => {
    if (Date.now() > current.expiresAt) {
      const s = await refresh(cfg);
      if (!s) { setSession(null); throw new Error("Session expired"); }
      current = s;
      setSession(s);
    }
    return current.accessToken;
  };
  const api = new Api(cfg, token);
  const boardId = new URLSearchParams(location.search).get("board") ?? DEFAULT_BOARD;
  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">Tasklane</span>
        <span className="stage">{cfg.stage}</span>
        <button className="link" onClick={() => { signOut(); setSession(null); }}>Sign out</button>
      </header>
      <BoardView api={api} boardId={boardId} stage={cfg.stage} />
    </div>
  );
}

function SignIn({ onSubmit, error }: { onSubmit: (e: string, p: string) => Promise<void>; error: string | null }) {
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form className="signin" onSubmit={async (e) => { e.preventDefault(); setBusy(true); await onSubmit(email, pw); setBusy(false); }}>
      <h1>Sign in to Tasklane</h1>
      <label>Email<input data-testid="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
      <label>Password<input data-testid="password" type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} required /></label>
      {error && <p className="error" role="alert">{error}</p>}
      <button data-testid="sign-in" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    </form>
  );
}
