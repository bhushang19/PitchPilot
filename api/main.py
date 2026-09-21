"""FastAPI service for the PitchPilot pipeline."""

import asyncio
import json
import os
import tempfile
import uuid
import zipfile
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field, HttpUrl
from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask

from core import explorer, video
from core.config import Config
from core.input_parser import parse_input
from core.render_html import render_html
from core.script_generator import generate_talking_script, save_talking_script


CONFIG = Config.load()
OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "output"


@dataclass
class Job:
    id: str
    make_video: bool
    dry_run: bool
    base_url: str = ""
    status: str = "queued"
    stage: str = "queued"
    run_dir: str | None = None
    app_slug: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    progress: int = 0
    heartbeat: int = 0
    message: str = "Starting the run..."
    started_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
    run_timestamp: str | None = None
    events: asyncio.Queue = field(default_factory=asyncio.Queue)


class JobRequest(BaseModel):
    base_url: HttpUrl
    spec_text: str = ""
    username: str = ""
    password: str = ""
    mfa_code: str = ""
    make_video: bool = False
    dry_run: bool = False
    format: Literal["md", "html"] = "md"


jobs: dict[str, Job] = {}
app = FastAPI(title="PitchPilot API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _snapshot(job: Job) -> dict[str, Any]:
    run_path = Path(job.run_dir or "")
    screenshot_dir = run_path / "screenshots"
    screenshot_roots = [screenshot_dir, run_path]
    screenshots = sorted({
        path.name
        for root in screenshot_roots
        if root.is_dir()
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    })
    return {
        "job_id": job.id,
        "status": job.status,
        "stage": job.stage,
        "make_video": job.make_video,
        "dry_run": job.dry_run,
        "artifacts": {
            name: path.replace(os.sep, "/") for name, path in job.artifacts.items()
        },
        "error": job.error,
        "screenshots": screenshots,
        "progress": job.progress,
        "heartbeat": job.heartbeat,
        "started_at": job.started_at,
        "run_timestamp": job.run_timestamp,
        "message": job.message,
    }


def _app_slug(base_url: str) -> str:
    host = urlparse(base_url).hostname or "app"
    slug = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")
    return slug.split(".")[0] or "app"


SIDECAR_NAME = "run.json"


def _duration_label(seconds: int) -> str:
    minutes, remainder = divmod(max(0, seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {remainder}s" if hours else f"{minutes}m {remainder}s"


def _write_sidecar(job: Job, request: JobRequest, *, ended: bool = False) -> None:
    """Persist run metadata next to the artifacts. Never stores credentials."""
    if not job.run_dir:
        return
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    data: dict[str, Any] = {
        "job_id": job.id,
        "base_url": job.base_url,
        "app_slug": job.app_slug,
        "make_video": job.make_video,
        "dry_run": job.dry_run,
        "format": request.format,
        "spec_present": bool(request.spec_text.strip()),
        "status": job.status,
        "stage": job.stage,
        "error": job.error,
        "started_at": job.started_at,
        "ended_at": now if ended else None,
        "run_timestamp": job.run_timestamp,
    }
    if ended:
        try:
            started = datetime.fromisoformat(job.started_at)
            data["duration_seconds"] = max(0, int((datetime.fromisoformat(now) - started).total_seconds()))
        except ValueError:
            data["duration_seconds"] = None
    try:
        path = _sidecar_path(job.run_dir)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def _sidecar_path(run_dir: str) -> Path:
    return Path(run_dir) / SIDECAR_NAME


def _read_sidecar(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / SIDECAR_NAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _refresh_live_output(job: Job) -> None:
    if job.run_dir:
        return
    app_dir = OUTPUT_ROOT / _app_slug(job.base_url)
    if not app_dir.is_dir():
        return
    candidates = [path for path in app_dir.iterdir() if path.is_dir()]
    if candidates:
        latest = max(candidates, key=lambda path: path.stat().st_mtime)
        job.run_dir = str(latest)
        job.app_slug = app_dir.name
        job.run_timestamp = datetime.fromtimestamp(
            latest.stat().st_ctime, tz=datetime.now().astimezone().tzinfo
        ).strftime("%Y-%m-%d %H:%M:%S %Z")


async def _push(job: Job, event: str, message: str | None = None) -> None:
    if message:
        job.message = message
    _refresh_live_output(job)
    payload = _snapshot(job)
    if message:
        payload["message"] = message
    await job.events.put({"event": event, "data": payload})


async def _worker(job: Job, request: JobRequest) -> None:
    heartbeat_task = None
    try:
        job.status = "running"
        job.stage = "exploring"
        job.progress = 10
        await _push(job, "stage", "Exploring the app - Chromium is visiting pages")

        async def keep_alive():
            while True:
                await asyncio.sleep(5)
                _refresh_live_output(job)
                job.heartbeat += 1
                await _push(job, "heartbeat", "Still exploring pages..." if job.stage == "exploring" else job.message)

        heartbeat_task = asyncio.create_task(keep_alive())
        run_dir, app_slug, script_path = await explorer.explore(
            CONFIG,
            str(request.base_url),
            request.spec_text,
            request.username,
            request.password,
            request.mfa_code,
        )
        job.run_dir = run_dir
        job.app_slug = app_slug
        job.run_timestamp = datetime.fromtimestamp(
            os.path.getctime(run_dir), tz=datetime.now().astimezone().tzinfo
        ).strftime("%Y-%m-%d %H:%M:%S %Z")
        _write_sidecar(job, request)
        if not os.path.isfile(script_path):
            raise RuntimeError(f"Expected demo script was not created: {script_path}")
        job.artifacts["demo-script"] = script_path
        html_path = os.path.join(run_dir, "demo-script.html")
        render_html(script_path, html_path)
        job.artifacts["demo-script-html"] = html_path
        latest_path = os.path.join(os.path.dirname(run_dir), "latest.html")
        render_html(script_path, latest_path, embed=True)
        job.artifacts["latest-html"] = latest_path

        job.progress = 33 if job.make_video else 50
        job.stage = "narrating"
        await _push(job, "stage", "Writing the talking script")
        parsed = parse_input(script_path)
        if not parsed.segments:
            raise RuntimeError("No feature segments found in the demo script.")
        script = generate_talking_script(CONFIG, parsed)
        json_path, md_path = save_talking_script(script, run_dir)
        job.artifacts["talking-script-json"] = json_path
        job.artifacts["talking-script"] = md_path

        if job.make_video:
            job.progress = 75
            job.stage = "rendering"
            await _push(job, "stage", "Rendering the video")
            video.render_video(CONFIG, script["segments"], run_dir, app_slug, job.dry_run)
            video_path = os.path.join(run_dir, "demo-video.mp4")
            if not os.path.isfile(video_path):
                raise RuntimeError(f"Expected video was not created: {video_path}")
            job.artifacts["video"] = video_path

        job.progress = 100
        job.status = "completed"
        job.stage = "completed"
        _write_sidecar(job, request, ended=True)
        await _push(job, "done", "Run completed")
    except Exception as exc:
        job.status = "failed"
        job.stage = "failed"
        job.error = str(exc)
        _write_sidecar(job, request, ended=True)
        await _push(job, "error", job.error)
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()


def _get_job(job_id: str) -> Job:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _artifact(job: Job, name: str) -> str:
    path = job.artifacts.get(name)
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Artifact not available")
    return path


def _run_archive(run_dir: Path) -> tuple[str, str]:
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="Run not found")
    archive = tempfile.NamedTemporaryFile(prefix="pitchpilot-", suffix=".zip", delete=False)
    archive_path = archive.name
    archive.close()
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in run_dir.rglob("*"):
            if path.is_file():
                bundle.write(path, path.relative_to(run_dir))
    return archive_path, f"pitchpilot-{run_dir.name}.zip"


def _archive_response(run_dir: Path) -> FileResponse:
    archive_path, filename = _run_archive(run_dir)
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(os.unlink, archive_path),
    )


def _history_run(app_slug: str, run_id: str) -> Path:
    root = (OUTPUT_ROOT / app_slug / run_id).resolve()
    if root.parent.parent != OUTPUT_ROOT.resolve() or not root.is_dir():
        raise HTTPException(status_code=404, detail="Run not found")
    return root


def _history_artifacts(run_dir: Path) -> dict[str, str]:
    names = {
        "demo-script": "demo-script.md",
        "demo-script-html": "demo-script.html",
        "talking-script-json": "talking-script.json",
        "talking-script": "talking-script.md",
        "video": "demo-video.mp4",
    }
    return {
        key: str(run_dir / filename).replace(os.sep, "/")
        for key, filename in names.items()
        if (run_dir / filename).is_file()
    }


def _run_screenshots(run_dir: Path) -> list[str]:
    roots = [run_dir, run_dir / "screenshots"]
    return sorted({
        path.name
        for root in roots
        if root.is_dir()
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    })


def _duration(run_dir: Path, started_at: float | None = None) -> tuple[int, str]:
    started = started_at or run_dir.stat().st_ctime
    latest = started
    for path in run_dir.rglob("*"):
        if path.is_file():
            latest = max(latest, path.stat().st_mtime)
    seconds = max(0, int(latest - started))
    return seconds, _duration_label(seconds)


@app.get("/api/history")
async def get_history():
    history = []
    for job in jobs.values():
        if job.status in {"queued", "running"}:
            _refresh_live_output(job)
            snapshot = _snapshot(job)
            history.append({
                "app_slug": job.app_slug or _app_slug(job.base_url),
                "run_id": job.id,
                "run_timestamp": job.run_timestamp or job.started_at,
                "base_url": job.base_url,
                "artifacts": snapshot["artifacts"],
                "screenshots": snapshot["screenshots"][:6],
                "screenshot_count": len(snapshot["screenshots"]),
                "status": "in_progress",
                "job_id": job.id,
                "stage": job.stage,
                "progress": job.progress,
                "message": "Starting the run..." if job.stage == "queued" else "Working...",
                "duration_seconds": max(0, int((datetime.now().astimezone() - datetime.fromisoformat(job.started_at)).total_seconds())),
            })
    if not OUTPUT_ROOT.is_dir():
        return history
    for app_dir in OUTPUT_ROOT.iterdir():
        if not app_dir.is_dir():
            continue
        for run_dir in app_dir.iterdir():
            if not run_dir.is_dir():
                continue
            artifacts = _history_artifacts(run_dir)
            screenshots = _run_screenshots(run_dir)
            if not artifacts and not screenshots:
                continue
            sidecar = _read_sidecar(run_dir)
            completed = "talking-script" in artifacts
            status = "completed" if completed else "in_progress"
            stage = "completed" if completed else "exploring"
            progress = 100 if completed else 10
            message = (
                "Run completed" if completed
                else "Partial output found; exploration may still be running or was interrupted"
            )
            duration_seconds, duration_label = _duration(run_dir)
            base_url = None
            if sidecar:
                base_url = sidecar.get("base_url") or None
                sc_status = sidecar.get("status")
                if sc_status == "failed":
                    status, stage, progress = "failed", "failed", 100
                    message = sidecar.get("error") or "Run failed"
                elif sc_status == "completed":
                    status, stage, progress, completed = "completed", "completed", 100, True
                    message = "Run completed"
                if isinstance(sidecar.get("duration_seconds"), int):
                    duration_seconds = sidecar["duration_seconds"]
                    duration_label = _duration_label(duration_seconds)
            history.append({
                "app_slug": app_dir.name,
                "run_id": run_dir.name,
                "run_timestamp": (sidecar or {}).get("run_timestamp") or datetime.fromtimestamp(
                    run_dir.stat().st_ctime, tz=datetime.now().astimezone().tzinfo
                ).strftime("%Y-%m-%d %H:%M:%S %Z"),
                "base_url": base_url,
                "artifacts": artifacts,
                "screenshots": screenshots[:6],
                "status": status,
                "stage": stage,
                "progress": progress,
                "message": message,
                "duration_seconds": duration_seconds,
                "duration_label": duration_label,
                "screenshot_count": len(screenshots),
            })
    return sorted(history, key=lambda item: item["run_id"], reverse=True)


@app.post("/api/jobs", status_code=202)
async def create_job(request: JobRequest):
    missing = CONFIG.missing_for_script()
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing env vars for exploration/script: {', '.join(missing)}",
        )
    if request.make_video and not request.dry_run:
        missing = CONFIG.missing_for_narration()
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing env vars for narration: {', '.join(missing)}",
            )

    job_id = str(uuid.uuid4())
    job = Job(job_id, request.make_video, request.dry_run, str(request.base_url))
    jobs[job_id] = job
    asyncio.create_task(_worker(job, request))
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    return _snapshot(_get_job(job_id))


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    job = _get_job(job_id)

    async def stream():
        yield {"event": "snapshot", "data": _snapshot(job)}
        while True:
            event = await job.events.get()
            yield event
            if event["event"] in {"done", "error"}:
                break

    return EventSourceResponse(stream())


@app.get("/api/jobs/{job_id}/script", response_class=PlainTextResponse)
async def get_script(job_id: str):
    return FileResponse(_artifact(_get_job(job_id), "talking-script"), media_type="text/markdown")


@app.get("/api/jobs/{job_id}/download")
async def download_job_artifacts(job_id: str):
    return _archive_response(Path(_get_job(job_id).run_dir or ""))


@app.get("/api/jobs/{job_id}/artifacts/{name}")
async def get_artifact(job_id: str, name: str):
    allowed = {
        "demo-script",
        "demo-script-html",
        "latest-html",
        "talking-script-json",
        "talking-script",
        "video",
    }
    if name not in allowed:
        raise HTTPException(status_code=404, detail="Artifact not available")
    return FileResponse(_artifact(_get_job(job_id), name))


@app.get("/api/history/{app_slug}/{run_id}/download")
async def download_history_artifacts(app_slug: str, run_id: str):
    return _archive_response(_history_run(app_slug, run_id))


@app.get("/api/history/{app_slug}/{run_id}/artifacts/{name}")
async def get_history_artifact(app_slug: str, run_id: str, name: str):
    allowed = {
        "demo-script",
        "demo-script-html",
        "talking-script-json",
        "talking-script",
        "video",
    }
    if name not in allowed:
        raise HTTPException(status_code=404, detail="Artifact not available")
    artifacts = _history_artifacts(_history_run(app_slug, run_id))
    path = artifacts.get(name)
    if not path:
        raise HTTPException(status_code=404, detail="Artifact not available")
    return FileResponse(path)


@app.get("/api/history/{app_slug}/{run_id}/artifacts/screenshots/{name}")
async def get_history_artifact_screenshot(app_slug: str, run_id: str, name: str):
    run_dir = _history_run(app_slug, run_id)
    if Path(name).name != name:
        raise HTTPException(status_code=400, detail="Invalid screenshot name")
    path = next((candidate for candidate in (run_dir / "screenshots" / name, run_dir / name) if candidate.is_file()), None)
    if path is None:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(path)


@app.get("/api/jobs/{job_id}/video")
async def get_video(job_id: str):
    return FileResponse(_artifact(_get_job(job_id), "video"), media_type="video/mp4", filename="demo-video.mp4")


@app.get("/api/jobs/{job_id}/screenshots/{name}")
async def get_screenshot(job_id: str, name: str):
    job = _get_job(job_id)
    if Path(name).name != name:
        raise HTTPException(status_code=400, detail="Invalid screenshot name")
    candidates = [Path(job.run_dir or "") / "screenshots" / name, Path(job.run_dir or "") / name]
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(path)


@app.get("/api/jobs/{job_id}/artifacts/screenshots/{name}")
async def get_job_artifact_screenshot(job_id: str, name: str):
    job = _get_job(job_id)
    if Path(name).name != name:
        raise HTTPException(status_code=400, detail="Invalid screenshot name")
    path = next((candidate for candidate in (Path(job.run_dir or "") / "screenshots" / name, Path(job.run_dir or "") / name) if candidate.is_file()), None)
    if path is None:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(path)
