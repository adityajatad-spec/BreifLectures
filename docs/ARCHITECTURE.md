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
│ youtube.py      captions in any language (2–5 s lines) + title                  │
│ speech.py   ┐   no captions? → brief-transcribe, a separate process:            │
│ transcribe.py┘    yt-dlp audio → Whisper, language checked every 30 s           │
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
| **Python for the backend** | The tools we need are Python-first: `youtube-transcript-api`, `yt-dlp`, and Whisper (`faster-whisper`). |
| **React + Vite + TypeScript for the UI** | The same UI becomes the macOS app's UI with no rewrite. |
| **Tauri 2 for the macOS app** | Wraps the web UI in the system WKWebView, so the shell adds only a few MB (Electron adds 150 MB+). The Python backend ships inside as a sidecar binary built with PyInstaller (~25 MB). Tauri also handles code signing, notarization and the .dmg. |
| **SQLite** | Zero-ops, a single file in `~/Library/Application Support/…` once it's an app. |
| **A local model via Ollama** | No API key, no per-lecture cost, and transcripts never leave the machine. Ollama handles Metal acceleration, model downloads and memory, and it can turn a JSON schema into a grammar so even a small model can only produce valid labels. If Ollama isn't running, the app falls back to an offline heuristic. |

Native SwiftUI would feel slightly more native, but it means writing the UI twice (web
and Mac) and moving off Python's media tooling. That isn't worth it at this stage.

## Any language, and mixed languages

Every lecture should work, whatever it's in, including lectures that switch languages
mid-sentence (Hindi and English, say).

**Getting the words.**
1. **YouTube captions** in whatever language the video has: the preferred languages
   (`BRIEF_LANGUAGES`) first, then any human-made captions, then auto-generated ones. They
   are used **as spoken, not machine-translated**: translation garbles mixed-language
   speech, and the model reads the original fine.
2. **No captions, or YouTube won't hand them over?** The engine runs `brief-transcribe`:
   - **Audio:** yt-dlp downloads the audio only. YouTube now requires a JavaScript runtime
     for that, so Deno is bundled.
   - **Speech to text:** faster-whisper transcribes it on the CPU, int8, with voice-activity
     detection. That covers about 99 languages, and with `multilingual=True` the language is
     re-detected for every 30 s of audio, so code-switching lectures come out in whichever
     language is being spoken.
   - **Which languages:** detection is sampled at 8 points across the speech before
     transcribing. That gives the "Transcribed on this computer · Hindi, English" line in
     the UI, and picks a **script hint**: Whisper tends to write Hindi in Urdu script, and
     Mandarin in Traditional characters, so a short phrase in Devanagari (mixed with English,
     the way Hinglish lectures speak) or in Simplified Chinese steers every 30 s window.
     The first macOS speech check showed the Urdu-script problem; the check now fails on it.
   - **Why a separate process:** it never loads into the engine, its memory is freed the
     moment it exits, and the 180 MB of speech libraries only unpack when a lecture
     actually needs them.
   - **Model choice** (Settings): Whisper `small` by default (484 MB, ~1 GB RAM); `medium`
     and `large-v3-turbo` are more accurate for less common languages and mixed speech, and
     slower. The model downloads on first use.

**Reading them.**
- **The prompt** tells the model the lecture may be in any language or switch languages,
  and that the text may contain misheard words or words written in another script.
  Settings → "Write chapter titles and summaries in" picks the output language: English by
  default, or the lecture's own.
- **Chunk size** is measured in estimated tokens (UTF-8 bytes / 4), not words. Chinese,
  Japanese and Thai have no spaces, so counting words would have put a whole lecture into
  one window.
- **Sentence ends** are recognized in other scripts too (`। ॥ 。 ！ ？ ؟ ۔`), and non-speech
  caption notes in any language (`[संगीत]`, `[Música]`, `[音楽]`, `♪`) count as silence.
- **The offline estimate** (no Ollama) measures speech density in tokens per second, so
  dense Chinese or Hindi speech isn't mistaken for filler. Its keyword rules (homework,
  "like and subscribe", …) are still English-only, so non-English lectures get only the
  timing-based labels until local AI is set up.

**Checked on every release build.** `scripts/speech-smoke.py` has macOS's built-in voices
speak lecture passages in Spanish, French, German, Hindi, Japanese, Chinese and Hinglish,
and the packaged worker must transcribe them and name the language. Spanish must pass;
the others depend on which voices the build machine has.

**Known limits.**
- **Speed:** transcription is CPU-only and not yet measured on a real lecture; expect
  minutes per hour of audio with `small`.
- **Uncommon languages:** Whisper and a 4B model are weaker there than in widely spoken
  ones; `large-v3-turbo` helps.
- **yt-dlp goes stale:** YouTube changes often, so yt-dlp needs updating, which is a reason
  for auto-updates.

## The desktop app

```
BriefLectures.app
├── brieflectures      Rust shell (desktop/src-tauri/src/lib.rs)
├── brief-api          the engine (Python, PyInstaller, ~26 MB)
├── brief-transcribe   speech-to-text worker (Whisper + yt-dlp + Deno, ~180 MB)
└── Resources/web/     the built web UI
```

1. The window opens on a bundled splash page (`desktop/splash/`).
2. The shell starts `brief-api --port 0 --data-dir … --static-dir Resources/web --parent-pid …
   --transcriber <path to brief-transcribe>`.
3. The engine binds a free port on 127.0.0.1 and prints `BRIEF_READY http://127.0.0.1:<port>`.
4. The shell navigates the window there. From then on the engine serves **both the UI and the
   API from one origin**. That needs no CORS, the web code is identical in dev and in the
   app, and the YouTube player gets the real `http://` origin it requires. YouTube refuses
   to play inside pages served from `tauri://`.
5. On quit the shell kills the engine. If the shell crashes instead, the engine notices
   that its parent PID is gone within ~2 s and exits, so no orphaned server stays behind.
6. If the engine dies or doesn't start within 60 s, the window returns to the splash page
   with the reason, the log path and a **Restart** button.

Page → shell calls are limited by `capabilities/default.json`: the engine's origin may only
open links in the browser (`opener:default`). There's one app command, `restart_app`.

Where things live on a Mac:

| What | Where |
|---|---|
| Library cache + settings | `~/Library/Application Support/com.brieflectures.desktop/` |
| Logs (`app.log`, `backend.log`, rotated) | `~/Library/Logs/com.brieflectures.desktop/` |
| Remembered cut, speed, auto-skip, resume position | the webview's localStorage |

**First run.** The home screen walks the user through local AI setup: download Ollama →
start Ollama (the backend can launch `/Applications/Ollama.app`) → download the model, with
a progress bar. Until that's done, lectures get the offline heuristic.

`make app-dev` opens the desktop window on top of `make dev`, with hot reload; no sidecar
is started in that mode. Releasing and signing are covered in [RELEASING.md](RELEASING.md).

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
- [x] Lectures in any language, mixed languages, and lectures without captions (local Whisper)
- [ ] Faster transcription on the Apple GPU (e.g. mlx-whisper) instead of the CPU
- [ ] Sharper cut boundaries: `ffmpeg silencedetect` on the audio, snapping cuts to real pauses
- [x] Background jobs with progress (polling; SSE later if needed)
- [x] Windowed analysis with a running outline, so a small local model handles any length
- [ ] Evaluation set: hand-label a few lectures and compare models and prompts on them
- [ ] Desktop app manages Ollama for the user (detect, offer install, pull the model with a progress bar)

**Phase 3: macOS app + branding**
- [x] Tauri shell, Python sidecar, splash and crash screen with restart, logs, single instance, window state
- [x] UI served from the engine's http:// origin, so the YouTube embed works
- [x] First-run setup (Ollama + model download), library, settings, resume position, auto-skip toggle
- [x] CI (tests + Rust lint) and a macOS release workflow (.dmg; signing/notarization via secrets)
- [ ] First real run on a Mac, and a signed + notarized release (see RELEASING.md)
- [ ] Auto-update, Intel build
- [ ] Brand pass: name, icon, colors (all colors are CSS tokens in `web/src/styles.css`;
      the icon is generated from `desktop/assets/icon.svg` with `npm run icons` in `desktop/`)

**Phase 4: Breefly-parity features**
- [ ] Notes, quizzes, flashcards, chat with the lecture, searchable transcript
- [ ] Per-course playlists
