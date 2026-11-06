"""Library: audiobooks found by scanning the save folder. No database; the folder is the source of truth."""

from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

from mutagen.id3 import ID3
from mutagen.mp3 import MP3

MAX_DEPTH = 3  # <root>/<author>/<title>/chapter.mp3 is depth 2; one spare level


def resolve_inside(root: Path, rel: str) -> Path:
    """Resolve a user-supplied relative path, refusing anything that escapes root."""
    root = root.resolve()
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise ValueError("Path is outside the library folder")
    return target


def _tag(tags: Optional[ID3], key: str) -> Optional[str]:
    frame = tags.get(key) if tags else None
    return str(frame.text[0]) if frame and frame.text else None


def _mp3s(book_dir: Path) -> List[Path]:
    return sorted(p for p in book_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp3")


def _book_info(root: Path, book_dir: Path) -> dict:
    files = _mp3s(book_dir)
    try:
        tags = ID3(str(files[0]))
    except Exception:  # untagged or unreadable file: fall back to the folder name
        tags = None
    rel = book_dir.relative_to(root).as_posix()
    return {
        "path": rel,
        "title": _tag(tags, "TALB") or book_dir.name,
        "author": _tag(tags, "TPE1") or "",
        "chapter_count": len(files),
        "size_mb": round(sum(f.stat().st_size for f in files) / (1024 * 1024), 1),
        "modified": max(f.stat().st_mtime for f in files),
        "cover_url": f"/api/library/file?path={quote(rel + '/cover.jpg')}" if (book_dir / "cover.jpg").exists() else None,
    }


def list_books(root: Path) -> List[dict]:
    """Every folder under root (up to MAX_DEPTH deep) that directly contains MP3 files."""
    root = root.resolve()
    books = []

    def walk(directory: Path, depth: int) -> None:
        try:
            entries = list(directory.iterdir())
        except OSError:
            return
        if any(e.is_file() and e.suffix.lower() == ".mp3" for e in entries):
            books.append(_book_info(root, directory))
        if depth < MAX_DEPTH:
            for e in entries:
                if e.is_dir() and not e.name.startswith("."):
                    walk(e, depth + 1)

    if root.exists():
        walk(root, 0)
    return books


def book_chapters(root: Path, rel: str) -> List[dict]:
    book_dir = resolve_inside(root, rel)
    if not book_dir.is_dir():
        raise FileNotFoundError(rel)
    chapters = []
    for f in _mp3s(book_dir):
        try:
            audio = MP3(str(f))
            duration = audio.info.length
            title = _tag(audio.tags, "TIT2")
        except Exception:
            duration, title = 0.0, None
        chapters.append({
            "title": title or f.stem,
            "duration": round(duration),
            "url": f"/api/library/file?path={quote(f.relative_to(root.resolve()).as_posix())}",
        })
    return chapters
