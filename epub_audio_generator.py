#!/usr/bin/env python3
"""
epub_audio_generator.py

Convert an EPUB ebook into an MP3 audiobook using Microsoft Edge's free
neural text-to-speech engine (edge-tts). Everything runs locally and for
free -- no paid API keys required. Only a working ffmpeg install and a
Python environment are needed.

Pipeline:
    1. Parse the .epub with ebooklib + BeautifulSoup, extracting clean
       reading-order text per chapter/section.
    2. Split each chapter into TTS-safe text chunks (sentence-aware).
    3. Synthesize every chunk to MP3 with edge-tts (async, concurrent).
    4. Stitch chunks back into per-chapter MP3s, then optionally stitch
       all chapters into one final audiobook MP3, tagging both with
       ID3 metadata (title/author/chapter/cover art) via mutagen.

For a point-and-click experience with a voice gallery, see the web app
in webapp/ (run `python run_webapp.py`).
"""

import argparse
import asyncio
import shutil
import sys
from pathlib import Path
from typing import List, Tuple

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

from audiobook_core import (
    Chapter,
    check_ffmpeg,
    concat_mp3_ffmpeg,
    extract_cover_image,
    list_voices as core_list_voices,
    parse_epub,
    run_synthesis,
    sanitize_filename,
    split_into_chunks,
    tag_mp3,
)


RECOMMENDED_VOICES_TEXT = """
Recommended natural-sounding narration voices (free, via edge-tts):
  en-US-AriaNeural      Female, US English   (default -- very natural)
  en-US-JennyNeural     Female, US English, warm/conversational
  en-US-GuyNeural       Male,   US English
  en-US-EricNeural      Male,   US English, calm narrator tone
  en-GB-SoniaNeural     Female, British English
  en-GB-RyanNeural      Male,   British English
  en-AU-NatashaNeural   Female, Australian English
  en-IE-ConnorNeural    Male,   Irish English

Run with --list-voices to see the full list of 300+ available voices
(optionally filtered with --language, e.g. --language en-US)

Prefer a point-and-click UI with instant voice previews? Run:
  python run_webapp.py
"""


async def print_voices(language_filter) -> None:
    voices = await core_list_voices(language_filter)
    print(f"{'Voice':38} {'Gender':8} {'Locale':10}")
    print("-" * 60)
    for v in voices:
        print(f"{v['ShortName']:38} {v['Gender']:8} {v['Locale']:10}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="epub_audio_generator.py",
        description="Convert an EPUB book into an MP3 audiobook using free Microsoft Edge neural TTS.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=RECOMMENDED_VOICES_TEXT,
    )
    parser.add_argument("epub_path", nargs="?", help="Path to the input .epub file")
    parser.add_argument("-o", "--output", default="output", help="Output directory (default: ./output)")
    parser.add_argument("-v", "--voice", default="en-US-AriaNeural",
                         help="edge-tts voice name (default: en-US-AriaNeural)")
    parser.add_argument("--rate", default="+0%", help="Speech rate adjustment, e.g. +10%%, -15%% (default: +0%%)")
    parser.add_argument("--pitch", default="+0Hz", help="Pitch adjustment, e.g. +5Hz, -10Hz (default: +0Hz)")
    parser.add_argument("--format", choices=["chapters", "single", "both"], default="both",
                         help="Output per-chapter MP3s, one combined MP3, or both (default: both)")
    parser.add_argument("--chunk-size", type=int, default=3000,
                         help="Max characters per TTS request chunk (default: 3000)")
    parser.add_argument("--concurrency", type=int, default=3,
                         help="Number of chunks to synthesize in parallel (default: 3)")
    parser.add_argument("--start-chapter", type=int, default=1, help="First chapter number to process (default: 1)")
    parser.add_argument("--end-chapter", type=int, default=None, help="Last chapter number to process (default: last)")
    parser.add_argument("--keep-temp", action="store_true", help="Keep intermediate per-chunk audio files")
    parser.add_argument("--list-voices", action="store_true", help="List all available edge-tts voices and exit")
    parser.add_argument("--language", default=None, help="Filter --list-voices by locale, e.g. en-US")
    parser.add_argument("--title", default=None, help="Override the book title used for metadata/filenames")
    parser.add_argument("--author", default=None, help="Override the author used for metadata")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.list_voices:
        asyncio.run(print_voices(args.language))
        return

    if not args.epub_path:
        parser.error("epub_path is required unless --list-voices is used")

    epub_path = Path(args.epub_path)
    if not epub_path.exists():
        print(f"ERROR: file not found: {epub_path}")
        sys.exit(1)

    check_ffmpeg()

    print(f"Parsing '{epub_path.name}'...")
    title, author, chapters, book_obj = parse_epub(epub_path)
    title = args.title or title
    author = args.author or author

    if not chapters:
        print("ERROR: no readable text content found in this EPUB.")
        sys.exit(1)

    end_chapter = args.end_chapter or len(chapters)
    chapters = [c for c in chapters if args.start_chapter <= c.index <= end_chapter]
    if not chapters:
        print("ERROR: --start-chapter/--end-chapter selected no chapters.")
        sys.exit(1)

    print(f"Book   : {title}")
    print(f"Author : {author}")
    print(f"Chapters to process: {len(chapters)}")

    output_dir = Path(args.output)
    chapters_dir = output_dir / "chapters"
    temp_dir = output_dir / ".chunks"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    cover = extract_cover_image(book_obj)

    chapter_chunk_map = {}
    work_items: List[Tuple[Chapter, int, str, Path]] = []
    for chapter in chapters:
        chunks = split_into_chunks(chapter.text, args.chunk_size)
        chapter_chunk_map[chapter.index] = []
        for i, chunk_text in enumerate(chunks):
            out_path = temp_dir / f"ch{chapter.index:03d}_part{i:03d}.mp3"
            chapter_chunk_map[chapter.index].append(out_path)
            work_items.append((chapter, i, chunk_text, out_path))

    print(f"Total text chunks to synthesize: {len(work_items)} (voice: {args.voice})")

    progress = tqdm(total=len(work_items), desc="Synthesizing", unit="chunk") if tqdm else None

    async def on_progress(done: int, _total: int) -> None:
        if progress:
            progress.n = done
            progress.refresh()

    try:
        asyncio.run(run_synthesis(work_items, args.voice, args.rate, args.pitch, args.concurrency, on_progress))
    except RuntimeError as exc:
        if progress:
            progress.close()
        print(f"\n{exc}")
        print("\nRe-run the same command to resume -- completed chunks are cached and skipped.")
        sys.exit(1)
    finally:
        if progress:
            progress.close()

    print("Merging chapters...")
    chapter_files = []
    for chapter in chapters:
        chunk_paths = chapter_chunk_map[chapter.index]
        chapter_filename = f"{chapter.index:03d} - {sanitize_filename(chapter.title)}.mp3"
        chapter_out = chapters_dir / chapter_filename
        concat_mp3_ffmpeg(chunk_paths, chapter_out)
        tag_mp3(chapter_out, title=chapter.title, album=title, artist=author, track=chapter.index, cover=cover)
        chapter_files.append(chapter_out)
        print(f"  Created {chapter_out}")

    if args.format in ("single", "both"):
        print("Combining all chapters into the final audiobook...")
        final_path = output_dir / f"{sanitize_filename(title)}.mp3"
        concat_mp3_ffmpeg(chapter_files, final_path)
        tag_mp3(final_path, title=title, album=title, artist=author, cover=cover)
        print(f"Final audiobook: {final_path}")

    if args.format == "single":
        shutil.rmtree(chapters_dir, ignore_errors=True)

    if not args.keep_temp:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("Done!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Re-run the same command to resume -- completed chunks are cached.")
        sys.exit(130)
