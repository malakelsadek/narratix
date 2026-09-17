"""
webapp/server.py

Minimal FastAPI backend for the EPUB -> Audiobook web app.

Flow:
  1. POST /api/parse       -- upload an epub, get back title/author/cover/
                               chapter preview + size estimate. The epub and
                               its parsed chapters are cached under an
                               upload_id for the next step.
  2. GET  /api/voices      -- curated list of high-quality narration voices
                               with sample clip URLs for instant preview.
  3. POST /api/jobs        -- start converting a previously uploaded book
                               with the chosen voice/options. Returns a job_id.
  4. GET  /api/jobs/{id}/events   -- Server-Sent Events progress stream.
  5. GET  /api/jobs/{id}/download -- the finished .zip (folder of chapter
                               MP3s + cover, ready to drop into an audiobook
                               player's library folder).

All uploads and generated audiobooks are stored under settings.data_dir,
a folder the user can choose (with a native folder picker) from the web UI;
see webapp/settings.py.
"""

import asyncio
import base64
import json
import shutil
import sys
import time
import uuid
import zipfile
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audiobook_core import (
    Chapter,
    CURATED_VOICES,
    concat_mp3_ffmpeg,
    estimate_audio_stats,
    estimate_conversion_seconds,
    extract_cover_image,
    ffmpeg_available,
    parse_epub,
    run_synthesis,
    sanitize_filename,
    split_into_chunks,
    tag_mp3,
)
from webapp.settings import pick_folder_dialog, settings

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

CHUNK_SIZE_CHARS = 3000
CONCURRENCY = 4

# In-memory registries. This app is meant for single-user local use, so a
# plain dict is enough -- no database needed.
UPLOADS: Dict[str, dict] = {}
JOBS: Dict[str, dict] = {}

app = FastAPI(title="EPUB to Audiobook")


@app.get("/api/health")
async def health():
    return {"ok": True, "ffmpeg": ffmpeg_available()}


def _folder_size_mb(path: Path) -> float:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total / (1024 * 1024), 1)


@app.get("/api/settings")
async def get_settings():
    size_mb = await asyncio.to_thread(_folder_size_mb, settings.data_dir)
    return {
        "data_dir": str(settings.data_dir),
        "is_default": settings.is_default(),
        "size_mb": size_mb,
    }


@app.post("/api/settings")
async def update_settings(data_dir: str = Form(...)):
    try:
        await asyncio.to_thread(settings.set_data_dir, Path(data_dir))
    except Exception as exc:
        raise HTTPException(400, f"Could not use that folder: {exc}")
    return {"data_dir": str(settings.data_dir)}


@app.post("/api/settings/browse")
async def browse_folder():
    try:
        path = await asyncio.to_thread(pick_folder_dialog)
    except Exception as exc:
        raise HTTPException(500, f"Could not open the folder picker: {exc}")
    return {"path": path}


@app.get("/api/voices")
async def get_voices():
    return [
        {**v, "sample_url": f"/static/samples/{v['id']}.mp3"}
        for v in CURATED_VOICES
    ]


@app.post("/api/parse")
async def parse_upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".epub"):
        raise HTTPException(400, "Please upload a .epub file")

    upload_id = uuid.uuid4().hex
    upload_dir = settings.uploads_dir / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    epub_path = upload_dir / "book.epub"

    data = await file.read()
    epub_path.write_bytes(data)

    try:
        title, author, chapters, book_obj = parse_epub(epub_path)
    except Exception as exc:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(400, f"Could not read this EPUB: {exc}")

    if not chapters:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(400, "No readable text content found in this EPUB.")

    cover_bytes = extract_cover_image(book_obj)
    cover_data_url = None
    if cover_bytes:
        (upload_dir / "cover.jpg").write_bytes(cover_bytes)
        cover_data_url = "data:image/jpeg;base64," + base64.b64encode(cover_bytes).decode("ascii")

    total_words = sum(len(c.text.split()) for c in chapters)
    stats = estimate_audio_stats(total_words)

    total_chunks = sum(len(split_into_chunks(c.text, CHUNK_SIZE_CHARS)) for c in chapters)
    eta_low, eta_high = estimate_conversion_seconds(total_chunks, len(chapters), CONCURRENCY)

    UPLOADS[upload_id] = {
        "epub_path": epub_path,
        "title": title,
        "author": author,
        "chapters": chapters,
        "cover_path": (upload_dir / "cover.jpg") if cover_bytes else None,
    }

    return {
        "upload_id": upload_id,
        "title": title,
        "author": author,
        "cover_data_url": cover_data_url,
        "chapter_count": len(chapters),
        "chapters": [{"index": c.index, "title": c.title} for c in chapters],
        "estimated_conversion_seconds_low": round(eta_low),
        "estimated_conversion_seconds_high": round(eta_high),
        **stats,
    }


@app.post("/api/jobs")
async def create_job(
    upload_id: str = Form(...),
    voice: str = Form(...),
    title: str = Form(None),
    author: str = Form(None),
    rate: str = Form("+0%"),
    include_combined: bool = Form(False),
):
    upload = UPLOADS.get(upload_id)
    if not upload:
        raise HTTPException(404, "Upload not found. Please re-upload the EPUB.")
    if not ffmpeg_available():
        raise HTTPException(500, "ffmpeg is not installed on the server -- cannot merge audio.")

    job_id = uuid.uuid4().hex
    queue: asyncio.Queue = asyncio.Queue()
    JOBS[job_id] = {"queue": queue, "status": "queued", "download_path": None}

    options = {
        "voice": voice,
        "title": (title or upload["title"]).strip() or upload["title"],
        "author": (author or upload["author"]).strip() or upload["author"],
        "rate": rate or "+0%",
        "include_combined": bool(include_combined),
    }

    asyncio.create_task(process_job(job_id, upload, options))
    return {"job_id": job_id}


async def process_job(job_id: str, upload: dict, options: dict) -> None:
    queue: asyncio.Queue = JOBS[job_id]["queue"]

    async def emit(payload: dict) -> None:
        await queue.put(payload)

    job_dir = settings.jobs_dir / job_id
    chapters_dir = job_dir / "chapters"
    temp_dir = job_dir / ".chunks"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        chapters: list[Chapter] = upload["chapters"]
        title = options["title"]
        author = options["author"]
        voice = options["voice"]
        rate = options["rate"]

        cover_bytes = None
        if upload["cover_path"] and upload["cover_path"].exists():
            cover_bytes = upload["cover_path"].read_bytes()

        await emit({"stage": "parsed", "chapters": len(chapters)})

        chapter_chunk_map = {}
        work_items = []
        for chapter in chapters:
            chunks = split_into_chunks(chapter.text, CHUNK_SIZE_CHARS)
            chapter_chunk_map[chapter.index] = []
            for i, chunk_text in enumerate(chunks):
                out_path = temp_dir / f"ch{chapter.index:03d}_part{i:03d}.mp3"
                chapter_chunk_map[chapter.index].append(out_path)
                work_items.append((chapter, i, chunk_text, out_path))

        total_chunks = len(work_items)
        await emit({"stage": "synthesizing", "done": 0, "total": total_chunks})

        synth_start = time.monotonic()

        async def on_progress(done: int, total: int) -> None:
            elapsed = time.monotonic() - synth_start
            eta_seconds = None
            if 0 < done < total and elapsed > 0:
                eta_seconds = (total - done) * (elapsed / done)
            await emit({"stage": "synthesizing", "done": done, "total": total, "eta_seconds": eta_seconds})

        await run_synthesis(work_items, voice, rate, "+0Hz", CONCURRENCY, on_progress)

        await emit({"stage": "merging", "done": 0, "total": len(chapters)})
        chapter_files = []
        for i, chapter in enumerate(chapters, start=1):
            chunk_paths = chapter_chunk_map[chapter.index]
            chapter_filename = f"{chapter.index:03d} - {sanitize_filename(chapter.title)}.mp3"
            chapter_out = chapters_dir / chapter_filename
            await asyncio.to_thread(concat_mp3_ffmpeg, chunk_paths, chapter_out)
            await asyncio.to_thread(
                tag_mp3, chapter_out, chapter.title, title, author, chapter.index, cover_bytes
            )
            chapter_files.append(chapter_out)
            await emit({"stage": "merging", "done": i, "total": len(chapters)})

        combined_path = None
        if options["include_combined"]:
            await emit({"stage": "combining"})
            combined_path = job_dir / f"{sanitize_filename(title)}.mp3"
            await asyncio.to_thread(concat_mp3_ffmpeg, chapter_files, combined_path)
            await asyncio.to_thread(tag_mp3, combined_path, title, title, author, None, cover_bytes)

        await emit({"stage": "packaging"})
        zip_path = job_dir / "audiobook.zip"
        folder_name = sanitize_filename(title)

        def build_zip():
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
                if cover_bytes:
                    zf.writestr(f"{folder_name}/cover.jpg", cover_bytes)
                for f in chapter_files:
                    zf.write(f, f"{folder_name}/{f.name}")
                if combined_path:
                    zf.write(combined_path, f"{folder_name}/{combined_path.name}")

        await asyncio.to_thread(build_zip)
        shutil.rmtree(temp_dir, ignore_errors=True)

        total_bytes = sum(f.stat().st_size for f in chapter_files)
        if combined_path:
            total_bytes += combined_path.stat().st_size

        JOBS[job_id]["status"] = "done"
        JOBS[job_id]["download_path"] = zip_path
        JOBS[job_id]["download_name"] = f"{folder_name}.zip"
        await emit({
            "stage": "done",
            "download_url": f"/api/jobs/{job_id}/download",
            "size_mb": round(total_bytes / (1024 * 1024), 1),
        })

    except Exception as exc:  # noqa: BLE001
        JOBS[job_id]["status"] = "error"
        await emit({"stage": "error", "message": str(exc)})
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    async def event_stream():
        queue: asyncio.Queue = job["queue"]
        while True:
            payload = await queue.get()
            yield f"data: {json.dumps(payload)}\n\n"
            if payload.get("stage") in ("done", "error"):
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/jobs/{job_id}/download")
async def download_job(job_id: str):
    job = JOBS.get(job_id)
    if not job or not job.get("download_path"):
        raise HTTPException(404, "Not ready or not found")
    return FileResponse(
        job["download_path"],
        media_type="application/zip",
        filename=job.get("download_name", "audiobook.zip"),
    )


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
