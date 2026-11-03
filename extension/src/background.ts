import { ENGINE_PORTS, type ApiRequest, type ApiResponse } from "./engine";

let base: string | null = null;

async function findEngine(): Promise<string | null> {
  for (const port of ENGINE_PORTS) {
    const url = `http://127.0.0.1:${port}`;
    try {
      const resp = await fetch(`${url}/api/health`, { signal: AbortSignal.timeout(1500) });
      if (resp.ok) return url;
    } catch {
      // not running on this port
    }
  }
  return null;
}

async function call(req: ApiRequest): Promise<ApiResponse> {
  for (let attempt = 0; attempt < 2; attempt++) {
    base ??= await findEngine();
    if (!base) return { ok: false, offline: true, error: "The BriefLectures app isn't running." };
    try {
      const resp = await fetch(`${base}${req.path}`, {
        method: req.method ?? "GET",
        headers: req.body ? { "Content-Type": "application/json" } : undefined,
        body: req.body ? JSON.stringify(req.body) : undefined,
      });
      const data = await resp.json().catch(() => null);
      if (!resp.ok) return { ok: false, offline: false, error: data?.detail ?? `Request failed (${resp.status})` };
      return { ok: true, data };
    } catch {
      base = null; // the app restarted (maybe on another port): look again once
    }
  }
  return { ok: false, offline: true, error: "The BriefLectures app isn't running." };
}

chrome.runtime.onMessage.addListener((msg: ApiRequest, _sender, reply) => {
  if (msg?.type !== "api") return false;
  call(msg).then(reply);
  return true; // reply asynchronously
});
