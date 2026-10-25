import type { Analysis, Job } from "./types";

// Empty in dev (Vite proxies /api). The desktop build points this at its bundled backend.
const BASE = import.meta.env.VITE_API_BASE ?? "";
const POLL_MS = 1000;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, init);
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${resp.status})`);
  }
  return resp.json();
}

/** Starts (or joins) an analysis and resolves when it finishes. A local model can take minutes. */
export async function analyze(url: string, onProgress: (job: Job) => void, force = false): Promise<Analysis> {
  let job = await request<Job>("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, force }),
  });
  while (job.status === "queued" || job.status === "running") {
    onProgress(job);
    await new Promise((r) => setTimeout(r, POLL_MS));
    job = await request<Job>(`/api/jobs/${job.id}`);
  }
  if (job.status === "error" || !job.result) throw new Error(job.error ?? "Analysis failed");
  return job.result;
}
