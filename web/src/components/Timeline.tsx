import type { Segment } from "../lib/types";
import { clock } from "../lib/format";

interface Props {
  segments: Segment[];
  keep: boolean[];
  duration: number;
  time: number;
  onSeek(seconds: number): void;
}

// One bar per segment: solid if it plays, hatched if the current cut skips it.
export function Timeline({ segments, keep, duration, time, onSeek }: Props) {
  if (!duration) return null;
  return (
    <div className="timeline" aria-label="Lecture timeline">
      {segments.map((s, i) => (
        <button
          key={s.id}
          className={`tl-seg label-${s.label} ${keep[i] ? "kept" : "skipped"}`}
          style={{ left: `${(s.start / duration) * 100}%`, width: `${((s.end - s.start) / duration) * 100}%` }}
          title={`${clock(s.start)} · ${s.label}${s.topic ? ` · ${s.topic}` : ""}${keep[i] ? "" : " (skipped)"}`}
          onClick={() => onSeek(s.start)}
        />
      ))}
      <div className="tl-head" style={{ left: `${Math.min(time / duration, 1) * 100}%` }} />
    </div>
  );
}
