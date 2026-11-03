// Talking to the BriefLectures engine that the Mac app runs on this computer.
// Only the background worker calls these: it may reach 127.0.0.1 without CORS limits.

export const ENGINE_PORTS = [47913, 8000]; // the app's port, then `make dev`'s
export const DOWNLOAD_URL = "https://github.com/adityajatad-spec/BreifLectures/releases/latest/download/BriefLectures.dmg";

export interface ApiRequest {
  type: "api";
  path: string;
  method?: "GET" | "POST";
  body?: unknown;
}

export type ApiResponse =
  | { ok: true; data: unknown }
  | { ok: false; offline: boolean; error: string };
