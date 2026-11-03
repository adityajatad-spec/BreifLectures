// Runs on youtube.com. On a watch page it asks the BriefLectures engine (the Mac app) to
// analyze the video, shows a panel under the player, and skips what the chosen cut leaves out.
import { buildCut, CUTS, keptDuration, rangeAt, skipRanges, type CutId, type SkipRange } from "../../web/src/lib/cuts";
import { minutes } from "../../web/src/lib/format";
import type { Analysis, Job, Label } from "../../web/src/lib/types";
import { DOWNLOAD_URL, type ApiRequest, type ApiResponse } from "./engine";
import { PANEL_CSS, TOAST_CSS } from "./styles";

const POLL_MS = 1000;
const TICK_MS = 200;
const SHOWN_CUTS: CutId[] = ["full", "no-filler", "key-moments"];
const KIND: Record<Label, string> = {
  core: "core", example: "example", recap: "recap", tangent: "recap",
  repeat: "skip", admin: "skip", promo: "skip", filler: "skip", silence: "skip",
};
const SKIP_NAMES: Partial<Record<Label, string>> = {
  admin: "logistics", filler: "filler", repeat: "a repeat", promo: "a promo", silence: "silence", tangent: "a tangent",
};

type View =
  | { kind: "loading"; step: string }
  | { kind: "offline" }
  | { kind: "error"; message: string }
  | { kind: "ready" };

const state = {
  videoId: null as string | null,
  analysis: null as Analysis | null,
  view: { kind: "loading", step: "Starting…" } as View,
  cut: "no-filler" as CutId,
  autoSkip: true,
  ranges: [] as SkipRange[],
  keep: [] as boolean[],
  exempt: new Set<string>(),
  request: 0,
  collapsed: false,
};

// ---------- Engine ----------

function api(req: Omit<ApiRequest, "type">): Promise<ApiResponse> {
  return chrome.runtime.sendMessage({ type: "api", ...req } as ApiRequest);
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function analyze(videoId: string, force = false) {
  const mine = ++state.request;
  const stale = () => state.request !== mine || state.videoId !== videoId;
  setView({ kind: "loading", step: "Connecting to BriefLectures…" });

  let res = await api({ path: "/api/analyze", method: "POST", body: { url: videoId, force } });
  while (!stale()) {
    if (!res.ok) {
      setView(res.offline ? { kind: "offline" } : { kind: "error", message: res.error });
      return;
    }
    const job = res.data as Job;
    const shown = job.result ?? job.partial;
    if (shown && shown.analyzed_until !== state.analysis?.analyzed_until) showAnalysis(shown);
    if (job.status === "done") return;
    if (job.status === "error") {
      setView({ kind: "error", message: job.error ?? "Analysis failed." });
      return;
    }
    if (!shown) setView({ kind: "loading", step: job.step || "Reading the lecture…" });
    else render(job);
    await sleep(POLL_MS);
    if (stale()) return;
    res = await api({ path: `/api/jobs/${job.id}` });
  }
}

function showAnalysis(a: Analysis) {
  state.analysis = a;
  state.view = { kind: "ready" };
  recompute();
}

function recompute() {
  const segs = state.analysis?.segments ?? [];
  state.keep = buildCut(segs, state.cut);
  state.ranges = state.autoSkip ? skipRanges(segs, state.keep) : [];
  render();
}

// ---------- Settings (shared with the popup) ----------

chrome.storage.sync.get({ cut: "no-filler", autoSkip: true }).then((s) => {
  state.cut = s.cut as CutId;
  state.autoSkip = s.autoSkip as boolean;
  recompute();
});
chrome.storage.onChanged.addListener((changes) => {
  if (changes.cut) state.cut = changes.cut.newValue as CutId;
  if (changes.autoSkip) state.autoSkip = changes.autoSkip.newValue as boolean;
  if (changes.cut || changes.autoSkip) recompute();
});

// ---------- DOM ----------

let host: HTMLElement | null = null;
let root: ShadowRoot | null = null;
let toastHost: HTMLElement | null = null;
let toastTimer = 0;

const player = () => document.querySelector<HTMLElement>("#movie_player");
const video = () => player()?.querySelector<HTMLVideoElement>("video") ?? null;
const isDark = () => document.documentElement.hasAttribute("dark");

function mount(): boolean {
  if (host?.isConnected) return true;
  const below = document.querySelector("ytd-watch-flexy #below") ?? document.querySelector("#below");
  if (!below) return false;
  host = document.createElement("div");
  host.id = "brieflectures-panel";
  host.style.cssText = "display:block;margin:12px 0 4px;";
  root = host.attachShadow({ mode: "open" });
  root.innerHTML = `<style>${PANEL_CSS}</style><div class="bl"></div>`;
  root.addEventListener("click", onClick);
  below.prepend(host);
  return true;
}

function unmount() {
  host?.remove();
  toastHost?.remove();
  host = root = toastHost = null;
}

function setView(v: View) {
  state.view = v;
  render();
}

function fmt(sec: number) {
  sec = Math.max(0, Math.round(sec));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = String(sec % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

function render(job?: Job) {
  if (!root) return;
  const el = root.querySelector(".bl") as HTMLElement;
  el.classList.toggle("dark", isDark());
  el.classList.toggle("collapsed", state.collapsed);
  const a = state.analysis;
  const refining = a?.analyzed_until != null;

  let status = "";
  if (state.view.kind === "ready" && a) {
    const full = a.duration;
    const saved = full - keptDuration(a.segments, state.keep);
    status = refining
      ? `<span class="live"></span>AI analyzing ahead · ${Math.round(((a.analyzed_until ?? 0) / Math.max(full, 1)) * 100)}%`
      : saved > 30
        ? `Saves ${minutes(saved)} of ${minutes(full)}`
        : `${minutes(full)} lecture`;
  }

  const headRow = `
    <div class="head">
      <span class="logo" aria-hidden="true"></span>
      <b>BriefLectures</b>
      <span class="status">${status}</span>
      <button class="ghost" data-act="collapse" title="${state.collapsed ? "Show" : "Hide"}">${state.collapsed ? "Show" : "Hide"}</button>
    </div>`;

  let body = "";
  const v = state.view;
  if (v.kind === "offline") {
    body = `<div class="msg"><p><b>Open the BriefLectures app to shorten this lecture.</b> The extension uses the app on your Mac to read the lecture; nothing is sent anywhere else.</p>
      <div class="row"><a class="btn primary" href="${DOWNLOAD_URL}" target="_blank" rel="noopener">Download for Mac</a><button class="btn" data-act="retry">Try again</button></div></div>`;
  } else if (v.kind === "error") {
    body = `<div class="msg"><p>${esc(v.message)}</p><div class="row"><button class="btn" data-act="retry">Try again</button></div></div>`;
  } else if (v.kind === "loading" || !a) {
    const step = v.kind === "loading" ? v.step : job?.step || "Reading the lecture…";
    body = `<div class="msg loading"><span class="spinner"></span><span>${esc(step)}</span></div>`;
  } else {
    const segs = a.segments;
    const full = a.duration || 1;
    const cuts = SHOWN_CUTS.map((id) => {
      const def = CUTS.find((c) => c.id === id)!;
      const len = keptDuration(segs, buildCut(segs, id));
      return `<button class="cut ${state.cut === id ? "on" : ""}" data-cut="${id}" title="${esc(def.blurb)}">${esc(def.name)}<span>${minutes(len)}</span></button>`;
    }).join("");
    const bars = segs
      .map((s, i) => `<i class="k-${KIND[s.label]} ${state.keep[i] ? "" : "off"}" style="left:${(s.start / full) * 100}%;width:${((s.end - s.start) / full) * 100}%" data-seek="${s.start}" title="${fmt(s.start)} · ${s.label}${s.topic ? ` · ${esc(s.topic)}` : ""}"></i>`)
      .join("");
    const pending = refining && (a.analyzed_until ?? 0) < full
      ? `<span class="pending" style="left:${((a.analyzed_until ?? 0) / full) * 100}%"></span>` : "";
    body = `
      <div class="controls">
        <div class="cuts" role="radiogroup" aria-label="Cut">${cuts}</div>
        <label class="toggle"><input type="checkbox" data-act="autoskip" ${state.autoSkip ? "checked" : ""}><span></span>Auto-skip</label>
      </div>
      <div class="tl">${bars}${pending}<b class="head-mark"></b></div>
      <div class="foot"><span>${esc(a.transcript_source || "")}</span><span class="legend"><em class="k-core"></em>Core <em class="k-example"></em>Example <em class="k-recap"></em>Recap <em class="k-skip"></em>Skipped</span></div>`;
  }
  el.innerHTML = headRow + `<div class="body">${body}</div>`;
  tick();
}

function onClick(e: Event) {
  const t = e.target as HTMLElement;
  const cut = t.closest<HTMLElement>("[data-cut]")?.dataset.cut as CutId | undefined;
  if (cut) {
    chrome.storage.sync.set({ cut });
    return;
  }
  const seek = t.closest<HTMLElement>("[data-seek]")?.dataset.seek;
  if (seek) {
    const v = video();
    if (v) v.currentTime = Number(seek);
    return;
  }
  const act = t.closest<HTMLElement>("[data-act]")?.dataset.act;
  if (act === "collapse") {
    state.collapsed = !state.collapsed;
    render();
  } else if (act === "retry" && state.videoId) {
    analyze(state.videoId);
  } else if (act === "autoskip") {
    chrome.storage.sync.set({ autoSkip: (t as HTMLInputElement).checked });
  }
}

// ---------- Skipping ----------

function toast(range: SkipRange) {
  const p = player();
  if (!p) return;
  if (!toastHost?.isConnected) {
    toastHost = document.createElement("div");
    toastHost.style.cssText = "position:absolute;left:0;right:0;bottom:64px;z-index:60;display:flex;justify-content:center;pointer-events:none;";
    const shadow = toastHost.attachShadow({ mode: "open" });
    shadow.innerHTML = `<style>${TOAST_CSS}</style><div class="toast"><span class="t"></span><button>Watch it</button></div>`;
    shadow.querySelector("button")!.addEventListener("click", () => {
      const key = toastHost!.dataset.key!;
      state.exempt.add(key);
      const v = video();
      if (v) v.currentTime = Number(key.split("-")[0]);
      toastHost!.shadowRoot!.querySelector(".toast")!.classList.remove("show");
    });
    p.appendChild(toastHost);
  }
  const shadow = toastHost.shadowRoot!;
  const what = range.labels.map((l) => SKIP_NAMES[l] ?? l).join(" + ");
  shadow.querySelector(".t")!.textContent = `Skipped ${fmt(range.end - range.start)} of ${what}`;
  toastHost.dataset.key = `${range.start}-${range.end}`;
  const box = shadow.querySelector(".toast")!;
  box.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => box.classList.remove("show"), 4000);
}

function tick() {
  // YouTube sometimes re-renders the area under the player; put the panel back.
  if (state.videoId && host && !host.isConnected) void sync();
  const v = video();
  const a = state.analysis;
  if (!v || !a) return;
  const mark = root?.querySelector<HTMLElement>(".head-mark");
  if (mark) mark.style.left = `${Math.min(v.currentTime / (a.duration || 1), 1) * 100}%`;
  // Never touch the player while YouTube is showing an ad: its currentTime is the ad's.
  if (player()?.classList.contains("ad-showing")) return;
  const i = rangeAt(state.ranges, v.currentTime);
  if (i < 0) return;
  const r = state.ranges[i];
  if (state.exempt.has(`${r.start}-${r.end}`)) return;
  v.currentTime = r.end;
  toast(r);
}
setInterval(tick, TICK_MS);

// ---------- Following YouTube's navigation ----------

function currentVideoId(): string | null {
  if (location.pathname !== "/watch") return null;
  return new URLSearchParams(location.search).get("v");
}

async function sync() {
  const id = currentVideoId();
  if (id === state.videoId && host?.isConnected) return;
  if (id !== state.videoId) {
    state.videoId = id;
    state.analysis = null;
    state.exempt.clear();
    state.ranges = [];
    state.request++;
  }
  if (!id) {
    unmount();
    return;
  }
  for (let i = 0; i < 50 && !mount(); i++) await sleep(200); // YouTube builds the page lazily
  if (!host) return;
  render();
  if (!state.analysis) analyze(id);
}

document.addEventListener("yt-navigate-finish", () => void sync());
// Follow YouTube's light/dark switch.
new MutationObserver(() => host?.shadowRoot?.querySelector(".bl")?.classList.toggle("dark", isDark())).observe(
  document.documentElement,
  { attributes: true, attributeFilter: ["dark"] },
);
void sync();
