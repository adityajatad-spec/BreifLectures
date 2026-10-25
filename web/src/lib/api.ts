import type { Analysis } from "./types";

// Empty in dev (Vite proxies /api). The desktop build points this at its bundled backend.
const BASE = import.meta.env.VITE_API_BASE ?? "";

export async function analyze(url: string, force = false): Promise<Analysis> {
  const resp = await fetch(`${BASE}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, force }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail ?? `Analysis failed (${resp.status})`);
  }
  return resp.json();
}
