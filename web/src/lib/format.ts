export function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

export function minutes(seconds: number): string {
  const m = Math.round(seconds / 60);
  return m < 1 ? `${Math.round(seconds)}s` : `${m} min`;
}

/** "hi" → "Hindi", in the user's own language. Unknown codes are shown as they are. */
export function languageName(code: string): string {
  try {
    return new Intl.DisplayNames([navigator.language, "en"], { type: "language" }).of(code) ?? code;
  } catch {
    return code;
  }
}

/** "YouTube captions · Hindi (auto-generated)", or "Transcribed on this computer · Hindi, English". */
export function transcriptLabel(source: string, languages: string[]): string {
  if (!source || source.includes("·") || !languages.length) return source;
  return `${source} · ${languages.map(languageName).join(", ")}`;
}
