"""
audiobook_core.py

Shared EPUB-to-audiobook logic used by both the CLI (epub_audio_generator.py)
and the web app (webapp/server.py): EPUB parsing, text chunking, edge-tts
synthesis, ffmpeg-based merging, and ID3 tagging.
"""

import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, List, Optional, Tuple

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import edge_tts

try:
    from mutagen.id3 import ID3, TIT2, TALB, TPE1, TRCK, APIC
    from mutagen.id3 import error as ID3Error
    from mutagen.mp3 import MP3
    HAVE_MUTAGEN = True
except ImportError:
    HAVE_MUTAGEN = False


SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# edge-tts's default output is 24kHz mono MP3 at ~48kbps -- excellent for
# spoken word and very storage-efficient (a 10 hour book is roughly 200MB).
DEFAULT_BITRATE_KBPS = 48
WORDS_PER_MINUTE = 150  # typical audiobook narration pace, used for estimates

# A curated shortlist of the most natural-sounding edge-tts neural voices
# for long-form narration, spanning a few English accents. The full catalog
# has 300+ voices across languages -- see --list-voices in the CLI.
CURATED_VOICES = [
    # American
    {"id": "en-US-AriaNeural", "name": "Aria", "gender": "Female", "accent": "American",
     "tagline": "Bright and endlessly natural, the go-to narrator voice."},
    {"id": "en-US-JennyNeural", "name": "Jenny", "gender": "Female", "accent": "American",
     "tagline": "Friendly and conversational, great for fiction and memoirs."},
    {"id": "en-US-AvaNeural", "name": "Ava", "gender": "Female", "accent": "American",
     "tagline": "Smooth and expressive, a newer-generation favorite."},
    {"id": "en-US-EmmaNeural", "name": "Emma", "gender": "Female", "accent": "American",
     "tagline": "Bright and engaging, a versatile all-rounder."},
    {"id": "en-US-MichelleNeural", "name": "Michelle", "gender": "Female", "accent": "American",
     "tagline": "Clear and articulate, a dependable narrator."},
    {"id": "en-US-AnaNeural", "name": "Ana", "gender": "Female", "accent": "American",
     "tagline": "Youthful and bright, perfect for children's stories."},
    {"id": "en-US-AndrewNeural", "name": "Andrew", "gender": "Male", "accent": "American",
     "tagline": "Confident and grounded, excellent for nonfiction."},
    {"id": "en-US-GuyNeural", "name": "Guy", "gender": "Male", "accent": "American",
     "tagline": "Classic deep narrator tone."},
    {"id": "en-US-EricNeural", "name": "Eric", "gender": "Male", "accent": "American",
     "tagline": "Calm, measured pace, easy on long listens."},
    {"id": "en-US-BrianNeural", "name": "Brian", "gender": "Male", "accent": "American",
     "tagline": "Rich, professional broadcast tone."},
    {"id": "en-US-ChristopherNeural", "name": "Christopher", "gender": "Male", "accent": "American",
     "tagline": "Grounded and authoritative, strong for nonfiction."},
    {"id": "en-US-RogerNeural", "name": "Roger", "gender": "Male", "accent": "American",
     "tagline": "Mature and gravelly, full of character."},
    {"id": "en-US-SteffanNeural", "name": "Steffan", "gender": "Male", "accent": "American",
     "tagline": "Polished diction, precise and professional."},
    {"id": "en-US-AndrewMultilingualNeural", "name": "Andrew (HD)", "gender": "Male", "accent": "American",
     "tagline": "Newer-generation voice, extra natural delivery."},
    {"id": "en-US-AvaMultilingualNeural", "name": "Ava (HD)", "gender": "Female", "accent": "American",
     "tagline": "Newer-generation voice, extra natural delivery."},
    {"id": "en-US-EmmaMultilingualNeural", "name": "Emma (HD)", "gender": "Female", "accent": "American",
     "tagline": "Newer-generation voice, extra natural delivery."},
    {"id": "en-US-BrianMultilingualNeural", "name": "Brian (HD)", "gender": "Male", "accent": "American",
     "tagline": "Newer-generation voice, extra natural delivery."},
    # British
    {"id": "en-GB-SoniaNeural", "name": "Sonia", "gender": "Female", "accent": "British",
     "tagline": "Crisp received-pronunciation, very polished."},
    {"id": "en-GB-LibbyNeural", "name": "Libby", "gender": "Female", "accent": "British",
     "tagline": "Youthful British charm."},
    {"id": "en-GB-MaisieNeural", "name": "Maisie", "gender": "Female", "accent": "British",
     "tagline": "Bright young British voice, great for children's books."},
    {"id": "en-GB-RyanNeural", "name": "Ryan", "gender": "Male", "accent": "British",
     "tagline": "Warm British narrator, great for classics."},
    {"id": "en-GB-ThomasNeural", "name": "Thomas", "gender": "Male", "accent": "British",
     "tagline": "Smooth, articulate storyteller quality."},
    # Australian
    {"id": "en-AU-NatashaNeural", "name": "Natasha", "gender": "Female", "accent": "Australian",
     "tagline": "Relaxed Australian warmth."},
    {"id": "en-AU-WilliamMultilingualNeural", "name": "William", "gender": "Male", "accent": "Australian",
     "tagline": "Easygoing Australian narrator."},
    # Irish
    {"id": "en-IE-EmilyNeural", "name": "Emily", "gender": "Female", "accent": "Irish",
     "tagline": "Soft, warm Irish storyteller."},
    {"id": "en-IE-ConnorNeural", "name": "Connor", "gender": "Male", "accent": "Irish",
     "tagline": "Distinctive Irish lilt, great character voice."},
]

VOICE_SAMPLE_TEXT = (
    "The old lighthouse keeper watched the storm roll in from the sea, "
    "and for the first time in years, he felt completely at peace."
)


@dataclass
class Chapter:
    index: int
    title: str
    text: str


# --------------------------------------------------------------------------
# EPUB parsing
# --------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """Collapse whitespace/newlines and strip stray unicode artifacts."""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def extract_cover_image(book: "epub.EpubBook") -> Optional[bytes]:
    """Best-effort extraction of the book's cover image for ID3 tagging."""
    try:
        for item in book.get_items_of_type(ebooklib.ITEM_COVER):
            return item.get_content()
    except Exception:
        pass
    try:
        cover_meta = book.get_metadata("OPF", "cover")
        if cover_meta:
            cover_id = cover_meta[0][1].get("content")
            item = book.get_item_with_id(cover_id)
            if item:
                return item.get_content()
    except Exception:
        pass
    try:
        for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
            if "cover" in item.get_name().lower():
                return item.get_content()
    except Exception:
        pass
    return None


def parse_epub(path: Path) -> Tuple[str, str, List[Chapter], "epub.EpubBook"]:
    """Parse an EPUB into (title, author, ordered chapters, raw book object)."""
    book = epub.read_epub(str(path), options={"ignore_ncx": True})

    title = path.stem
    author = "Unknown"
    if book.get_metadata("DC", "title"):
        title = book.get_metadata("DC", "title")[0][0] or title
    if book.get_metadata("DC", "creator"):
        author = book.get_metadata("DC", "creator")[0][0] or author

    items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    id_to_item = {item.get_id(): item for item in items}
    spine_ids = [entry[0] for entry in book.spine]
    ordered_items = [id_to_item[i] for i in spine_ids if i in id_to_item]
    if not ordered_items:
        ordered_items = items

    chapters: List[Chapter] = []
    for item in ordered_items:
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for tag in soup(["script", "style", "nav"]):
            tag.decompose()

        heading = soup.find(["h1", "h2", "h3"])
        chapter_title = heading.get_text(strip=True) if heading else None

        text = clean_text(soup.get_text(separator=" "))
        if len(text.split()) < 20:
            # Skip near-empty sections: cover pages, TOC stubs, blank dividers.
            continue

        chapters.append(Chapter(index=len(chapters) + 1, title=chapter_title or f"Chapter {len(chapters) + 1}", text=text))

    return title, author, chapters, book


def estimate_audio_stats(total_words: int) -> dict:
    """Rough estimate of narration length/size at edge-tts's default bitrate."""
    minutes = max(total_words / WORDS_PER_MINUTE, 0.1)
    seconds = minutes * 60
    size_mb = (DEFAULT_BITRATE_KBPS * 1000 / 8) * seconds / (1024 * 1024)
    return {"estimated_minutes": round(minutes, 1), "estimated_size_mb": round(size_mb, 1)}


# Empirical averages from real edge-tts runs, used only for the *upfront*
# estimate shown before conversion starts. The live progress stream reports
# a much more accurate ETA once synthesis is actually underway.
AVG_SECONDS_PER_CHUNK = 1.5
MERGE_SECONDS_PER_CHAPTER = 0.4
PACKAGE_OVERHEAD_SECONDS = 2.0


def estimate_conversion_seconds(total_chunks: int, chapter_count: int, concurrency: int) -> Tuple[float, float]:
    """Rough (low, high) wall-clock seconds range for the full conversion."""
    base = (total_chunks / max(concurrency, 1)) * AVG_SECONDS_PER_CHUNK
    base += chapter_count * MERGE_SECONDS_PER_CHAPTER
    base += PACKAGE_OVERHEAD_SECONDS
    return (base * 0.6, base * 1.6)


# --------------------------------------------------------------------------
# Text chunking
# --------------------------------------------------------------------------

def split_into_chunks(text: str, max_chars: int = 3000) -> List[str]:
    """Split chapter text into sentence-aware chunks under max_chars."""
    sentences = SENTENCE_SPLIT_RE.split(text)
    chunks: List[str] = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
                current = ""
            if len(sentence) > max_chars:
                for i in range(0, len(sentence), max_chars):
                    chunks.append(sentence[i:i + max_chars])
            else:
                current = sentence

    if current:
        chunks.append(current)
    return chunks


# --------------------------------------------------------------------------
# TTS synthesis (async, concurrency-limited, resumable)
# --------------------------------------------------------------------------

async def synthesize_chunk(text: str, voice: str, rate: str, pitch: str,
                            out_path: Path, semaphore: asyncio.Semaphore,
                            retries: int = 3) -> None:
    async with semaphore:
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
                await communicate.save(str(out_path))
                return
            except Exception as exc:  # noqa: BLE001 - network/service errors vary widely
                last_error = exc
                if attempt < retries:
                    await asyncio.sleep(2 * attempt)
        raise RuntimeError(f"Failed to synthesize chunk after {retries} attempts: {last_error}")


ProgressCallback = Callable[[int, int], Awaitable[None]]


async def run_synthesis(work_items: List[Tuple[Chapter, int, str, Path]],
                         voice: str, rate: str, pitch: str, concurrency: int,
                         on_progress: Optional[ProgressCallback] = None) -> None:
    """Synthesize every chunk in work_items, calling on_progress(done, total) as they complete."""
    semaphore = asyncio.Semaphore(concurrency)
    total = len(work_items)
    completed = 0
    lock = asyncio.Lock()

    async def worker(item: Tuple[Chapter, int, str, Path]) -> None:
        nonlocal completed
        _chapter, _chunk_idx, text, out_path = item
        try:
            if not (out_path.exists() and out_path.stat().st_size > 0):
                await synthesize_chunk(text, voice, rate, pitch, out_path, semaphore)
        finally:
            async with lock:
                completed += 1
                if on_progress:
                    await on_progress(completed, total)

    results = await asyncio.gather(*(worker(item) for item in work_items), return_exceptions=True)

    failures = [r for r in results if isinstance(r, Exception)]
    if failures:
        raise RuntimeError(
            f"{len(failures)} of {total} chunk(s) failed to synthesize. First error: {failures[0]}"
        )


async def list_voices(language_filter: Optional[str] = None) -> list:
    voices = await edge_tts.list_voices()
    voices = sorted(voices, key=lambda v: v["ShortName"])
    if language_filter:
        voices = [v for v in voices if language_filter.lower() in v["Locale"].lower()]
    return voices


# --------------------------------------------------------------------------
# Audio merging (ffmpeg concat -- memory-safe for very long books)
# --------------------------------------------------------------------------

def _find_ffmpeg_dir() -> Optional[Path]:
    """Look in common Windows install locations that a freshly-installed
    ffmpeg might live in even though the current process's PATH (inherited
    at process start) hasn't picked up the update yet -- e.g. right after
    `winget install ffmpeg`, which requires a new shell/process to see it."""
    if sys.platform != "win32":
        return None

    candidates: List[Path] = []
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        winget_root = Path(localappdata) / "Microsoft" / "WinGet" / "Packages"
        if winget_root.exists():
            candidates.extend(winget_root.glob("*ffmpeg*/**/ffmpeg.exe"))
    for base in (Path("C:/ProgramData/chocolatey/bin"), Path("C:/ffmpeg/bin")):
        exe = base / "ffmpeg.exe"
        if exe.exists():
            candidates.append(exe)

    return candidates[0].parent if candidates else None


def ffmpeg_available() -> bool:
    if shutil.which("ffmpeg"):
        return True
    ffmpeg_dir = _find_ffmpeg_dir()
    if ffmpeg_dir:
        os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")
        return shutil.which("ffmpeg") is not None
    return False


def check_ffmpeg() -> None:
    if not ffmpeg_available():
        print("ERROR: ffmpeg was not found on PATH.")
        print("Install it, then re-run:")
        print("  Windows : winget install ffmpeg   (or choco install ffmpeg)")
        print("  macOS   : brew install ffmpeg")
        print("  Linux   : sudo apt install ffmpeg")
        sys.exit(1)


def concat_mp3_ffmpeg(files: List[Path], out_path: Path) -> None:
    if not files:
        raise ValueError("No audio files to merge")
    if len(files) == 1:
        shutil.copyfile(files[0], out_path)
        return

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for file in files:
            escaped = str(file.resolve()).replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
        list_path = f.name

    try:
        # Fast path: stream copy (no re-encoding).
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", str(out_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Fallback: re-encode in case segments have mismatched frame params.
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                   "-c:a", "libmp3lame", "-b:a", "64k", "-ac", "1", str(out_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg concat failed:\n{result.stderr}")
    finally:
        os.unlink(list_path)


def get_mp3_duration_seconds(path: Path) -> float:
    if not ffmpeg_available():
        return 0.0
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:80] if name else "untitled"


def tag_mp3(path: Path, title: str, album: str, artist: str,
            track: Optional[int] = None, cover: Optional[bytes] = None) -> None:
    if not HAVE_MUTAGEN:
        return
    try:
        audio = MP3(str(path), ID3=ID3)
        try:
            audio.add_tags()
        except ID3Error:
            pass
        audio.tags.add(TIT2(encoding=3, text=title))
        audio.tags.add(TALB(encoding=3, text=album))
        audio.tags.add(TPE1(encoding=3, text=artist))
        if track is not None:
            audio.tags.add(TRCK(encoding=3, text=str(track)))
        if cover:
            audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover))
        audio.save()
    except Exception as exc:  # noqa: BLE001
        print(f"  Warning: failed to tag {path.name}: {exc}")
