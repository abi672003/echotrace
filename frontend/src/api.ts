// API_BASE is build-time configurable (Docker/production points this at the
// real backend origin) instead of hardcoded to localhost.
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8010";

const TOKEN_KEY = "echotrace_token";
const TOKEN_EXPIRY_KEY = "echotrace_token_expiry";
const USERNAME_KEY = "echotrace_username";

// Token lives in sessionStorage (not localStorage) — cleared when the tab
// closes, to limit how long a stolen token via XSS stays useful.
export function saveSession(token: string, username: string) {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(USERNAME_KEY, username);
  // JWT_SECRET-signed tokens are issued with a 24h expiry server-side
  // (see auth/security.py); mirror that so the client can proactively
  // redirect to /login instead of waiting for a 401.
  sessionStorage.setItem(TOKEN_EXPIRY_KEY, String(Date.now() + 24 * 60 * 60 * 1000));
}

export function clearSession() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TOKEN_EXPIRY_KEY);
  sessionStorage.removeItem(USERNAME_KEY);
}

export function getToken(): string | null {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const expiry = Number(sessionStorage.getItem(TOKEN_EXPIRY_KEY) ?? 0);
  if (!token || Date.now() > expiry) {
    clearSession();
    return null;
  }
  return token;
}

export function getUsername(): string | null {
  return sessionStorage.getItem(USERNAME_KEY);
}

export function isLoggedIn(): boolean {
  return getToken() !== null;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) return body.detail.map((d: { msg?: string }) => d.msg).join("; ");
  } catch {
    // fall through
  }
  return `${res.status} ${res.statusText}`;
}

async function apiGet<T>(path: string, params: Record<string, string | number> = {}): Promise<T> {
  const qs = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();
  const res = await fetch(`${API_BASE}${path}${qs ? `?${qs}` : ""}`, { headers: { ...authHeaders() } });
  if (res.status === 401) {
    clearSession();
  }
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return res.json();
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (res.status === 401) {
    clearSession();
  }
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return res.json();
}

// --- Auth --------------------------------------------------------------

export interface TokenResponse {
  access_token: string;
  token_type: string;
  username: string;
}

export async function register(username: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return res.json();
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return res.json();
}

// --- Investigate ---------------------------------------------------------

export interface Evidence {
  id: string;
  similarity: number;
  score: number | null;
  title?: string | null;
  domain?: string | null;
}

export interface InvestigateResult {
  model_available: boolean;
  message?: string;
  aggregated_score?: number;
  single_instance_score?: number;
  verdict?: string | null;
  evidence: Evidence[];
}

export type Timespan = "24h" | "7d" | "30d";

interface InvestigateArgs {
  text?: string;
  url?: string;
  k?: number;
  timespan?: Timespan;
}

export function investigate(args: InvestigateArgs): Promise<InvestigateResult> {
  return apiPost<InvestigateResult>("/api/investigate", { k: 5, timespan: "7d", ...args });
}

export interface ProgressEvent {
  stage: "searching" | "scoring" | "aggregating";
  message: string;
  count?: number;
}

/** Consumes the SSE investigate stream, calling `onProgress` for each
 * intermediate stage and resolving with the final result. Uses a manual
 * `fetch` + ReadableStream reader (not the native EventSource API) because
 * EventSource cannot send an Authorization header or a POST body. */
export async function investigateStream(
  args: InvestigateArgs,
  onProgress: (event: ProgressEvent) => void
): Promise<InvestigateResult> {
  const res = await fetch(`${API_BASE}/api/investigate/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ k: 5, timespan: "7d", ...args }),
  });
  if (res.status === 401) clearSession();
  if (!res.ok || !res.body) throw new ApiError(res.status, await parseErrorDetail(res));

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sepIndex: number;
    while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, sepIndex);
      buffer = buffer.slice(sepIndex + 2);

      const eventLine = rawEvent.split("\n").find((l) => l.startsWith("event: "));
      const dataLine = rawEvent.split("\n").find((l) => l.startsWith("data: "));
      if (!eventLine || !dataLine) continue;

      const eventName = eventLine.slice("event: ".length).trim();
      const data = JSON.parse(dataLine.slice("data: ".length));

      if (eventName === "progress") {
        onProgress(data as ProgressEvent);
      } else if (eventName === "done") {
        return data as InvestigateResult;
      } else if (eventName === "error") {
        throw new ApiError(500, data.message ?? "Investigation failed.");
      }
    }
  }
  throw new ApiError(500, "Stream ended without a result.");
}

// --- History ---------------------------------------------------------

export interface InvestigationSummary {
  id: number;
  target_url: string | null;
  target_text_preview: string;
  verdict: string | null;
  aggregated_score: number | null;
  single_instance_score: number | null;
  evidence: Evidence[];
  created_at: string;
}

export function fetchInvestigations(limit = 20): Promise<InvestigationSummary[]> {
  return apiGet<InvestigationSummary[]>("/api/investigations", { limit });
}

// --- Detector Sandbox (labeled demo data) ---------------------------------

export interface SampleArticle {
  id: string;
  preview: string;
  cluster_id?: number;
  label?: string;
}

export interface Article {
  id: string;
  text: string;
  cluster_id: number | null;
  source: string;
}

export function fetchSampleArticles(limit = 12): Promise<SampleArticle[]> {
  return apiGet<SampleArticle[]>("/api/articles/sample", { limit });
}

export function fetchMdaigtSamples(limit = 15, split = "test"): Promise<SampleArticle[]> {
  return apiGet<SampleArticle[]>("/api/mdaigt/sample", { limit, split });
}

export function fetchArticle(id: string): Promise<Article> {
  return apiGet<Article>(`/api/articles/${encodeURIComponent(id)}`);
}

export interface DetectResult {
  model_available: boolean;
  score?: number;
  message?: string;
}

export function detect(text: string): Promise<DetectResult> {
  return apiPost<DetectResult>("/api/detect", { text });
}

export { ApiError };
