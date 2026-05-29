/**
 * Centralised API client for the Exegol Control Tower backend.
 *
 * All fetch calls MUST use this helper to ensure the X-API-Key header
 * is attached automatically. The key is read from NEXT_PUBLIC_API_KEY
 * (set in workbench_ui/.env.local) and falls back to "dev-local-key".
 */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "dev-local-key";
const REQUEST_TIMEOUT_MS = 8000;

function buildHeaders(extra: HeadersInit = {}): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,
    ...extra,
  };
}

export async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const headers = buildHeaders(options.headers as HeadersInit);
  const urls = localLoopbackUrls(path);
  let lastError: unknown = null;

  for (const url of urls) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(url, {
        ...options,
        headers,
        signal: controller.signal,
      });
      if (response.ok || !shouldRetryLocalLoopback(response.status, url, urls)) {
        return response;
      }
      lastError = new Error(`${response.status} ${response.statusText}`);
    } catch (error) {
      lastError = error;
      if (!shouldRetryLocalLoopback(null, url, urls)) {
        throw error;
      }
    } finally {
      window.clearTimeout(timeout);
    }
  }

  throw lastError instanceof Error ? lastError : new Error("API request failed");
}

function localLoopbackUrls(path: string): string[] {
  const primary = `${API_BASE}${path}`;
  try {
    const url = new URL(primary);
    const alternateHostname = url.hostname === "127.0.0.1"
      ? "localhost"
      : url.hostname === "localhost"
        ? "127.0.0.1"
        : null;
    if (!alternateHostname) return [primary];

    url.hostname = alternateHostname;
    return [primary, url.toString()];
  } catch {
    return [primary];
  }
}

function shouldRetryLocalLoopback(status: number | null, url: string, urls: string[]): boolean {
  if (urls.length < 2 || url !== urls[0]) return false;
  return status === null || status === 0 || status === 403 || status >= 500;
}


export async function apiGet<T = unknown>(path: string): Promise<T> {
  const res = await apiFetch(path);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export async function apiPost<T = unknown>(
  path: string,
  body: unknown
): Promise<T> {
  const res = await apiFetch(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export function getLocalActiveRepo(): string {
  if (typeof window !== "undefined") {
    return localStorage.getItem("exegol_repo_path") || process.env.NEXT_PUBLIC_REPO_PATH || "";
  }
  return process.env.NEXT_PUBLIC_REPO_PATH || "";
}

export function setLocalActiveRepo(path: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem("exegol_repo_path", path);
  }
}
