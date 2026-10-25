import os
import shutil

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import analyze_claude, analyze_heuristic, cache, config, youtube
from .models import Analysis, AnalyzeRequest
from .segmenter import build_segments

app = FastAPI(title="BriefLectures API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _engine() -> str:
    if config.ANALYZER != "auto":
        return config.ANALYZER
    has_credentials = (
        os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or shutil.which("ant")
    )
    return "claude" if has_credentials else "heuristic"


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "engine": _engine()}


# A plain `def` endpoint runs in FastAPI's threadpool, so a slow analysis doesn't block the server.
@app.post("/api/analyze", response_model=Analysis)
def analyze(req: AnalyzeRequest) -> Analysis:
    try:
        video_id = youtube.parse_video_id(req.url)
    except youtube.YouTubeError as exc:
        raise HTTPException(400, str(exc)) from exc

    engine = _engine()
    if not req.force and (hit := cache.get(video_id, engine)):
        return hit

    try:
        snippets = youtube.fetch_transcript(video_id, config.TRANSCRIPT_LANGUAGES)
    except youtube.YouTubeError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not snippets:
        raise HTTPException(422, "This video has no captions to analyze.")

    title = youtube.fetch_title(video_id)
    segments = build_segments(snippets)
    chapters = []
    if engine == "claude":
        try:
            segments, chapters, summary = analyze_claude.analyze(title, segments)
        except analyze_claude.ClaudeAnalysisError as exc:
            raise HTTPException(502, str(exc)) from exc
    else:
        segments, summary = analyze_heuristic.analyze(segments)

    result = Analysis(
        video_id=video_id,
        title=title,
        duration=segments[-1].end if segments else 0.0,
        engine=engine,
        summary=summary,
        segments=segments,
        chapters=chapters,
    )
    cache.put(result)
    return result
