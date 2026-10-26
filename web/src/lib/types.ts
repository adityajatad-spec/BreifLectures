// Mirrors backend/app/models.py.

export type Label =
  | "core"
  | "example"
  | "recap"
  | "repeat"
  | "tangent"
  | "admin"
  | "promo"
  | "filler"
  | "silence";

export interface Segment {
  id: number;
  start: number;
  end: number;
  text: string;
  label: Label;
  importance: number;
  topic: string;
}

export interface Chapter {
  start: number;
  title: string;
}

export interface Analysis {
  video_id: string;
  title: string;
  duration: number;
  engine: "ollama" | "heuristic";
  summary: string;
  segments: Segment[];
  chapters: Chapter[];
  transcript_source: string;
  languages: string[];
}

export interface Job {
  id: string;
  video_id: string;
  status: "queued" | "running" | "done" | "error";
  step: string;
  done: number;
  total: number;
  error: string | null;
  result: Analysis | null;
}

export interface LibraryItem {
  video_id: string;
  title: string;
  duration: number;
  engine: "ollama" | "heuristic";
  analyzed_at: string;
}

export interface PullState {
  model: string;
  status: "idle" | "running" | "done" | "error";
  detail: string;
  completed: number;
  total: number;
  error: string | null;
}

export interface RecommendedModel {
  name: string;
  download_gb: number;
  ram_gb: number;
  note: string;
}

export interface SpeechModel {
  name: string;
  download_mb: number;
  ram_gb: number;
  note: string;
}

export interface SetupStatus {
  engine: "ollama" | "heuristic";
  detail: string;
  model_ready: boolean;
  ollama: "running" | "stopped" | "missing";
  ollama_download_url: string;
  model: string;
  pulled: string[];
  recommended: RecommendedModel[];
  speech_models: SpeechModel[];
  pull: PullState;
}

export interface Settings {
  model: string;
  think: boolean;
  whisper_model: string;
  output_language: string; // a language name, or "auto" for the lecture's own language
}
