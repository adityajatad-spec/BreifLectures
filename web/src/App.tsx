import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { analyze, forgetLecture, getLibrary } from "./lib/api";
import { buildCut, CUTS, keptDuration, skipRanges, type CutId } from "./lib/cuts";
import { clock, minutes, transcriptLabel } from "./lib/format";
import { load, save } from "./lib/platform";
import type { Analysis, Job, LibraryItem } from "./lib/types";
import { CutPicker } from "./components/CutPicker";
import { Icon, type IconName } from "./components/Icon";
import { Library } from "./components/Library";
import { Player, type PlayerHandle } from "./components/Player";
import { SettingsDialog } from "./components/SettingsDialog";
import { SetupCard } from "./components/SetupCard";
import { Timeline } from "./components/Timeline";

const RATES = [1, 1.25, 1.5, 1.75, 2];
const SAVE_POSITION_EVERY = 5; // seconds of playback

const FEATURES: { icon: IconName; title: string; text: string }[] = [
  { icon: "scissors", title: "Cuts the filler", text: "Silence, logistics, promos and repeats are skipped as you watch." },
  { icon: "globe", title: "Any language", text: "Hindi, Hinglish, Spanish, Japanese… with or without captions." },
  { icon: "lock", title: "Stays on your Mac", text: "A local AI model does the work. No account, no uploads." },
];

function UrlForm({
  value,
  onChange,
  onSubmit,
  loading,
  size,
}: {
  value: string;
  onChange(v: string): void;
  onSubmit(e: FormEvent): void;
  loading: boolean;
  size: "hero" | "bar";
}) {
  return (
    <form className={`command command-${size}`} onSubmit={onSubmit}>
      <Icon name="link" className="command-icon" size={size === "hero" ? 20 : 16} />
      <input
        type="url"
        inputMode="url"
        placeholder={size === "hero" ? "Paste a YouTube lecture link…" : "Paste another lecture link…"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label="YouTube link"
        autoFocus={size === "hero"}
      />
      <button type="submit" className="btn btn-primary" disabled={loading}>
        {loading ? <span className="spinner" aria-hidden /> : <Icon name="sparkles" size={16} />}
        <span>{loading ? "Analyzing" : "Shorten"}</span>
      </button>
    </form>
  );
}

function ProgressCard({ job }: { job: Job | null }) {
  const pct = job && job.total > 0 ? Math.round((job.done / job.total) * 100) : null;
  return (
    <section className="glass progress-card" aria-live="polite">
      <div className="progress-head">
        <span className="pulse-dot" aria-hidden />
        <strong>{job?.step || "Starting…"}</strong>
        {pct !== null && <span className="progress-pct">{pct}%</span>}
      </div>
      <div className={`progress-track ${pct === null ? "indeterminate" : ""}`}>
        <div className="progress-fill" style={{ width: pct === null ? undefined : `${pct}%` }} />
      </div>
      <p className="muted small">
        The AI runs on this computer, so a long lecture takes a few minutes. You only wait once per video.
      </p>
    </section>
  );
}

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
  const allSkips = useMemo(() => skipRanges(segments, keep), [segments, keep]);
  const ranges = autoSkip ? allSkips : [];

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
  const saved = Math.max(0, full - durations[cut]);
  const savedPct = full ? Math.round((saved / full) * 100) : 0;
  // Don't resume into the last few seconds: that just shows the end screen.
  const resumeAt = videoId ? load(`pos:${videoId}`, 0) : 0;
  const startAt = resumeAt < full - 15 ? resumeAt : 0;
  const currentChapter = analysis ? analysis.chapters.filter((c) => c.start <= time).length - 1 : -1;

  return (
    <div className="app">
      <div className="aurora" aria-hidden>
        <span />
        <span />
        <span />
      </div>

      <header className="topbar">
        <button className="brand" onClick={goHome} title="Your lectures">
          <img src="/icon.svg" alt="" width="30" height="30" />
          <span className="wordmark">BriefLectures</span>
        </button>
        {analysis && <UrlForm value={url} onChange={setUrl} onSubmit={submit} loading={loading} size="bar" />}
        <div className="topbar-end">
          <button className="btn btn-icon" onClick={() => setSettingsOpen(true)} aria-label="Settings" title="Settings">
            <Icon name="settings" />
          </button>
        </div>
      </header>

      {error && (
        <div className="alert" role="alert">
          <Icon name="alert" />
          <span>{error}</span>
          <button className="btn btn-icon btn-small" onClick={() => setError(null)} aria-label="Dismiss">
            <Icon name="x" size={16} />
          </button>
        </div>
      )}

      {!analysis && (
        <main className="home">
          <section className="hero">
            <span className="eyebrow">
              <Icon name="sparkles" size={14} /> Local AI · Any language · Private
            </span>
            <h1>
              Watch the lecture.
              <br />
              <span className="gradient-text">Skip the rest.</span>
            </h1>
            <p className="lede">
              Paste a YouTube link. We find the filler, the logistics and the parts that repeat, and the player jumps
              past them for you.
            </p>
            <UrlForm value={url} onChange={setUrl} onSubmit={submit} loading={loading} size="hero" />
          </section>

          {loading && <ProgressCard job={job} />}
          <SetupCard />

          {!library.length && !loading && (
            <section className="features">
              {FEATURES.map((f) => (
                <article key={f.title} className="glass feature">
                  <span className="feature-icon">
                    <Icon name={f.icon} size={20} />
                  </span>
                  <h3>{f.title}</h3>
                  <p>{f.text}</p>
                </article>
              ))}
            </section>
          )}

          <Library items={library} onOpen={(id) => open(id)} onForget={forget} />
        </main>
      )}

      {analysis && (
        <main className="workspace">
          <div className="stage">
            <div className="title-row">
              <button className="btn btn-ghost btn-small" onClick={goHome}>
                <Icon name="arrowLeft" size={16} /> Library
              </button>
              <span className={`chip ${analysis.engine === "ollama" ? "chip-ai" : ""}`}>
                <Icon name={analysis.engine === "ollama" ? "cpu" : "zap"} size={14} />
                {analysis.engine === "ollama" ? "Local AI" : "Offline estimate"}
              </span>
            </div>
            <h2 className="lecture-heading">{analysis.title}</h2>

            {loading && <ProgressCard job={job} />}

            <div className="player-shell">
              <Player
                ref={player}
                videoId={analysis.video_id}
                ranges={ranges}
                rate={rate}
                startAt={startAt}
                onTime={onTime}
              />
            </div>
            <Timeline segments={segments} keep={keep} duration={full} time={time} onSeek={seek} />

            <div className="kpis">
              <div className="glass kpi">
                <span className="kpi-label">
                  <Icon name="clock" size={14} /> Watch time
                </span>
                <strong>{minutes(durations[cut])}</strong>
                <span className="kpi-sub">of {minutes(full)}</span>
              </div>
              <div className="glass kpi kpi-accent">
                <span className="kpi-label">
                  <Icon name="zap" size={14} /> Time saved
                </span>
                <strong>{saved > 30 ? minutes(saved) : "—"}</strong>
                <span className="kpi-sub">{savedPct}% shorter</span>
                <div className="kpi-bar">
                  <span style={{ width: `${savedPct}%` }} />
                </div>
              </div>
              <div className="glass kpi">
                <span className="kpi-label">
                  <Icon name="scissors" size={14} /> Skips
                </span>
                <strong>{allSkips.length}</strong>
                <span className="kpi-sub">{autoSkip ? "auto-skipping" : "auto-skip off"}</span>
              </div>
            </div>

            <div className="glass controls">
              <div className="segmented" role="group" aria-label="Playback speed">
                {RATES.map((r) => (
                  <button key={r} className={r === rate ? "active" : ""} onClick={() => setRate(r)}>
                    {r}×
                  </button>
                ))}
              </div>
              <label className="toggle">
                <input type="checkbox" checked={autoSkip} onChange={(e) => setAutoSkip(e.target.checked)} />
                <span className="toggle-track" aria-hidden>
                  <span className="toggle-thumb" />
                </span>
                Auto-skip
              </label>
              <button className="btn btn-ghost btn-small" disabled={loading} onClick={() => open(analysis.video_id, true)}>
                <Icon name="refresh" size={15} /> Re-analyze
              </button>
            </div>

            {(analysis.summary || analysis.transcript_source) && (
              <section className="glass summary-card">
                <h3>
                  <Icon name="sparkles" size={16} /> Summary
                </h3>
                {analysis.summary && <p>{analysis.summary}</p>}
                {analysis.transcript_source && (
                  <p className="source">
                    <Icon name="mic" size={14} />
                    {transcriptLabel(analysis.transcript_source, analysis.languages ?? [])}
                  </p>
                )}
              </section>
            )}
          </div>

          <aside className="side">
            <CutPicker
              value={cut}
              onChange={setCut}
              durations={durations}
              full={full}
              target={customTarget}
              targetMax={noFiller}
              onTarget={setTarget}
            />
            {analysis.chapters.length > 0 && (
              <nav className="glass chapters" aria-label="Chapters">
                <h3>
                  <Icon name="list" size={16} /> Chapters
                </h3>
                <ol>
                  {analysis.chapters.map((c, i) => (
                    <li key={c.start} className={i === currentChapter ? "current" : i < currentChapter ? "passed" : ""}>
                      <button onClick={() => seek(c.start)}>
                        <span className="ch-time">{clock(c.start)}</span>
                        <span className="ch-title">{c.title}</span>
                      </button>
                    </li>
                  ))}
                </ol>
              </nav>
            )}
          </aside>
        </main>
      )}

      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
