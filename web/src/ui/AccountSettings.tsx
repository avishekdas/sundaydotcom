/** Admin "Account settings" (A1.2): sends only the fields that changed; the server validates and audits them. */
import { useEffect, useState } from "react";

export interface Settings {
  name: string;
  timezone: string;
  date_format: "DD/MM/YYYY" | "MM/DD/YYYY" | "YYYY-MM-DD";
  week_start: "Sun" | "Mon";
  allowed_domains: string[];
}

export interface AccountApi {
  getSettings(): Promise<Settings>;
  saveSettings(patch: Partial<Settings>): Promise<Settings>;
}

const FORMATS: Settings["date_format"][] = ["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"];

export function AccountSettings({ api, onSaved }: { api: AccountApi; onSaved: (s: Settings) => void }) {
  const [saved, setSaved] = useState<Settings | null>(null);
  const [draft, setDraft] = useState<Settings | null>(null);
  const [domains, setDomains] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings()
      .then((s) => { setSaved(s); setDraft(s); setDomains(s.allowed_domains.join(", ")); })
      .catch((e: Error) => setError(e.message));
  }, [api]);

  if (!draft || !saved) return <section className="admin">{error ? <p className="error" role="alert">{error}</p> : "Loading…"}</section>;

  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setDraft({ ...draft, [k]: v });
  const save = async () => {
    setError(null); setNotice(null);
    const list = domains.split(",").map((d) => d.trim()).filter(Boolean);
    const patch: Partial<Settings> = {};
    for (const k of ["name", "timezone", "date_format", "week_start"] as const) {
      if (draft[k] !== saved[k]) Object.assign(patch, { [k]: draft[k] });
    }
    if (list.join(",") !== saved.allowed_domains.join(",")) patch.allowed_domains = list;
    if (Object.keys(patch).length === 0) { setNotice("Nothing to save."); return; }
    try {
      const s = await api.saveSettings(patch);
      setSaved(s); setDraft(s); setDomains(s.allowed_domains.join(", ")); setNotice("Saved."); onSaved(s);
    } catch (e) { setError((e as Error).message); }
  };

  return (
    <section className="admin">
      <h1>Account settings</h1>
      <form className="settings" onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <label>Account name<input data-testid="account-name" maxLength={80} value={draft.name} onChange={(e) => set("name", e.target.value)} /></label>
        <label>Default timezone<input data-testid="account-timezone" placeholder="America/New_York" value={draft.timezone} onChange={(e) => set("timezone", e.target.value)} /></label>
        <label>Date format
          <select data-testid="account-date-format" value={draft.date_format} onChange={(e) => set("date_format", e.target.value as Settings["date_format"])}>
            {FORMATS.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </label>
        <label>Week starts on
          <select data-testid="account-week-start" value={draft.week_start} onChange={(e) => set("week_start", e.target.value as Settings["week_start"])}>
            <option value="Mon">Monday</option><option value="Sun">Sunday</option>
          </select>
        </label>
        <label>Allowed invite domains (comma separated; empty = any)
          <input data-testid="account-domains" placeholder="acme.com" value={domains} onChange={(e) => setDomains(e.target.value)} />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        {notice && <p className="muted" role="status">{notice}</p>}
        <button data-testid="account-save">Save</button>
      </form>
    </section>
  );
}
