"""
narratix/server.py

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
                               the library folder chosen in the UI, ready for a player.

Finished audiobooks go to settings.data_dir (the library folder), which the
user chooses with a native folder picker in the web UI;
see narratix/settings.py.
"""

import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import library, tts
from .audio import concat_to_mp3, ffmpeg_available, sanitize_filename, tag_mp3
from .epub import Chapter, extract_cover_image, parse_epub, split_into_chunks
from .settings import pick_folder_dialog, settings

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

CHUNK_SIZE_CHARS = 3000

# In-memory registries. This app is meant for single-user local use, so a
# plain dict is enough -- no database needed.
# Folder-name templates the user can choose between in the UI.
FOLDER_FORMATS = {
    "title_author": "{title} - {author}",
    "author_title": "{author} - {title}",
    "title": "{title}",
    "author_nested": "{author}/{title}",  # <author>/<title>/ -- one author folder, many books
}

UPLOADS: Dict[str, dict] = {}
JOBS: Dict[str, dict] = {}

app = FastAPI(title="Narratix")


@app.get("/api/health")
async def health():
    return {"ok": True, "ffmpeg": ffmpeg_available()}


@app.get("/api/settings")
async def get_settings():
    return {
        "data_dir": str(settings.data_dir),
        "is_default": settings.is_default(),
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
    return [{**v, "sample_url": f"/static/samples/{v['id']}.mp3"} for v in tts.VOICES]


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
    stats = tts.estimate_audio(total_words)

    total_chunks = sum(len(split_into_chunks(c.text, CHUNK_SIZE_CHARS)) for c in chapters)
    eta_low, eta_high = tts.estimate_conversion_seconds(total_chunks)

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
    folder_format: str = Form("title_author"),
):
    upload = UPLOADS.get(upload_id)
    if not upload:
        raise HTTPException(404, "Upload not found. Please re-upload the EPUB.")
    if folder_format not in FOLDER_FORMATS:
        raise HTTPException(400, f"Unknown folder format: {folder_format}")
    if voice not in {v["id"] for v in tts.VOICES}:
        raise HTTPException(400, f"Unknown voice: {voice}")
    if not ffmpeg_available():
        raise HTTPException(500, "ffmpeg is not installed on the server -- cannot merge audio.")

    job_id = uuid.uuid4().hex
    queue: asyncio.Queue = asyncio.Queue()
    JOBS[job_id] = {"queue": queue, "status": "queued"}

    options = {
        "voice": voice,
        "title": (title or upload["title"]).strip() or upload["title"],
        "author": (author or upload["author"]).strip() or upload["author"],
        "rate": rate or "+0%",
        "include_combined": bool(include_combined),
        "folder_format": folder_format,
    }

    asyncio.create_task(process_job(job_id, upload, options))
    return {"job_id": job_id}


async def process_job(job_id: str, upload: dict, options: dict) -> None:
    queue: asyncio.Queue = JOBS[job_id]["queue"]

    async def emit(payload: dict) -> None:
        await queue.put(payload)

    temp_dir = settings.jobs_dir / job_id  # scratch space for WAV chunks, deleted afterwards
    temp_dir.mkdir(parents=True, exist_ok=True)
    # Final output: <library>/<folder name per the chosen format>/ with chapter MP3s + cover.jpg
    parts = FOLDER_FORMATS[options["folder_format"]].format(
        title=sanitize_filename(options["title"]), author=sanitize_filename(options["author"]))
    book_dir = settings.data_dir.joinpath(*parts.split("/"))
    book_dir.mkdir(parents=True, exist_ok=True)

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

        chunk_paths = {}  # chapter index -> wav files, in order
        work = []
        for chapter in chapters:
            chunk_paths[chapter.index] = []
            for i, text in enumerate(split_into_chunks(chapter.text, CHUNK_SIZE_CHARS)):
                path = temp_dir / f"ch{chapter.index:03d}_part{i:03d}.wav"
                chunk_paths[chapter.index].append(path)
                work.append((text, path))

        await emit({"stage": "synthesizing", "done": 0, "total": len(work)})

        loop = asyncio.get_running_loop()
        synth_start = time.monotonic()

        def on_progress(done: int, total: int) -> None:  # runs in the worker thread
            eta = (total - done) * (time.monotonic() - synth_start) / done if done < total else None
            loop.call_soon_threadsafe(
                queue.put_nowait, {"stage": "synthesizing", "done": done, "total": total, "eta_seconds": eta})

        await asyncio.to_thread(tts.synthesize_all, work, voice, rate, on_progress)

        await emit({"stage": "merging", "done": 0, "total": len(chapters)})
        chapter_files = []
        for i, chapter in enumerate(chapters, start=1):
            chapter_filename = f"{chapter.index:03d} - {sanitize_filename(chapter.title)}.mp3"
            chapter_out = book_dir / chapter_filename
            await asyncio.to_thread(concat_to_mp3, chunk_paths[chapter.index], chapter_out)
            await asyncio.to_thread(
                tag_mp3, chapter_out, chapter.title, title, author, chapter.index, cover_bytes
            )
            chapter_files.append(chapter_out)
            await emit({"stage": "merging", "done": i, "total": len(chapters)})

        combined_path = None
        if options["include_combined"]:
            await emit({"stage": "combining"})
            combined_path = book_dir / f"{sanitize_filename(title)}.mp3"
            await asyncio.to_thread(concat_to_mp3, chapter_files, combined_path)
            await asyncio.to_thread(tag_mp3, combined_path, title, title, author, None, cover_bytes)

        if cover_bytes:
            (book_dir / "cover.jpg").write_bytes(cover_bytes)
        shutil.rmtree(temp_dir, ignore_errors=True)

        total_bytes = sum(f.stat().st_size for f in chapter_files)
        if combined_path:
            total_bytes += combined_path.stat().st_size

        JOBS[job_id]["status"] = "done"
        await emit({
            "stage": "done",
            "saved_path": str(book_dir),
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


def _library_path(rel: str) -> Path:
    try:
        return library.resolve_inside(settings.data_dir, rel)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/library")
async def library_books():
    return await asyncio.to_thread(library.list_books, settings.data_dir)


@app.get("/api/library/chapters")
async def library_chapters(path: str):
    _library_path(path)  # validate before touching the disk
    try:
        return await asyncio.to_thread(library.book_chapters, settings.data_dir, path)
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")


@app.get("/api/library/file")
async def library_file(path: str):
    target = _library_path(path)
    if target.suffix.lower() not in (".mp3", ".jpg") or not target.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(target)  # supports HTTP range requests, so audio can seek


@app.post("/api/library/open")
async def library_open(path: str = Form("")):
    """Reveal a book's folder in the OS file manager (this server runs on your own machine)."""
    target = _library_path(path)
    if not target.is_dir():
        raise HTTPException(404, "Folder not found")
    if sys.platform == "win32":
        os.startfile(target)  # noqa: S606
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(target)])
    return {"ok": True}


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
