import { describe, expect, it } from "vitest";
import { buildCut, keptDuration, rangeAt, skipRanges } from "./cuts";
import type { Label, Segment } from "./types";

let nextId = 0;
function seg(start: number, end: number, label: Label, importance: number): Segment {
  return { id: nextId++, start, end, text: "", label, importance, topic: "" };
}

const lecture: Segment[] = [
  seg(0, 30, "admin", 0.1),
  seg(30, 40, "silence", 0),
  seg(40, 100, "core", 0.9),
  seg(100, 160, "example", 0.6),
  seg(160, 170, "filler", 0.05),
  seg(170, 175, "promo", 0),
  seg(175, 235, "core", 0.8),
  seg(235, 265, "repeat", 0.2),
  seg(265, 295, "recap", 0.4),
];

describe("buildCut", () => {
  it("full keeps everything", () => {
    expect(buildCut(lecture, "full").every(Boolean)).toBe(true);
  });

  it("no-filler drops the always-skip labels", () => {
    const keep = buildCut(lecture, "no-filler");
    expect(lecture.filter((_, i) => keep[i]).map((s) => s.label)).toEqual(["core", "example", "core", "recap"]);
  });

  it("key-moments keeps only high-importance core material", () => {
    const keep = buildCut(lecture, "key-moments");
    expect(lecture.filter((_, i) => keep[i]).map((s) => s.importance)).toEqual([0.9, 0.8]);
  });

  it("custom fits the budget by importance", () => {
    const keep = buildCut(lecture, "custom", 130);
    expect(keptDuration(lecture, keep)).toBeLessThanOrEqual(130);
    expect(keep[2] && keep[6]).toBe(true); // the two most important segments survive
  });

  it("custom never brings filler back", () => {
    expect(buildCut(lecture, "custom", 10_000)).toEqual(buildCut(lecture, "no-filler"));
  });
});

describe("skipRanges", () => {
  it("merges adjacent skipped segments", () => {
    const ranges = skipRanges(lecture, buildCut(lecture, "no-filler"));
    expect(ranges.map((r) => [r.start, r.end])).toEqual([
      [0, 40],
      [160, 175],
      [235, 265],
    ]);
    expect(ranges[0].labels).toEqual(["admin", "silence"]);
  });

  it("ignores skips shorter than the minimum", () => {
    const tiny = [seg(0, 10, "core", 1), seg(10, 11, "filler", 0), seg(11, 20, "core", 1)];
    expect(skipRanges(tiny, buildCut(tiny, "no-filler"))).toEqual([]);
  });
});

describe("rangeAt", () => {
  const ranges = [{ start: 10, end: 20, labels: [] as Label[] }];
  it("finds the range under the playhead", () => {
    expect(rangeAt(ranges, 10)).toBe(0);
    expect(rangeAt(ranges, 15)).toBe(0);
  });
  it("does not re-trigger right at the landing point", () => {
    expect(rangeAt(ranges, 19.8)).toBe(-1);
    expect(rangeAt(ranges, 9.9)).toBe(-1);
  });
});
