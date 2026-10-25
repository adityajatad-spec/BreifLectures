# Architecture

BriefLectures is a working name until branding is settled. It shortens YouTube lectures.
You paste a link, AI labels every part of the lecture, and our own player skips the parts
your chosen "cut" leaves out. The idea comes from [Breefly](https://chromewebstore.google.com/detail/kminbfmdchjlkgaffnfoemnmckhnoelo),
a Chrome extension with Key Moments, Cut Filler and Custom Cuts modes. We run it as our own
web app and macOS app instead of an extension.

## The idea in one picture

```
 YouTube link
     │
     ▼
┌─────────────────────────── backend (Python, FastAPI) ───────────────────────────┐
│ youtube.py      captions (2–5 s lines) + title                                  │
│ segmenter.py    → ~20 s segments, gaps ≥ 3 s become "silence"                   │
│ analyze_*.py    → every segment gets: label, importance 0–1, topic              │
│                   local model via Ollama, ~15 min windows + running outline     │
│                   (so it can spot repeats), or an offline heuristic             │
│ main.py         one background job at a time; client polls for progress        │
│ cache.py        SQLite, one row per (video, engine): analyze once, replay free  │
└──────────────────────────────────────┬──────────────────────────────────────────┘
                                       │  Analysis JSON (segments + chapters + summary)
                                       ▼
┌─────────────────────────────── web (React, Vite) ───────────────────────────────┐
│ cuts.ts         policy → which segments play. Full / Cut filler / Key moments / │
│                 Custom length. Pure functions, instant to switch, unit-tested.  │
│ Player.tsx      YouTube IFrame API; polls time every 200 ms, seeks past skip    │
│                 ranges, "Watch it" toast undoes any single skip                 │
│ Timeline.tsx    kept vs skipped segments, click to seek                         │
└─────────────────────────────────────────────────────────────────────────────────┘
```

The key design decision is that **the backend describes the lecture, and the client decides
what to play.** Analysis is slow (minutes on a laptop), so it runs once per video and is cached.
Cuts are cheap policies over that analysis, so adding a new cut never means re-analyzing
anything. The same split also covers the upcoming features (notes, quizzes, flashcards,
chat, searchable transcript): each is a new view over the same segments.

### Labels

`core`, `example`, `recap`, `repeat`, `tangent`, `admin`, `promo`, `filler`, `silence`.
"Cut the filler" always skips `silence`, `filler`, `admin`, `promo` and `repeat`.
"Key moments" keeps `core` and `example` with importance ≥ 0.7. "Custom length" fills a
time budget with the highest-importance segments that are left once filler is gone.

## Why this stack (and why it fits a Mac)

The plan assumes an Apple Silicon Mac (M1 or newer), because the end product is a macOS app.

| Decision | Why |
|---|---|
| **Run the backend on your Mac, not in the cloud** | YouTube blocks caption scraping from datacenter IPs (`youtube-transcript-api` raises `IpBlocked` / `RequestBlocked` there, and this repo's cloud sandbox can't reach YouTube at all). From a home IP it just works. This makes desktop-first the easier path, not a detour. |
| **Python for the backend** | The tools we need are Python-first: `youtube-transcript-api`, `yt-dlp`, and Whisper ports such as `mlx-whisper`, which runs very fast on Apple Silicon. |
| **React + Vite + TypeScript for the UI** | The same UI becomes the macOS app's UI with no rewrite. |
| **Tauri 2 for the macOS app (phase 2)** | Wraps the web UI in the system WKWebView. The app is ~10 MB, against 150 MB+ for Electron. The Python backend ships as a bundled sidecar binary (PyInstaller). It also supports a native menu bar, global shortcuts, auto-update and code signing. |
| **SQLite** | Zero-ops, a single file in `~/Library/Application Support/…` once it's an app. |
| **A local model via Ollama** | No API key, no per-lecture cost, and transcripts never leave the machine. Ollama handles Metal acceleration, model downloads and memory, and it can turn a JSON schema into a grammar so even a small model can only produce valid labels. If Ollama isn't running, the app falls back to an offline heuristic. |

Native SwiftUI would feel slightly more native, but it means writing the UI twice (web
and Mac) and moving off Python's media tooling. That isn't worth it at this stage.

## Local model: sizing for a 16 GB machine

**Budget:** 5–6 GB for the model, leaving ~10 GB for macOS, the browser and the user's apps.

What a model really uses is **weights + context (KV cache) + runtime overhead**, not just its
download size:

| Piece | 4B model | 8B model |
|---|---|---|
| Weights at Q4_K_M (Ollama's default ~4.5-bit quantization) | ~2.5–3.4 GB | ~5–5.2 GB |
| Context window of 8k tokens | ~0.5–1.2 GB | ~1.2 GB |
| Runtime overhead | ~0.3 GB | ~0.3 GB |
| **Total** | **~3.5–5 GB ✅** | **~6.5 GB ❌ over budget** |

So the default is a **4B-class model: `qwen3.5:4b`**. Choosing the model is a single setting:

| Model (`BRIEF_OLLAMA_MODEL`) | Download | When |
|---|---|---|
| `qwen3.5:4b` (default) | ~3.4 GB | Best quality inside the budget |
| `qwen3:4b` | ~2.5 GB | If the 3.5 tag misbehaves; most widely supported |
| `llama3.2:3b` | ~2 GB | 8 GB machines; noticeably weaker labels |
| `qwen3:8b` | ~5.2 GB | Machines with 24 GB+ only |

Download sizes come from third-party listings. Check `ollama show <model>` after pulling,
and watch the real footprint in Activity Monitor during a run.

**How a 4B model handles a long lecture.** A 4B model at an 8k context can't read a whole
lecture at once, so the analyzer works in windows of about 15 minutes of speech
(≤1,800 words, roughly 3k tokens). Spotting a *repeat* needs memory of what came earlier,
so each window also receives a running outline: the topics of the core segments seen so far,
capped at 40 lines. That's a few hundred tokens instead of the whole transcript.

**Keeping a small model accurate.**
- Every request sends a JSON schema. Ollama compiles it to a grammar, so the model can
  only write the allowed labels, the segment ids in that window, and an importance from 0 to 10.
  It can't invent ids or labels.
- `temperature: 0`, and thinking is off by default (`BRIEF_OLLAMA_THINK=1` turns it on:
  better labels, several times slower).
- The heuristic labels everything first. If a window comes back unusable twice, that window
  keeps the heuristic labels instead of failing the whole lecture.

**Being a good citizen on the user's machine.**
- Only one analysis runs at a time (a single worker thread), so RAM use never doubles.
- `keep_alive` is 2 minutes, so Ollama unloads the model shortly after a job and the
  memory goes back to the user.
- Results are cached, so each video costs the analysis time only once.

**Speed: not yet measured.** Expect a few minutes per hour of lecture on an M1/M2 with a
4B model. The UI shows "Analyzing part N of M". Measure on real hardware before promising
numbers to users.

## Roadmap

**Phase 1: skeleton (this commit)**
- [x] Link → captions → segments → local-model/heuristic labels → cached analysis
- [x] Player with auto-skip and undo, 4 cuts, timeline, chapters, playback speed
- [x] Tests for URL parsing, segmentation, the API and the cut policies

**Phase 2: make it robust**
- [ ] Lectures with no captions: `yt-dlp` pulls the audio and `mlx-whisper` transcribes it locally
- [ ] Sharper cut boundaries: `ffmpeg silencedetect` on the audio, snapping cuts to real pauses
- [x] Background jobs with progress (polling; SSE later if needed)
- [x] Windowed analysis with a running outline, so a small local model handles any length
- [ ] Evaluation set: hand-label a few lectures and compare models and prompts on them
- [ ] Desktop app manages Ollama for the user (detect, offer install, pull the model with a progress bar)

**Phase 3: macOS app + branding**
- [ ] Tauri shell, Python sidecar, signed and notarized `.dmg`
- [ ] Spike early: YouTube embeds inside WKWebView need a real HTTP origin. Serve the UI from
      `http://localhost` (Tauri localhost plugin), not `tauri://`, or YouTube refuses to play.
- [ ] Brand pass: name, icon, colors (all colors are CSS tokens in `web/src/styles.css`)

**Phase 4: Breefly-parity features**
- [ ] Notes, quizzes, flashcards, chat with the lecture, searchable transcript
- [ ] Library of past lectures, resume position, per-course playlists
