import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import analyze_heuristic, analyze_ollama, cache, config, youtube
from .models import Analysis, AnalyzeRequest, Job
from .segmenter import build_segments

app = FastAPI(title="BriefLectures API", version="0.2.0")
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
        job.status, job.error = "error", f"Unexpected error: {type(exc).__name__}: {exc}"


@app.post("/api/analyze", response_model=Job)
def analyze(req: AnalyzeRequest) -> Job:
    try:
        video_id = youtube.parse_video_id(req.url)
    except youtube.YouTubeError as exc:
        raise HTTPException(400, str(exc)) from exc

    engine = _engine()
    if not req.force and (hit := cache.get(video_id, engine[0])):
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
