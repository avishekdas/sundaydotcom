export interface AppConfig {
  apiBase: string;
  authBase: string;
  wsPath: string;
  stage: string;
  auth?: "cognito" | "dev"; // "dev" only from the local devserver (make dev)
  devToken?: string;
}

export async function loadConfig(): Promise<AppConfig> {
  const r = await fetch("/config.json", { cache: "no-store" });
  if (!r.ok) throw new Error("config.json missing");
  return (await r.json()) as AppConfig;
}
