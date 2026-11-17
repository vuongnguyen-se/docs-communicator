/**
 * Runtime configuration.
 *
 * - Deployed build: fetched from /config.json, written by CDK at deploy time.
 *   One build therefore works for any deployment, and no IDs live in source.
 * - `npm run dev`: read from VITE_ variables (frontend/.env.local), mock by default.
 *
 * All values are public identifiers, never secrets.
 */

export type ApiMode = "mock" | "http";

export interface AppConfig {
  mode: ApiMode;
  apiUrl: string;
  region: string;
  userPoolId: string;
  userPoolClientId: string;
}

const HTTP_FIELDS = ["apiUrl", "region", "userPoolId", "userPoolClientId"] as const;

export function parseConfig(raw: unknown): AppConfig {
  const r = (raw ?? {}) as Record<string, unknown>;
  const str = (k: string) => (typeof r[k] === "string" ? (r[k] as string).trim() : "");
  const mode: ApiMode = str("mode") === "http" ? "http" : "mock";
  const config: AppConfig = {
    mode,
    apiUrl: str("apiUrl").replace(/\/+$/, ""),
    region: str("region"),
    userPoolId: str("userPoolId"),
    userPoolClientId: str("userPoolClientId"),
  };
  if (mode === "http") {
    const missing = HTTP_FIELDS.filter((k) => !config[k]);
    if (missing.length) throw new Error(`Configuration is missing: ${missing.join(", ")}`);
    if (!config.apiUrl.startsWith("https://")) throw new Error("apiUrl must use https://");
  }
  return config;
}

export async function loadConfig(): Promise<AppConfig> {
  if (import.meta.env.DEV) {
    const env = import.meta.env;
    return parseConfig({
      mode: env.VITE_API_MODE ?? "mock",
      apiUrl: env.VITE_API_URL,
      region: env.VITE_AWS_REGION,
      userPoolId: env.VITE_USER_POOL_ID,
      userPoolClientId: env.VITE_USER_POOL_CLIENT_ID,
    });
  }
  const res = await fetch("/config.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`Could not load /config.json (HTTP ${res.status})`);
  return parseConfig(await res.json());
}
