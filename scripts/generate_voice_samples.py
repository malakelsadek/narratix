"""Regenerate the voice preview clips in narratix/static/samples/ (the repo ships with them already)."""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from narratix import tts  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "narratix" / "static" / "samples"
OUT.mkdir(parents=True, exist_ok=True)

for v in tts.VOICES:
    mp3 = OUT / f"{v['id']}.mp3"
    if mp3.exists():
        continue
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "s.wav"
        tts.synthesize(tts.VOICE_SAMPLE_TEXT, v["id"], "+0%", wav)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "48k", "-ac", "1", str(mp3)], check=True)
    print("generated", mp3.name)
