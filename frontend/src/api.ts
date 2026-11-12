export type Role = "admin" | "nurse" | "doctor";

export interface User {
  id: string;
  full_name: string;
  username: string;
  role: Role;
}

let csrfToken = "";
const configuredApiBase = (import.meta.env.VITE_API_BASE_URL ?? "")
  .trim()
  .replace(/\/+$/, "")
  .replace(/\/api\/v1$/i, "");

const apiBaseUrl = configuredApiBase || (import.meta.env.DEV ? "" : window.location.origin);

export function setCsrfToken(token: string) {
  csrfToken = token;
}

export function apiUrl(path: string): string {
  const route = path.startsWith("/") ? path : `/${path}`;
  if (!apiBaseUrl) return route;
  return new URL(route, `${apiBaseUrl}/`).toString();
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(options.method?.toUpperCase() ?? "GET") && csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(apiUrl(path), { ...options, headers, credentials: "include" });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      message = body.detail ?? message;
    } catch {
      // Keep the HTTP status message when the server does not return JSON.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function jsonBody(value: unknown): string {
  return JSON.stringify(value);
}
