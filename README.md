# BriefLectures

Paste a YouTube lecture link and pick how short you want it. AI finds the filler, the
logistics and the parts that repeat, and the player skips them for you.

> Working name. Branding comes later. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and roadmap.

## Run it (macOS / Linux)

You need Python 3.11+ and Node 20+.

```sh
make setup                              # backend venv + web deps
export ANTHROPIC_API_KEY=sk-ant-...     # optional; without it you get the offline heuristic
make dev                                # API on :8000, web app on http://localhost:5173
```

Paste a link such as `https://www.youtube.com/watch?v=...` and press **Shorten**.

## Layout

```
backend/   FastAPI service: captions → segments → labels (Claude or heuristic) → SQLite cache
web/       React + Vite UI: cut picker, auto-skipping YouTube player, timeline
docs/      Architecture and roadmap
```

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Enables AI analysis |
| `BRIEF_ANALYZER` | `auto` | `auto`, `claude` or `heuristic` |
| `BRIEF_CLAUDE_MODEL` | `claude-opus-5-5` | Model used for analysis |
| `BRIEF_LANGUAGES` | `en,en-US,en-GB` | Caption languages to try, in order |
| `BRIEF_DATA_DIR` | `backend/data` | Where the SQLite cache lives |

## Tests

```sh
make test
```
