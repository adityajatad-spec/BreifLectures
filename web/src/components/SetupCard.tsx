import { useEffect, useState } from "react";
import { getSetup, pullModel, startOllama } from "../lib/api";
import { openExternal } from "../lib/platform";
import type { SetupStatus } from "../lib/types";
import { Icon } from "./Icon";

const POLL_MS = 2000;

function gb(bytes: number): string {
  return `${(bytes / 1e9).toFixed(1)} GB`;
}

/**
 * Walks the user from "nothing installed" to "local AI ready": install Ollama, start it,
 * download the model. Polls while anything is pending, and disappears once ready.
 */
export function SetupCard({ onReady }: { onReady?: () => void }) {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer = 0;
    const tick = async () => {
      try {
        const next = await getSetup();
        if (cancelled) return;
        setStatus(next);
        if (next.model_ready) {
          onReady?.();
          return; // nothing left to watch
        }
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      }
      if (!cancelled) timer = window.setTimeout(tick, POLL_MS);
    };
    tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [onReady]);

  if (!status || status.model_ready) return null;

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const rec = status.recommended.find((m) => m.name === status.model);
  const pull = status.pull;
  const pulling = pull.status === "running" && pull.model === status.model;

  let body;
  if (status.ollama === "missing") {
    body = (
      <>
        <p>
          BriefLectures runs its AI on this computer with <strong>Ollama</strong>, a free app. Nothing you watch leaves your
          computer. Install it, open it once, and come back here.
        </p>
        <button className="btn btn-primary" onClick={() => act(() => openExternal(status.ollama_download_url))}>
          Download Ollama
        </button>
      </>
    );
  } else if (status.ollama === "stopped") {
    body = (
      <>
        <p>Ollama is installed but not running.</p>
        <button className="btn btn-primary" disabled={busy} onClick={() => act(startOllama)}>
          Start Ollama
        </button>
      </>
    );
  } else if (pulling) {
    const pct = pull.total ? Math.floor((pull.completed / pull.total) * 100) : 0;
    body = (
      <>
        <p>
          Downloading <strong>{status.model}</strong>… {pull.total ? `${gb(pull.completed)} of ${gb(pull.total)}` : pull.detail}
        </p>
        <div className="progress-track" role="progressbar" aria-valuenow={pct} aria-label="Model download progress">
          <div className="progress-fill" style={{ width: `${pct}%` }} />
        </div>
      </>
    );
  } else {
    body = (
      <>
        <p>
          One more step: download the AI model <strong>{status.model}</strong>
          {rec && (
            <>
              {" "}
              ({rec.download_gb} GB, uses about {rec.ram_gb} GB of memory while analyzing)
            </>
          )}
          .
        </p>
        {pull.status === "error" && pull.model === status.model && <p className="error-text">{pull.error}</p>}
        <button className="btn btn-primary" disabled={busy} onClick={() => act(() => pullModel(status.model))}>
          Download model
        </button>
      </>
    );
  }

  // 1 install → 2 start → 3 download; `stage` is the step in progress.
  const stage = status.ollama === "missing" ? 0 : status.ollama === "stopped" ? 1 : 2;
  const steps = ["Install Ollama", "Start Ollama", "Download the model"];

  return (
    <section className="glass setup" aria-live="polite">
      <div className="setup-head">
        <span className="feature-icon">
          <Icon name="cpu" size={20} />
        </span>
        <div>
          <h3>Set up local AI</h3>
          <p className="muted small">Until then, lectures get a rough offline estimate instead.</p>
        </div>
      </div>
      <ol className="stepper">
        {steps.map((label, i) => (
          <li key={label} className={i < stage ? "done" : i === stage ? "now" : ""}>
            <span className="step-dot">{i < stage ? <Icon name="check" size={13} /> : i + 1}</span>
            {label}
          </li>
        ))}
      </ol>
      <div className="setup-body">{body}</div>
      {error && <p className="error-text">{error}</p>}
    </section>
  );
}
