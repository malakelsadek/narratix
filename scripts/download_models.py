"""One-time download of the Kokoro model files (~350MB) into models/. After this, Narratix is fully offline."""

import urllib.request
from pathlib import Path

BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]
DEST = Path(__file__).resolve().parent.parent / "models"

DEST.mkdir(exist_ok=True)
for name in FILES:
    target = DEST / name
    if target.exists():
        print(f"{name}: already present")
        continue
    print(f"Downloading {name} ...")
    urllib.request.urlretrieve(BASE + name, target)
print("Done.")
