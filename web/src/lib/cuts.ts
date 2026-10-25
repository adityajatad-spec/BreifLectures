// A "cut" is a policy that decides, per segment, whether the player plays or skips it.
// Cuts live on the client so switching between them (or dragging the custom-length
// slider) is instant and needs no new analysis.

import type { Label, Segment } from "./types";

export type CutId = "full" | "no-filler" | "key-moments" | "custom";

export interface CutDef {
  id: CutId;
  name: string;
  blurb: string;
}

export const CUTS: CutDef[] = [
  { id: "full", name: "Full lecture", blurb: "Everything, untouched" },
  { id: "no-filler", name: "Cut the filler", blurb: "Skips silence, logistics, promos and repeats" },
  { id: "key-moments", name: "Key moments", blurb: "Only the most important explanations" },
  { id: "custom", name: "Custom length", blurb: "Pick a target length; we keep what matters most" },
];

const ALWAYS_SKIP: ReadonlySet<Label> = new Set(["silence", "filler", "admin", "promo", "repeat"]);
const KEY_LABELS: ReadonlySet<Label> = new Set(["core", "example"]);
const KEY_THRESHOLD = 0.7;

export interface SkipRange {
  start: number;
  end: number;
  labels: Label[];
}

const length = (s: Segment) => s.end - s.start;

export function keptDuration(segments: Segment[], keep: boolean[]): number {
  return segments.reduce((sum, s, i) => sum + (keep[i] ? length(s) : 0), 0);
}

/** Keep the highest-importance segments (from `pool`) until `budget` seconds are used. */
function keepByImportance(segments: Segment[], pool: boolean[], budget: number): boolean[] {
  const keep = segments.map(() => false);
  const ranked = segments
    .map((s, i) => ({ s, i }))
    .filter(({ i }) => pool[i])
    .sort((a, b) => b.s.importance - a.s.importance || a.s.start - b.s.start);
  let used = 0;
  for (const { s, i } of ranked) {
    if (used + length(s) > budget && used > 0) continue;
    keep[i] = true;
    used += length(s);
  }
  return keep;
}

export function buildCut(segments: Segment[], id: CutId, targetSeconds?: number): boolean[] {
  const noFiller = segments.map((s) => !ALWAYS_SKIP.has(s.label));
  switch (id) {
    case "full":
      return segments.map(() => true);
    case "no-filler":
      return noFiller;
    case "key-moments": {
      const keep = segments.map((s) => KEY_LABELS.has(s.label) && s.importance >= KEY_THRESHOLD);
      // A lecture where nothing clears the bar still deserves a highlight reel.
      const total = keptDuration(segments, noFiller);
      if (keptDuration(segments, keep) < total * 0.1) return keepByImportance(segments, noFiller, total * 0.25);
      return keep;
    }
    case "custom": {
      const budget = targetSeconds ?? keptDuration(segments, noFiller);
      if (budget >= keptDuration(segments, noFiller)) return noFiller;
      return keepByImportance(segments, noFiller, budget);
    }
  }
}

/** Merge consecutive skipped segments into ranges; ignore skips too short to be worth a seek. */
export function skipRanges(segments: Segment[], keep: boolean[], minSkip = 2): SkipRange[] {
  const ranges: SkipRange[] = [];
  let current: SkipRange | null = null;
  segments.forEach((s, i) => {
    if (keep[i]) {
      current = null;
      return;
    }
    if (current && Math.abs(current.end - s.start) < 0.01) {
      current.end = s.end;
      if (!current.labels.includes(s.label)) current.labels.push(s.label);
    } else {
      current = { start: s.start, end: s.end, labels: [s.label] };
      ranges.push(current);
    }
  });
  return ranges.filter((r) => r.end - r.start >= minSkip);
}

/** The range the playhead is inside, if any. The tail margin stops us re-seeking after landing. */
export function rangeAt(ranges: SkipRange[], t: number, tail = 0.3): number {
  return ranges.findIndex((r) => t >= r.start && t < r.end - tail);
}
