import { useCallback, useMemo, useRef, useState, type FormEvent } from "react";
import { analyze } from "./lib/api";
import { buildCut, CUTS, keptDuration, skipRanges, type CutId } from "./lib/cuts";
import { clock, minutes } from "./lib/format";
import type { Analysis } from "./lib/types";
import { CutPicker } from "./components/CutPicker";
import { Player, type PlayerHandle } from "./components/Player";
import { Timeline } from "./components/Timeline";

const RATES = [1, 1.25, 1.5, 1.75, 2];

export default function App() {
  const [url, setUrl] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cut, setCut] = useState<CutId>("no-filler");
  const [target, setTarget] = useState<number | null>(null); // null = pick a default per lecture
  const [rate, setRate] = useState(1);
  const [time, setTime] = useState(0);
  const player = useRef<PlayerHandle>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await analyze(url.trim());
      setAnalysis(result);
      setTarget(null);
      setTime(0);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const segments = useMemo(() => analysis?.segments ?? [], [analysis]);
  const noFiller = useMemo(() => keptDuration(segments, buildCut(segments, "no-filler")), [segments]);
  const customTarget = Math.min(target ?? Math.round((noFiller * 0.6) / 30) * 30, noFiller);
  const durations = useMemo(
    () =>
      Object.fromEntries(
        CUTS.map((c) => [c.id, keptDuration(segments, buildCut(segments, c.id, customTarget))]),
      ) as Record<CutId, number>,
    [segments, customTarget],
  );
  const keep = useMemo(() => buildCut(segments, cut, customTarget), [segments, cut, customTarget]);
  const ranges = useMemo(() => skipRanges(segments, keep), [segments, keep]);
  const onTime = useCallback((t: number) => setTime(t), []);
  const seek = (s: number) => player.current?.seek(s);

  const full = analysis?.duration ?? 0;
  const saved = full - durations[cut];

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="brand-mark" aria-hidden>
            ▸▸
          </span>
          BriefLectures
        </div>
        <form className="url-form" onSubmit={submit}>
          <input
            type="url"
            inputMode="url"
            placeholder="Paste a YouTube lecture link…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            aria-label="YouTube link"
          />
          <button type="submit" disabled={loading}>
            {loading ? "Analyzing…" : "Shorten"}
          </button>
        </form>
      </header>

      {error && <div className="banner error">{error}</div>}

      {!analysis && !loading && (
        <section className="empty">
          <h1>Watch the lecture, skip the rest.</h1>
          <p>
            Paste a YouTube link. We read the transcript, find the filler, the logistics and the parts that repeat, and
            the player jumps past them for you.
          </p>
        </section>
      )}

      {loading && <div className="banner">Reading the transcript and finding what to skip… long lectures take a minute.</div>}

      {analysis && (
        <main className="workspace">
          <div className="stage">
            <Player ref={player} videoId={analysis.video_id} ranges={ranges} rate={rate} onTime={onTime} />
            <Timeline segments={segments} keep={keep} duration={full} time={time} onSeek={seek} />
            <div className="meta">
              <h2>{analysis.title}</h2>
              <div className="stats">
                <span>
                  {minutes(durations[cut])} of {minutes(full)}
                </span>
                {saved > 30 && <span className="saved">saves {minutes(saved)}</span>}
                <span className={`engine engine-${analysis.engine}`}>
                  {analysis.engine === "claude" ? "AI analysis" : "Offline estimate"}
                </span>
                <span className="rates">
                  {RATES.map((r) => (
                    <button key={r} className={r === rate ? "active" : ""} onClick={() => setRate(r)}>
                      {r}×
                    </button>
                  ))}
                </span>
              </div>
              {analysis.summary && <p className="summary">{analysis.summary}</p>}
            </div>
          </div>

          <aside className="side">
            <CutPicker
              value={cut}
              onChange={setCut}
              durations={durations}
              target={customTarget}
              targetMax={noFiller}
              onTarget={setTarget}
            />
            {analysis.chapters.length > 0 && (
              <nav className="chapters" aria-label="Chapters">
                <h3>Chapters</h3>
                {analysis.chapters.map((c) => (
                  <button key={c.start} onClick={() => seek(c.start)} className={time >= c.start ? "passed" : ""}>
                    <span className="ch-time">{clock(c.start)}</span>
                    {c.title}
                  </button>
                ))}
              </nav>
            )}
          </aside>
        </main>
      )}
    </div>
  );
}
