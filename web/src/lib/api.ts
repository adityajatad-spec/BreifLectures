import type { Analysis, Job, LibraryItem, PullState, Settings, SetupStatus } from "./types";

// Same origin everywhere: Vite proxies /api in dev, and the desktop app's backend serves the UI.
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

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** Starts (or joins) an analysis and resolves when it finishes. A local model can take minutes. */
export async function analyze(url: string, onProgress: (job: Job) => void, force = false): Promise<Analysis> {
  let job = await request<Job>("/api/analyze", json("POST", { url, force }));
  while (job.status === "queued" || job.status === "running") {
    onProgress(job);
    await new Promise((r) => setTimeout(r, POLL_MS));
    job = await request<Job>(`/api/jobs/${job.id}`);
  }
  if (job.status === "error" || !job.result) throw new Error(job.error ?? "Analysis failed");
  return job.result;
}

export const getLibrary = () => request<LibraryItem[]>("/api/library");
export const forgetLecture = (videoId: string) => request<{ ok: boolean }>(`/api/library/${videoId}`, { method: "DELETE" });

export const getSetup = () => request<SetupStatus>("/api/setup");
export const startOllama = () => request<{ ok: boolean }>("/api/setup/start-ollama", { method: "POST" });
export const pullModel = (model: string) => request<PullState>("/api/setup/pull", json("POST", { model }));

export const getSettings = () => request<Settings>("/api/settings");
export const saveSettings = (s: Settings) => request<Settings>("/api/settings", json("PUT", s));
