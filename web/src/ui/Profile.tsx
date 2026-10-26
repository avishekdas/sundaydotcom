/** Profile (A16): name, title, phone, timezone; a blank timezone uses the account default. */
import { useEffect, useState } from "react";

export interface Me {
  id: string;
  email: string;
  name: string;
  title: string | null;
  phone: string | null;
  timezone: string | null;
  effective_timezone: string;
  role: string;
  capabilities: string[];
}

export interface ProfileApi {
  me(): Promise<Me>;
  updateMe(patch: Partial<Me>): Promise<Me>;
}

export function Profile({ api, onSaved }: { api: ProfileApi; onSaved?: (me: Me) => void }) {
  const [saved, setSaved] = useState<Me | null>(null);
  const [draft, setDraft] = useState({ name: "", title: "", phone: "", timezone: "" });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    api.me().then((m) => {
      setSaved(m);
      setDraft({ name: m.name, title: m.title ?? "", phone: m.phone ?? "", timezone: m.timezone ?? "" });
    }).catch((e: Error) => setError(e.message));
  }, [api]);

  if (!saved) return <section className="admin">{error ?? "Loading…"}</section>;
  const save = async () => {
    setError(null); setNotice(null);
    const patch: Partial<Me> = {};
    if (draft.name !== saved.name) patch.name = draft.name;
    for (const k of ["title", "phone", "timezone"] as const) {
      const v = draft[k].trim() || null;
      if (v !== saved[k]) Object.assign(patch, { [k]: v });
    }
    if (Object.keys(patch).length === 0) { setNotice("Nothing to save."); return; }
    try { const m = await api.updateMe(patch); setSaved(m); setNotice("Saved."); onSaved?.(m); }
    catch (e) { setError((e as Error).message); }
  };
  return (
    <section className="admin">
      <h1>Your profile</h1>
      <form className="settings" onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <p className="muted">{saved.email} · {saved.role}</p>
        <label>Name<input data-testid="profile-name" maxLength={80} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
        <label>Title<input data-testid="profile-title" maxLength={100} value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></label>
        <label>Phone<input data-testid="profile-phone" maxLength={40} value={draft.phone} onChange={(e) => setDraft({ ...draft, phone: e.target.value })} /></label>
        <label>Timezone (blank = account default, now {saved.effective_timezone})
          <input data-testid="profile-timezone" placeholder="Asia/Kolkata" value={draft.timezone} onChange={(e) => setDraft({ ...draft, timezone: e.target.value })} />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        {notice && <p className="muted" role="status">{notice}</p>}
        <button data-testid="profile-save">Save</button>
      </form>
    </section>
  );
}
