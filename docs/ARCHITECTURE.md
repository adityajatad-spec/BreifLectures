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
│                   Claude (whole transcript in one call, so it can spot          │
│                   repeats an hour apart) or an offline heuristic                │
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
what to play.** Analysis is slow and costs money, so it runs once per video and is cached.
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
| **Claude for analysis** | One call sees the whole lecture, which is what redundancy detection needs. Structured JSON output means no parsing hacks. Without an API key the app falls back to an offline heuristic, so development never blocks on credentials. |

Native SwiftUI would feel slightly more native, but it means writing the UI twice (web
and Mac) and moving off Python's media tooling. That isn't worth it at this stage.

## Roadmap

**Phase 1: skeleton (this commit)**
- [x] Link → captions → segments → Claude/heuristic labels → cached analysis
- [x] Player with auto-skip and undo, 4 cuts, timeline, chapters, playback speed
- [x] Tests for URL parsing, segmentation, the API and the cut policies

**Phase 2: make it robust**
- [ ] Lectures with no captions: `yt-dlp` pulls the audio and `mlx-whisper` transcribes it locally
- [ ] Sharper cut boundaries: `ffmpeg silencedetect` on the audio, snapping cuts to real pauses
- [ ] Background jobs with progress streaming (SSE) instead of one long request
- [ ] Analysis of very long (3 h+) lectures in overlapping windows if one call isn't enough

**Phase 3: macOS app + branding**
- [ ] Tauri shell, Python sidecar, signed and notarized `.dmg`
- [ ] Spike early: YouTube embeds inside WKWebView need a real HTTP origin. Serve the UI from
      `http://localhost` (Tauri localhost plugin), not `tauri://`, or YouTube refuses to play.
- [ ] Brand pass: name, icon, colors (all colors are CSS tokens in `web/src/styles.css`)

**Phase 4: Breefly-parity features**
- [ ] Notes, quizzes, flashcards, chat with the lecture, searchable transcript
- [ ] Library of past lectures, resume position, per-course playlists
