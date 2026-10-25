import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { analyze, forgetLecture, getLibrary } from "./lib/api";
import { buildCut, CUTS, keptDuration, skipRanges, type CutId } from "./lib/cuts";
import { clock, minutes } from "./lib/format";
import { load, save } from "./lib/platform";
import type { Analysis, Job, LibraryItem } from "./lib/types";
import { CutPicker } from "./components/CutPicker";
import { Library } from "./components/Library";
import { Player, type PlayerHandle } from "./components/Player";
import { SettingsDialog } from "./components/SettingsDialog";
import { SetupCard } from "./components/SetupCard";
import { Timeline } from "./components/Timeline";

const RATES = [1, 1.25, 1.5, 1.75, 2];
const SAVE_POSITION_EVERY = 5; // seconds of playback

export default function App() {
  const [url, setUrl] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [library, setLibrary] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cut, setCut] = useState<CutId>(() => load<CutId>("cut", "no-filler"));
  const [target, setTarget] = useState<number | null>(null); // null = pick a default per lecture
  const [rate, setRate] = useState(() => load("rate", 1));
  const [autoSkip, setAutoSkip] = useState(() => load("autoSkip", true));
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [time, setTime] = useState(0);
  const player = useRef<PlayerHandle>(null);
  const lastSaved = useRef(0);

  const refreshLibrary = useCallback(() => {
    getLibrary()
      .then(setLibrary)
      .catch(() => setLibrary([]));
  }, []);
  useEffect(refreshLibrary, [refreshLibrary]);

  useEffect(() => save("cut", cut), [cut]);
  useEffect(() => save("rate", rate), [rate]);
  useEffect(() => save("autoSkip", autoSkip), [autoSkip]);

  const open = async (link: string, force = false) => {
    setLoading(true);
    setJob(null);
    setError(null);
    try {
      const result = await analyze(link, setJob, force);
      setAnalysis(result);
      setTarget(null);
      setTime(0);
      lastSaved.current = 0;
      setUrl("");
      refreshLibrary();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (url.trim()) open(url.trim());
  };

  const goHome = () => {
    setAnalysis(null);
    setError(null);
    refreshLibrary();
  };

  const forget = async (videoId: string) => {
    await forgetLecture(videoId).catch((err: Error) => setError(err.message));
    refreshLibrary();
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
  const ranges = useMemo(() => (autoSkip ? skipRanges(segments, keep) : []), [segments, keep, autoSkip]);

  const videoId = analysis?.video_id;
  const onTime = useCallback(
    (t: number) => {
      setTime(t);
      if (videoId && Math.abs(t - lastSaved.current) >= SAVE_POSITION_EVERY) {
        lastSaved.current = t;
        save(`pos:${videoId}`, t);
      }
    },
    [videoId],
  );
  const seek = (s: number) => player.current?.seek(s);

  const full = analysis?.duration ?? 0;
  const saved = full - durations[cut];
  // Don't resume into the last few seconds: that just shows the end screen.
  const resumeAt = videoId ? load(`pos:${videoId}`, 0) : 0;
  const startAt = resumeAt < full - 15 ? resumeAt : 0;

  return (
    <div className="app">
      <header className="top">
        <button className="brand" onClick={goHome} title="Your lectures">
          <img className="brand-mark" src="/icon.svg" alt="" width="28" height="28" />
          BriefLectures
        </button>
        <form className="url-form" onSubmit={submit}>
          <input
            type="url"
            inputMode="url"
            placeholder="Paste a YouTube lecture link…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            aria-label="YouTube link"
          />
          <button type="submit" className="primary" disabled={loading}>
            {loading ? "Analyzing…" : "Shorten"}
          </button>
        </form>
        <button className="icon-button" onClick={() => setSettingsOpen(true)} aria-label="Settings" title="Settings">
          ⚙
        </button>
      </header>

      {error && (
        <div className="banner error" role="alert">
          {error}
        </div>
      )}

      {loading && (
        <div className="banner progress">
          <span>{job?.step || "Starting…"}</span>
          {job && job.total > 0 && <progress value={job.done} max={job.total} aria-label="Analysis progress" />}
          <small>The AI runs on this computer, so a long lecture takes a few minutes. You only wait once per video.</small>
        </div>
      )}

      {!analysis && (
        <div className="home">
          {!library.length && !loading && (
            <section className="empty">
              <h1>Watch the lecture, skip the rest.</h1>
              <p>
                Paste a YouTube link. We read the transcript, find the filler, the logistics and the parts that repeat,
                and the player jumps past them for you.
              </p>
            </section>
          )}
          <SetupCard />
          <Library items={library} onOpen={(id) => open(id)} onForget={forget} />
        </div>
      )}

      {analysis && (
        <main className="workspace">
          <div className="stage">
            <Player
              ref={player}
              videoId={analysis.video_id}
              ranges={ranges}
              rate={rate}
              startAt={startAt}
              onTime={onTime}
            />
            <Timeline segments={segments} keep={keep} duration={full} time={time} onSeek={seek} />
            <div className="meta">
              <h2>{analysis.title}</h2>
              <div className="stats">
                <span>
                  {minutes(durations[cut])} of {minutes(full)}
                </span>
                {saved > 30 && <span className="saved">saves {minutes(saved)}</span>}
                <span className={`engine engine-${analysis.engine}`}>
                  {analysis.engine === "ollama" ? "Local AI" : "Offline estimate"}
                </span>
                <span className="rates" role="group" aria-label="Playback speed">
                  {RATES.map((r) => (
                    <button key={r} className={r === rate ? "active" : ""} onClick={() => setRate(r)}>
                      {r}×
                    </button>
                  ))}
                </span>
              </div>
              <div className="toolbar">
                <label className="switch">
                  <input type="checkbox" checked={autoSkip} onChange={(e) => setAutoSkip(e.target.checked)} />
                  Auto-skip
                </label>
                <button disabled={loading} onClick={() => open(analysis.video_id, true)}>
                  Re-analyze
                </button>
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

      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
