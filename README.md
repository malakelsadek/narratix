# Narratix

Converts an `.epub` book into a high-quality MP3 audiobook using **Microsoft
Edge's free neural text-to-speech engine** ([edge-tts](https://github.com/rany2/edge-tts)).
No paid API keys, no external GUI apps -- just Python and ffmpeg.

Built to produce output that drops straight into an audiobook player (per-chapter
MP3s with ID3 chapter/track tags and embedded cover art, or one combined file).

Two ways to use it:

- **Web app** (recommended) -- drag-and-drop an EPUB, preview and pick a voice
  from a gallery of the best edge-tts narrators, click Generate, download a
  ready-to-transfer `.zip`. See [Web App](#web-app) below.
- **Command line** -- `epub_audio_generator.py`, for scripting/automation or
  power-user options like chapter ranges and pitch control. See
  [CLI Usage](#cli-usage) below.

## Web App

Narratix's point-and-click interface: drop in an EPUB, preview real voice
samples, and get back a `.zip` folder of tagged chapter MP3s ready to copy
onto your phone.

```bash
pip install -r requirements.txt
python run_webapp.py
```

This starts a local server and opens `http://127.0.0.1:8000` in your browser.

**Workflow:**

1. **Drop your `.epub`.** It's parsed instantly and never leaves your machine.
   You'll see the cover, title, author (both editable), chapter count, and an
   estimated narration length/file size.
2. **Pick a voice.** The gallery shows a curated shortlist of the most natural
   edge-tts neural voices (13 voices across American, British, Australian,
   and Irish accents) -- tap play on any card to hear a real sample before you
   commit. "Advanced options" has a narration-speed slider and a toggle to
   also generate one combined MP3 (off by default, since per-chapter files
   alone already play back-to-back with full chapter navigation and take half
   the storage).
3. **Click Generate.** Before you commit, you'll see an upfront estimate of
   how long conversion will take; once it starts, a progress bar and a live,
   continuously-updating ETA track synthesis, chapter merging, and packaging
   in real time.
4. **Download the `.zip`.** Unzip it into a folder inside your Smart
   AudioBooks Player library directory (e.g. via a USB transfer or a cloud
   sync folder) and it shows up as a book with cover art and chapter
   navigation, ready to play -- no extra setup.

**Why it stays small:** edge-tts's default output (24kHz mono MP3, ~48kbps)
is already tuned for spoken word -- a full 10-hour audiobook comes out to
roughly 200MB, a fraction of what music-grade bitrates would take, with no
audible quality loss for narration.

Need more control (custom chunk size, pitch shift, resuming an interrupted
run, scripting a batch of books)? Use the [CLI](#cli-usage) instead -- both
tools share the same underlying `audiobook_core.py` engine.

## Features

- **Direct EPUB parsing** with `ebooklib` + `beautifulsoup4` -- strips HTML tags,
  navigation clutter, and excess whitespace, keeping only clean narration text
  in original reading order.
- **Automatic chunking** -- long chapters are split into sentence-aware chunks
  (configurable size) so TTS requests stay fast and reliable, even for
  10+ hour books.
- **Any edge-tts voice** -- pick from 300+ free neural voices across languages
  and accents with `--voice`, or browse them with `--list-voices`.
- **Resumable** -- if a run is interrupted (network hiccup, closed laptop),
  re-running the same command skips chunks that already synthesized
  successfully.
- **Concurrent synthesis** -- multiple chunks are synthesized in parallel
  (tunable via `--concurrency`) for much faster processing of long books.
- **Memory-safe merging** -- chapters and the final book are stitched with
  `ffmpeg`'s concat demuxer, so even very long audiobooks merge without
  loading the whole thing into RAM.
- **ID3 metadata & cover art** -- chapter files get title/album/artist/track
  tags; the cover image embedded in the EPUB (if any) is carried over
  automatically.

## Requirements

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/) available on your `PATH` (used to stitch audio
  segments together)

Install ffmpeg:

```
# Windows (winget)
winget install ffmpeg

# Windows (choco)
choco install ffmpeg

# macOS
brew install ffmpeg

# Linux (Debian/Ubuntu)
sudo apt install ffmpeg
```

## Setup

```bash
# From the project folder
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
```

## CLI Usage

Basic conversion (default voice `en-US-AriaNeural`, produces both per-chapter
files and one combined MP3):

```bash
python epub_audio_generator.py "My Book.epub"
```

Choose a different voice:

```bash
python epub_audio_generator.py "My Book.epub" --voice en-US-GuyNeural
```

Browse all available voices (300+, all languages):

```bash
python epub_audio_generator.py --list-voices
python epub_audio_generator.py --list-voices --language en-US
```

Only produce per-chapter files (good for the "smart audiobook player" chapter
navigation UI), custom output folder, and a faster narration pace:

```bash
python epub_audio_generator.py "My Book.epub" \
  --output "MyBookAudio" \
  --format chapters \
  --rate +10%
```

Only produce a single combined MP3:

```bash
python epub_audio_generator.py "My Book.epub" --format single
```

Process just a chapter range (e.g. to re-run a section that failed, or test
on the first few chapters):

```bash
python epub_audio_generator.py "My Book.epub" --start-chapter 1 --end-chapter 3
```

Speed up synthesis on a fast connection, or slow it down if you're getting
throttled:

```bash
python epub_audio_generator.py "My Book.epub" --concurrency 6
```

### All options

```
positional arguments:
  epub_path             Path to the input .epub file

options:
  -o, --output          Output directory (default: ./output)
  -v, --voice           edge-tts voice name (default: en-US-AriaNeural)
  --rate                Speech rate adjustment, e.g. +10%, -15% (default: +0%)
  --pitch               Pitch adjustment, e.g. +5Hz, -10Hz (default: +0Hz)
  --format              chapters | single | both (default: both)
  --chunk-size          Max characters per TTS request chunk (default: 3000)
  --concurrency         Parallel synthesis workers (default: 3)
  --start-chapter       First chapter number to process (default: 1)
  --end-chapter         Last chapter number to process (default: last)
  --keep-temp           Keep intermediate per-chunk audio files
  --list-voices         List all available edge-tts voices and exit
  --language            Filter --list-voices by locale, e.g. en-US
  --title               Override book title used for metadata/filenames
  --author              Override author used for metadata
```

## Output layout

```
output/
├── My Book.mp3               # final combined audiobook (--format single/both)
└── chapters/
    ├── 001 - Chapter One.mp3
    ├── 002 - Chapter Two.mp3
    └── ...
```

Each chapter file carries ID3 tags (title, album = book title, artist =
author, track number, cover art) so it displays correctly in any audiobook
or media player.

## Project structure

```
audiobook_core.py           # shared engine: parsing, chunking, TTS, merging, tagging
epub_audio_generator.py     # CLI
run_webapp.py                # launches the web app
webapp/
├── server.py                # FastAPI backend (upload, voices, jobs, SSE progress)
├── generate_voice_samples.py  # (re)generates the voice preview clips
└── static/                  # frontend (index.html, style.css, app.js) + sample audio
```

## Notes & tips

- edge-tts calls Microsoft's free public TTS service over the network --
  keep `--concurrency` reasonable (3-6) to avoid being rate-limited on very
  long books.
- If a run is interrupted, just re-run the exact same command: already
  synthesized chunks in `output/.chunks/` are detected and skipped.
- Chapters shorter than ~20 words (blank dividers, cover pages, stray TOC
  entries) are automatically skipped during parsing.
