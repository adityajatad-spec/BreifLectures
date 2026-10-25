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
