"""ffmpeg merging and ID3 tagging."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

try:
    from mutagen.id3 import ID3, TIT2, TALB, TPE1, TRCK, APIC
    from mutagen.id3 import error as ID3Error
    from mutagen.mp3 import MP3
    HAVE_MUTAGEN = True
except ImportError:
    HAVE_MUTAGEN = False

# 24kHz mono 48kbps MP3: plenty for spoken word (~200MB for a 10 hour book).
BITRATE_KBPS = 48


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


def concat_to_mp3(files: List[Path], out_path: Path) -> None:
    """Concatenate audio files (WAV chunks or MP3s) into one MP3 via ffmpeg's concat demuxer."""
    if not files:
        raise ValueError("No audio files to merge")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for file in files:
            escaped = str(file.resolve()).replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
        list_path = f.name

    try:
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
               "-c:a", "libmp3lame", "-b:a", f"{BITRATE_KBPS}k", "-ac", "1", str(out_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed:\n{result.stderr}")
    finally:
        os.unlink(list_path)


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
