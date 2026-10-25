import { useEffect, useState } from "react";
import { getSetup, pullModel, startOllama } from "../lib/api";
import { openExternal } from "../lib/platform";
import type { SetupStatus } from "../lib/types";

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
          BriefLectures runs its AI on your Mac with <strong>Ollama</strong>, a free app. Nothing you watch leaves your
          computer. Install it, open it once, and come back here.
        </p>
        <button className="primary" onClick={() => act(() => openExternal(status.ollama_download_url))}>
          Download Ollama
        </button>
      </>
    );
  } else if (status.ollama === "stopped") {
    body = (
      <>
        <p>Ollama is installed but not running.</p>
        <button className="primary" disabled={busy} onClick={() => act(startOllama)}>
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
        <progress value={pct} max={100} aria-label="Model download progress" />
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
        <button className="primary" disabled={busy} onClick={() => act(() => pullModel(status.model))}>
          Download model
        </button>
      </>
    );
  }

  return (
    <section className="setup card" aria-live="polite">
      <h3>Set up local AI</h3>
      {body}
      {error && <p className="error-text">{error}</p>}
      <p className="hint">Until then, lectures get a rough offline estimate instead.</p>
    </section>
  );
}
