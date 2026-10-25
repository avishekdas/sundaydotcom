export interface AppConfig {
  region: string;
  userPoolId: string;
  clientId: string;
  apiBase: string;
  wsPath: string;
  stage: string;
}

export async function loadConfig(): Promise<AppConfig> {
  const r = await fetch("/config.json", { cache: "no-store" });
  if (!r.ok) throw new Error("config.json missing");
  return (await r.json()) as AppConfig;
}
