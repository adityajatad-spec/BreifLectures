import { useEffect, useRef, useState, type FormEvent } from "react";
import { getSettings, getSetup, saveSettings } from "../lib/api";
import type { RecommendedModel, Settings } from "../lib/types";

interface Props {
  open: boolean;
  onClose(changed: boolean): void;
}

export function SettingsDialog({ open, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [recommended, setRecommended] = useState<RecommendedModel[]>([]);
  const [pulled, setPulled] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    if (open && !el.open) {
      el.showModal();
      setError(null);
      Promise.all([getSettings(), getSetup()])
        .then(([s, setup]) => {
          setSettings(s);
          setRecommended(setup.recommended);
          setPulled(setup.pulled);
        })
        .catch((err: Error) => setError(err.message));
    } else if (!open && el.open) {
      el.close();
    }
  }, [open]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!settings) return;
    try {
      await saveSettings(settings);
      onClose(true);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const others = pulled.filter((name) => !recommended.some((m) => m.name === name));

  return (
    <dialog ref={dialog} className="settings" onCancel={() => onClose(false)}>
      <form onSubmit={submit}>
        <h2>Settings</h2>
        {settings ? (
          <>
            <fieldset>
              <legend>AI model</legend>
              {recommended.map((m) => (
                <label key={m.name} className="model-option">
                  <input
                    type="radio"
                    name="model"
                    checked={settings.model === m.name}
                    onChange={() => setSettings({ ...settings, model: m.name })}
                  />
                  <span>
                    <span className="model-name">
                      <strong>{m.name}</strong>
                      {pulled.includes(m.name) && <em className="pill">downloaded</em>}
                    </span>
                    <small>
                      {m.note} · {m.download_gb} GB download · ~{m.ram_gb} GB memory
                    </small>
                  </span>
                </label>
              ))}
              {others.map((name) => (
                <label key={name} className="model-option">
                  <input
                    type="radio"
                    name="model"
                    checked={settings.model === name}
                    onChange={() => setSettings({ ...settings, model: name })}
                  />
                  <span>
                    <span className="model-name">
                      <strong>{name}</strong>
                      <em className="pill">downloaded</em>
                    </span>
                  </span>
                </label>
              ))}
            </fieldset>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={settings.think}
                onChange={(e) => setSettings({ ...settings, think: e.target.checked })}
              />
              <span>
                Think before labeling
                <small>Somewhat better labels, but analysis takes several times longer.</small>
              </span>
            </label>
            <p className="hint">Lectures you've already analyzed keep their results. Use “Re-analyze” to redo one.</p>
          </>
        ) : (
          !error && <p className="hint">Loading…</p>
        )}
        {error && <p className="error-text">{error}</p>}
        <div className="dialog-actions">
          <button type="button" onClick={() => onClose(false)}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={!settings}>
            Save
          </button>
        </div>
      </form>
    </dialog>
  );
}
