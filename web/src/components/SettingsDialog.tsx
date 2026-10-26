import { useEffect, useRef, useState, type FormEvent } from "react";
import { getSettings, getSetup, saveSettings } from "../lib/api";
import type { RecommendedModel, Settings, SpeechModel } from "../lib/types";

// Any language works ("auto" keeps the lecture's own); these are just quick picks.
const OUTPUT_LANGUAGES = [
  "English", "Hindi", "Spanish", "French", "German", "Portuguese", "Italian", "Russian", "Arabic",
  "Bengali", "Marathi", "Tamil", "Telugu", "Kannada", "Gujarati", "Urdu", "Punjabi", "Malayalam",
  "Chinese", "Japanese", "Korean", "Indonesian", "Vietnamese", "Thai", "Turkish", "Persian", "Swahili",
];

interface Props {
  open: boolean;
  onClose(changed: boolean): void;
}

export function SettingsDialog({ open, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [recommended, setRecommended] = useState<RecommendedModel[]>([]);
  const [pulled, setPulled] = useState<string[]>([]);
  const [speechModels, setSpeechModels] = useState<SpeechModel[]>([]);
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
          setSpeechModels(setup.speech_models);
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
            <label className="field">
              <span>Write chapter titles and summaries in</span>
              <select
                value={settings.output_language}
                onChange={(e) => setSettings({ ...settings, output_language: e.target.value })}
              >
                <option value="auto">The lecture's own language</option>
                {[...new Set([settings.output_language, ...OUTPUT_LANGUAGES])]
                  .filter((l) => l !== "auto")
                  .map((l) => (
                    <option key={l} value={l}>
                      {l}
                    </option>
                  ))}
              </select>
              <small>Lectures in any language work, including ones that mix languages.</small>
            </label>
            <fieldset>
              <legend>Speech-to-text, for lectures without captions</legend>
              {speechModels.map((m) => (
                <label key={m.name} className="model-option">
                  <input
                    type="radio"
                    name="whisper"
                    checked={settings.whisper_model === m.name}
                    onChange={() => setSettings({ ...settings, whisper_model: m.name })}
                  />
                  <span>
                    <strong>Whisper {m.name}</strong>
                    <small>
                      {m.note} · {m.download_mb >= 1000 ? `${(m.download_mb / 1000).toFixed(1)} GB` : `${m.download_mb} MB`}{" "}
                      download on first use · ~{m.ram_gb} GB memory
                    </small>
                  </span>
                </label>
              ))}
            </fieldset>
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
