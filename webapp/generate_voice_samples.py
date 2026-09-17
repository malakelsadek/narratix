"""
Generates short preview clips for every curated voice in audiobook_core.py,
saved to webapp/static/samples/{voice_id}.mp3. Run this once during setup
(the repo already ships with samples generated, so most users never need
to run it) or after editing CURATED_VOICES.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import edge_tts

from audiobook_core import CURATED_VOICES, VOICE_SAMPLE_TEXT

SAMPLES_DIR = Path(__file__).resolve().parent / "static" / "samples"


async def generate_one(voice_id: str, semaphore: asyncio.Semaphore) -> None:
    out_path = SAMPLES_DIR / f"{voice_id}.mp3"
    if out_path.exists() and out_path.stat().st_size > 0:
        print(f"  skipping {out_path.name} (already exists)")
        return
    async with semaphore:
        communicate = edge_tts.Communicate(VOICE_SAMPLE_TEXT, voice=voice_id)
        await communicate.save(str(out_path))
    print(f"  generated {out_path.name} ({out_path.stat().st_size} bytes)")


async def main() -> None:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(4)
    print(f"Checking {len(CURATED_VOICES)} voice samples...")
    await asyncio.gather(*(generate_one(v["id"], semaphore) for v in CURATED_VOICES))
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
