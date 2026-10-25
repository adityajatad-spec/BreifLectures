# BriefLectures

Paste a YouTube lecture link and pick how short you want it. A local AI model running on
your own machine finds the filler, the logistics and the parts that repeat, and the player
skips them for you. No API keys, and nothing leaves your computer except the YouTube requests.

> Working name. Branding comes later. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and roadmap.

## The macOS app

Download the `.dmg` from the GitHub release (or the **Release (macOS)** workflow's artifacts),
drag BriefLectures to Applications, and open it. The first screen walks you through
installing Ollama and downloading the model. To build it yourself on a Mac: `make setup && make app`.
See [docs/RELEASING.md](docs/RELEASING.md) for signing and releases.

## Run it for development (macOS / Linux)

You need Python 3.11+, Node 20+ and [Ollama](https://ollama.com/download).

```sh
ollama pull qwen3.5:4b    # ~3.4 GB download, ~4.5 GB RAM while analyzing
make setup                # backend venv + web deps
make dev                  # API on :8000, web app on http://localhost:5173
```

Without Ollama the app still works, using a rough offline heuristic instead of AI.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#local-model-sizing-for-a-16-gb-machine) for model sizing.

Paste a link such as `https://www.youtube.com/watch?v=...` and press **Shorten**.
`make app-dev` does the same inside the desktop window (needs Rust).

## Layout

```
backend/   FastAPI service: captions → segments → labels (local model or heuristic) → SQLite cache
web/       React + Vite UI: setup, library, cut picker, auto-skipping YouTube player, timeline
desktop/   Tauri 2 macOS app: Rust shell, splash page, icons, bundling config
scripts/   build-sidecar.sh packages the backend into one binary for the app
docs/      Architecture, roadmap, releasing
```

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `BRIEF_ANALYZER` | `auto` | `auto` (Ollama if ready, else heuristic), `ollama` or `heuristic` |
| `BRIEF_OLLAMA_MODEL` | `qwen3.5:4b` | Any model you've pulled into Ollama |
| `BRIEF_OLLAMA_CTX` | `8192` | Context window; bigger uses more RAM |
| `BRIEF_OLLAMA_THINK` | `0` | `1` lets the model think first: better labels, much slower |
| `BRIEF_OLLAMA_KEEP_ALIVE` | `2m` | How long Ollama keeps the model in RAM after a job |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Where Ollama is listening |
| `BRIEF_LANGUAGES` | `en,en-US,en-GB` | Caption languages to try, in order |
| `BRIEF_DATA_DIR` | `backend/data` | Where the SQLite cache lives |

## Tests

```sh
make test
```
