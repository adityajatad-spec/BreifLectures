import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analyze_heuristic, analyze_ollama, cache, config, ollama_setup, settings, youtube
from .models import Analysis, AnalyzeRequest, Job, LibraryItem
from .segmenter import build_segments

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.load()
    yield


app = FastAPI(title="BriefLectures API", version="0.3.0", lifespan=lifespan)
# Only answer to loopback host names. Otherwise a web page could rebind its own domain to
# 127.0.0.1 (DNS rebinding) and drive this API from the user's browser.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# One worker on purpose: two lectures analyzed at once would double the model's RAM use.
_executor = ThreadPoolExecutor(max_workers=1)
_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def _engine() -> tuple[str, str]:
    """(engine, explanation shown to the user)."""
    if config.ANALYZER == "heuristic":
        return "heuristic", "Offline estimate (local AI disabled)."
    ready, why = analyze_ollama.status()
    if ready or config.ANALYZER == "ollama":
        return "ollama", why
    return "heuristic", f"Offline estimate. {why}"


@app.get("/api/health")
def health() -> dict:
    engine, detail = _engine()
    return {"ok": True, "engine": engine, "model": config.OLLAMA_MODEL, "detail": detail}


def _run(job: Job, engine_info: tuple[str, str]) -> None:
    engine, detail = engine_info

    def progress(done: int, total: int) -> None:
        job.done, job.total = done, total
        job.step = f"Analyzing part {min(done + 1, total)} of {total}" if done < total else "Finishing up"

    try:
        job.status, job.step = "running", "Fetching captions"
        snippets = youtube.fetch_transcript(job.video_id, config.TRANSCRIPT_LANGUAGES)
        if not snippets:
            raise youtube.YouTubeError("This video has no captions to analyze.")
        title = youtube.fetch_title(job.video_id)
        segments = build_segments(snippets)
        chapters = []
        if engine == "ollama":
            segments, chapters, summary = analyze_ollama.analyze(title, segments, progress)
        else:
            segments, _ = analyze_heuristic.analyze(segments)
            summary = detail
        result = Analysis(
            video_id=job.video_id,
            title=title,
            duration=segments[-1].end if segments else 0.0,
            engine=engine,
            summary=summary,
            segments=segments,
            chapters=chapters,
        )
        cache.put(result)
        job.result, job.status, job.step = result, "done", ""
    except (youtube.YouTubeError, analyze_ollama.LocalModelError) as exc:
        job.status, job.error = "error", str(exc)
    except Exception as exc:  # surface anything unexpected instead of leaving the job "running" forever
        log.exception("Analysis of %s failed", job.video_id)
        job.status, job.error = "error", f"Unexpected error: {type(exc).__name__}: {exc}"


@app.post("/api/analyze", response_model=Job)
def analyze(req: AnalyzeRequest) -> Job:
    try:
        video_id = youtube.parse_video_id(req.url)
    except youtube.YouTubeError as exc:
        raise HTTPException(400, str(exc)) from exc

    engine = _engine()
    if not req.force:
        # An AI analysis beats a fresh heuristic one, e.g. when Ollama just isn't running right now.
        hit = cache.get(video_id, engine[0]) or (engine[0] == "heuristic" and cache.get(video_id, "ollama"))
        if hit:
            return Job(id="cached", video_id=video_id, status="done", result=hit)

    with _lock:
        for job in _jobs.values():
            if job.video_id == video_id and job.status in ("queued", "running"):
                return job
        job = Job(id=uuid.uuid4().hex, video_id=video_id, status="queued", step="Waiting for the model")
        _jobs[job.id] = job
    _executor.submit(_run, job, engine)
    return job


@app.get("/api/jobs/{job_id}", response_model=Job)
def job_status(job_id: str) -> Job:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job")
    return job


# --- Library: lectures analyzed before -------------------------------------------------


@app.get("/api/library", response_model=list[LibraryItem])
def library() -> list[LibraryItem]:
    return cache.recent()


@app.delete("/api/library/{video_id}")
def forget(video_id: str) -> dict:
    cache.delete(video_id)
    return {"ok": True}


# --- Setup: getting a local model running ------------------------------------------------


@app.get("/api/setup")
def setup_status() -> dict:
    models = ollama_setup.pulled_models()
    engine, detail = _engine()
    return {
        "engine": engine,
        "detail": detail,
        "model_ready": analyze_ollama.status()[0] if models is not None else False,
        "ollama": ollama_setup.ollama_state(models),
        "ollama_download_url": ollama_setup.OLLAMA_DOWNLOAD_URL,
        "model": config.OLLAMA_MODEL,
        "pulled": models or [],
        "recommended": ollama_setup.RECOMMENDED,
        "pull": ollama_setup.pull_state(),
    }


@app.post("/api/setup/start-ollama")
def start_ollama() -> dict:
    try:
        ollama_setup.start_ollama()
    except (RuntimeError, OSError) as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True}


class PullRequest(BaseModel):
    model: str


@app.post("/api/setup/pull", response_model=ollama_setup.PullState)
def pull(req: PullRequest) -> ollama_setup.PullState:
    return ollama_setup.start_pull(req.model.strip())


@app.get("/api/settings", response_model=settings.Settings)
def get_settings() -> settings.Settings:
    return settings.current()


@app.put("/api/settings", response_model=settings.Settings)
def put_settings(new: settings.Settings) -> settings.Settings:
    if not new.model.strip():
        raise HTTPException(400, "Model name can't be empty.")
    return settings.save(new)


# Registered last so /api/* always wins. Only the desktop app sets this.
if config.STATIC_DIR:
    app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="ui")
