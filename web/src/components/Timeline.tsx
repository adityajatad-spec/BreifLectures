import type { Label, Segment } from "../lib/types";
import { clock } from "../lib/format";

interface Props {
  segments: Segment[];
  keep: boolean[];
  duration: number;
  time: number;
  /** While the AI is still working: how far it has got. Beyond that, labels are provisional. */
  analyzedUntil?: number | null;
  onSeek(seconds: number): void;
}

// Colour families for the timeline and its legend.
const KIND: Record<Label, "core" | "example" | "recap" | "skip"> = {
  core: "core",
  example: "example",
  recap: "recap",
  repeat: "skip",
  tangent: "recap",
  admin: "skip",
  promo: "skip",
  filler: "skip",
  silence: "skip",
};

// One bar per segment, coloured by kind; hatched and dimmed when the current cut skips it.
export function Timeline({ segments, keep, duration, time, analyzedUntil = null, onSeek }: Props) {
  if (!duration) return null;
  return (
    <div className="timeline-wrap">
      <div className="timeline" aria-label="Lecture timeline">
        {segments.map((s, i) => (
          <button
            key={s.id}
            className={`tl-seg kind-${KIND[s.label]} ${keep[i] ? "kept" : "skipped"}`}
            style={{ left: `${(s.start / duration) * 100}%`, width: `${((s.end - s.start) / duration) * 100}%` }}
            title={`${clock(s.start)} · ${s.label}${s.topic ? ` · ${s.topic}` : ""}${keep[i] ? "" : " (skipped)"}`}
            onClick={() => onSeek(s.start)}
          />
        ))}
        {analyzedUntil != null && analyzedUntil < duration && (
          <div
            className="tl-pending"
            style={{ left: `${(analyzedUntil / duration) * 100}%`, right: 0 }}
            title="The AI hasn't reached this part yet"
          />
        )}
        <div className="tl-head" style={{ left: `${Math.min(time / duration, 1) * 100}%` }} />
      </div>
      <div className="timeline-meta">
        <span className="tl-clock">
          {clock(time)} / {clock(duration)}
        </span>
        <span className="legend">
          <span className="kind-core">Core</span>
          <span className="kind-example">Example</span>
          <span className="kind-recap">Recap</span>
          <span className="kind-skip">Skipped</span>
          {analyzedUntil != null && <span className="kind-pending">Analyzing</span>}
        </span>
      </div>
    </div>
  );
}
