/**
 * Centralised API client for the Exegol Control Tower backend.
 *
 * All fetch calls MUST use this helper to ensure the X-API-Key header
 * is attached automatically. The key is read from NEXT_PUBLIC_API_KEY
 * (set in workbench_ui/.env.local) and falls back to "dev-local-key".
 */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "dev-local-key";

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
  const url = `${API_BASE}${path}`;
  return fetch(url, {
    ...options,
    headers: buildHeaders(options.headers as HeadersInit),
  });
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
