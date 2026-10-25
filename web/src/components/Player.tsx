import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { rangeAt, type SkipRange } from "../lib/cuts";
import { clock } from "../lib/format";
import { loadYouTube, type YTPlayer } from "../lib/youtube";

export interface PlayerHandle {
  seek(seconds: number): void;
}

interface Props {
  videoId: string;
  ranges: SkipRange[];
  rate: number;
  startAt?: number;
  onTime(seconds: number): void;
}

interface Toast {
  range: SkipRange;
  index: number;
}

const POLL_MS = 200;

// Embeds the YouTube player and auto-skips `ranges`. "Undo" on the toast jumps back
// and exempts that range, so a student can always watch what we cut.
export const Player = forwardRef<PlayerHandle, Props>(function Player({ videoId, ranges, rate, startAt = 0, onTime }, ref) {
  const host = useRef<HTMLDivElement>(null);
  const player = useRef<YTPlayer | null>(null);
  const exempt = useRef<Set<number>>(new Set());
  const [toast, setToast] = useState<Toast | null>(null);
  const [error, setError] = useState<string | null>(null);

  useImperativeHandle(ref, () => ({ seek: (s) => player.current?.seekTo(s, true) }), []);

  useEffect(() => {
    let cancelled = false;
    const mount = document.createElement("div");
    host.current!.replaceChildren(mount);
    loadYouTube()
      .then((YT) => {
        if (cancelled) return;
        player.current = new YT.Player(mount, {
          videoId,
          playerVars: {
            rel: 0,
            playsinline: 1,
            start: Math.floor(startAt),
            // The IFrame API talks to us via postMessage; inside the desktop app it must know our origin.
            origin: window.location.origin,
          },
          events: { onReady: () => player.current?.setPlaybackRate(rate) },
        });
      })
      .catch((e: Error) => setError(e.message));
    return () => {
      cancelled = true;
      player.current?.destroy();
      player.current = null;
    };
    // `rate` and `startAt` are deliberately not dependencies: they must not rebuild the player.
  }, [videoId]);

  useEffect(() => {
    player.current?.setPlaybackRate?.(rate);
  }, [rate]);

  // Switching cuts changes which ranges exist; old exemptions no longer mean anything.
  useEffect(() => {
    exempt.current = new Set();
    setToast(null);
  }, [ranges]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const p = player.current;
      if (!p?.getCurrentTime) return;
      const t = p.getCurrentTime();
      onTime(t);
      const i = rangeAt(ranges, t);
      if (i >= 0 && !exempt.current.has(i)) {
        p.seekTo(ranges[i].end, true);
        setToast({ range: ranges[i], index: i });
      }
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [ranges, onTime]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const undo = () => {
    if (!toast) return;
    exempt.current.add(toast.index);
    player.current?.seekTo(toast.range.start, true);
    setToast(null);
  };

  return (
    <div className="player">
      <div className="player-frame" ref={host} />
      {error && <div className="player-error">{error}</div>}
      {toast && (
        <div className="toast" role="status">
          Skipped {clock(toast.range.end - toast.range.start)} of {toast.range.labels.join(" + ")}
          <button onClick={undo}>Watch it</button>
        </div>
      )}
    </div>
  );
});
