"""Command-line interface: `python -m narratix.cli book.epub`."""

import argparse
import shutil
import sys
from pathlib import Path

from tqdm import tqdm

from . import tts
from .audio import check_ffmpeg, concat_to_mp3, sanitize_filename, tag_mp3
from .epub import extract_cover_image, parse_epub, split_into_chunks


def main() -> None:
    p = argparse.ArgumentParser(prog="narratix.cli", description="Convert an EPUB into an MP3 audiobook, fully offline.")
    p.add_argument("epub_path", nargs="?", help="Path to the input .epub file")
    p.add_argument("-o", "--output", default="output", help="Output directory (default: ./output)")
    p.add_argument("-v", "--voice", default="af_heart", help="Voice id (default: af_heart; see --list-voices)")
    p.add_argument("--rate", default="+0%", help="Speech rate, e.g. +10%%, -15%% (default: +0%%)")
    p.add_argument("--format", choices=["chapters", "single", "both"], default="chapters",
                   help="Per-chapter MP3s, one combined MP3, or both (default: chapters)")
    p.add_argument("--chunk-size", type=int, default=1000, help="Max characters per TTS chunk (default: 1000)")
    p.add_argument("--start-chapter", type=int, default=1)
    p.add_argument("--end-chapter", type=int, default=None)
    p.add_argument("--list-voices", action="store_true", help="List all voices in the model and exit")
    p.add_argument("--title", default=None, help="Override the book title")
    p.add_argument("--author", default=None, help="Override the author")
    args = p.parse_args()

    if args.list_voices:
        print("\n".join(tts.list_voices()))
        return
    if not args.epub_path:
        p.error("epub_path is required unless --list-voices is used")
    if not Path(args.epub_path).exists():
        sys.exit(f"ERROR: file not found: {args.epub_path}")
    check_ffmpeg()

    title, author, chapters, book = parse_epub(Path(args.epub_path))
    title, author = args.title or title, args.author or author
    end = args.end_chapter or len(chapters)
    chapters = [c for c in chapters if args.start_chapter <= c.index <= end]
    if not chapters:
        sys.exit("ERROR: no readable chapters selected.")
    print(f"{title} by {author} -- {len(chapters)} chapters")

    out = Path(args.output)
    chapters_dir, temp_dir = out / "chapters", out / ".chunks"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    chunk_paths, work = {}, []
    for ch in chapters:
        chunk_paths[ch.index] = []
        for i, text in enumerate(split_into_chunks(ch.text, args.chunk_size)):
            path = temp_dir / f"ch{ch.index:03d}_part{i:03d}.wav"
            chunk_paths[ch.index].append(path)
            work.append((text, path))

    with tqdm(total=len(work), desc="Synthesizing", unit="chunk") as bar:
        tts.synthesize_all(work, args.voice, args.rate, lambda done, _total: (setattr(bar, "n", done), bar.refresh()))

    cover = extract_cover_image(book)
    chapter_files = []
    for ch in chapters:
        f = chapters_dir / f"{ch.index:03d} - {sanitize_filename(ch.title)}.mp3"
        concat_to_mp3(chunk_paths[ch.index], f)
        tag_mp3(f, ch.title, title, author, ch.index, cover)
        chapter_files.append(f)

    if args.format in ("single", "both"):
        final = out / f"{sanitize_filename(title)}.mp3"
        concat_to_mp3(chapter_files, final)
        tag_mp3(final, title, title, author, None, cover)
        print(f"Combined audiobook: {final}")
    if args.format == "single":
        shutil.rmtree(chapters_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)
    print(f"Done: {out}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrupted. Re-run the same command to resume.")
