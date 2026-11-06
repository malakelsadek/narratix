"""EPUB parsing and text chunking."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chapter:
    index: int
    title: str
    text: str


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


def split_into_chunks(text: str, max_chars: int = 1000) -> List[str]:
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
