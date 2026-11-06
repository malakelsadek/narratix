"""Builds demo EPUBs (generated covers, short original placeholder text) and narrates them into demo/library/.

Only for README screenshots; delete demo/ and this script afterwards.
Real covers can be dropped into demo/covers_in/<Title>.png; otherwise a cover is generated. Needs Pillow (pip install pillow).
Run: python scripts/make_demo.py
"""

import io
import shutil
import sys
import tempfile
from pathlib import Path

from ebooklib import epub
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from narratix import tts  # noqa: E402
from narratix.audio import concat_to_mp3, sanitize_filename, tag_mp3  # noqa: E402
from narratix.epub import parse_epub  # noqa: E402

DEMO = ROOT / "demo"
FONT = ROOT / "narratix" / "static" / "fonts" / "EBGaramond-Regular.ttf"

# (title, author, cover background, text colour, voice, three short placeholder chapters)
BOOKS = [
    ("How to Listen with Intention", "Patrick King", "#2F4B4A", "#F1E9D8", "af_heart",
     ["Listening begins with attention. Put down what you are holding and let the other person finish their thought before you form your reply.",
      "Notice the pauses between words. Silence is not an interruption; it is room for the speaker to find what they mean.",
      "End each conversation by repeating back one thing you heard. It shows you were present, and it keeps you honest."]),
    ("Outliers", "Malcolm Gladwell", "#B5472E", "#FBEFE3", "am_michael",
     ["Success rarely arrives from talent alone. It grows from where we start, when we were born, and who gave us a first chance.",
      "Practice matters, but so does the opportunity to practice. Hours only count when someone opens the door to the workshop.",
      "Look closely at any story of achievement and you will find a long chain of quiet advantages behind it."]),
    ("Flowers for Algernon", "Daniel Keyes", "#6B5B95", "#F4EEF9", "bf_emma",
     ["The first entry in the journal is short and full of mistakes. Each page after it grows clearer, faster, and a little lonelier.",
      "Understanding the world brings new questions about the people in it, and about whether they ever understood him at all.",
      "Some gifts cannot be kept. What remains is the writing, and the hope that someone will read it kindly."]),
    ("Atomic Habits", "James Clear", "#E4B93C", "#2A2310", "am_eric",
     ["Small changes look like nothing on any single day. Repeated for a year, they add up to a different person.",
      "Make the good habit obvious, easy, and satisfying, and make the bad one hard to start. The environment does most of the work.",
      "Do not aim only at the goal. Build the system that makes the goal the natural result of an ordinary week."]),
    ("Deep Work", "Cal Newport", "#1F2A44", "#E7ECF7", "am_adam",
     ["Hard things get done in long, uninterrupted stretches. Close the tabs, silence the phone, and give one problem your full attention.",
      "Shallow tasks fill every spare minute if you let them. Schedule focus first, and let the small requests wait their turn.",
      "The ability to concentrate is becoming rare in a distracted world, and rare skills tend to become more valuable over time, not less."]),
    ("How We Learn", "Stanislas Dehaene", "#3C6E57", "#EAF4EC", "af_bella",
     ["Memory is not a recording. Each time you recall something, you rebuild it, and the rebuilding is what makes it stick.",
      "Spacing your study over several days beats one long night. The gaps feel inefficient, but they are where the learning settles.",
      "Testing yourself is not only a way to measure learning. It is one of the strongest ways to produce it."]),
    ("The Giver", "Lois Lowry", "#5B5B5B", "#F2F2F2", "bf_isabella",
     ["In a quiet community where everything is orderly, one person is chosen to carry the memories that everyone else has agreed to forget.",
      "The memories arrive slowly at first, a color, a sound, a feeling, and each one makes the careful rules around him seem a little smaller.",
      "Carrying them alone grows heavy, and he begins to wonder whether a world without pain can also be a world without meaning."]),
    ("Shadow of the Minotaur", "Alan Gibbons", "#3B2A25", "#E9D8C4", "bm_george",
     ["The corridors of the maze turned back on themselves, and the torchlight shrank to a small, nervous circle on the stone floor.",
      "Somewhere ahead, something heavy shifted in the dark. Every instinct said to turn around, and every step said otherwise.",
      "At the center, the shadow was larger than the creature that cast it, and that was the first thing that gave him courage."]),
    ("What Life Should Mean to You", "Alfred Adler", "#4A6FA5", "#EEF3FA", "bm_fable",
     ["A person is shaped less by what happened to them than by the meaning they give to it, and that meaning can be revised.",
      "A sense of belonging is the quiet foundation of a good life. Courage grows where people feel they are part of something.",
      "Ask not only what you can get from life, but what you can contribute. The answer changes how every day feels."]),
]


def make_cover(title: str, author: str, bg: str, fg: str) -> bytes:
    w, h = 600, 900
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([28, 28, w - 28, h - 28], outline=fg, width=2)
    title_font = ImageFont.truetype(str(FONT), 72)
    author_font = ImageFont.truetype(str(FONT), 34)

    lines, line = [], ""
    for word in title.split():
        trial = f"{line} {word}".strip()
        if d.textlength(trial, font=title_font) <= w - 130:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)

    y = 170
    for ln in lines:
        d.text(((w - d.textlength(ln, font=title_font)) / 2, y), ln, font=title_font, fill=fg)
        y += 84
    d.line([w / 2 - 40, y + 24, w / 2 + 40, y + 24], fill=fg, width=2)
    d.text(((w - d.textlength(author, font=author_font)) / 2, h - 130), author, font=author_font, fill=fg)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def provided_cover(stem: str):
    """A real cover dropped into demo/covers_in/<title>.(png|jpg), as a 2:3 JPEG, if one exists."""
    for f in sorted((DEMO / "covers_in").glob(f"{stem}.*")):
        img = Image.open(f).convert("RGB")
        w, h = img.size
        if abs(w / h - 2 / 3) > 0.015:  # pad (don't crop) to the shelf's 2:3 shape, using the corner colour
            tw, th = (w, round(w * 1.5)) if w / h > 2 / 3 else (round(h / 1.5), h)
            padded = Image.new("RGB", (tw, th), img.getpixel((0, 0)))
            padded.paste(img, ((tw - w) // 2, (th - h) // 2))
            img = padded
        img.thumbnail((600, 900))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=92)
        return buf.getvalue()
    return None


def make_epub(path: Path, title: str, author: str, cover: bytes, chapters: list) -> None:
    book = epub.EpubBook()
    book.set_identifier(sanitize_filename(title))
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)
    book.set_cover("cover.jpg", cover)
    items = []
    for i, text in enumerate(chapters, start=1):
        c = epub.EpubHtml(title=f"Chapter {i}", file_name=f"chap_{i}.xhtml", lang="en")
        c.content = f"<h1>Chapter {i}</h1><p>{text}</p>"
        book.add_item(c)
        items.append(c)
    book.toc = items
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]
    epub.write_epub(str(path), book, {})


def narrate(epub_path: Path, voice: str, library: Path) -> None:
    title, author, chapters, book = parse_epub(epub_path)
    cover = (epub_path.parent / "covers" / f"{epub_path.stem}.jpg").read_bytes()
    out = library / sanitize_filename(f"{title} - {author}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "cover.jpg").write_bytes(cover)
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for ch in chapters:
            wav = Path(tmp) / f"{ch.index:03d}.wav"
            tts.synthesize(ch.text, voice, "+0%", wav)
            mp3 = out / f"{ch.index:03d} - {sanitize_filename(ch.title)}.mp3"
            concat_to_mp3([wav], mp3)
            tag_mp3(mp3, ch.title, title, author, ch.index, cover)
            files.append(mp3)


def main() -> None:
    epubs, covers, library = DEMO / "epubs", DEMO / "epubs" / "covers", DEMO / "library"
    covers.mkdir(parents=True, exist_ok=True)
    library.mkdir(parents=True, exist_ok=True)
    only = sys.argv[1:]  # optional: only rebuild books whose title contains one of these words
    for title, author, bg, fg, voice, chapters in BOOKS:
        if only and not any(w.lower() in title.lower() for w in only):
            continue
        stem = sanitize_filename(title)
        cover = provided_cover(stem) or make_cover(title, author, bg, fg)
        (covers / f"{stem}.jpg").write_bytes(cover)
        epub_path = epubs / f"{stem}.epub"
        make_epub(epub_path, title, author, cover, chapters)
        print(f"narrating {title} ({voice})", flush=True)
        narrate(epub_path, voice, library)
    print("done:", library)


if __name__ == "__main__":
    main()
