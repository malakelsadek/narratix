"""Offline text-to-speech with the Kokoro ONNX model."""

import threading
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import soundfile as sf

from .audio import BITRATE_KBPS

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "models" / "kokoro-v1.0.onnx"
VOICES_PATH = ROOT / "models" / "voices-v1.0.bin"

VOICE_SAMPLE_TEXT = (
    "The old lighthouse keeper watched the storm roll in from the sea, "
    "and for the first time in years, he felt completely at peace."
)

# Voice ids encode accent + gender: a=American, b=British; f=female, m=male.
# (id, display name, tagline)
_VOICES = [
    ("af_heart", "Heart", "Warm and expressive, a great default narrator."),
    ("af_bella", "Bella", "Smooth and engaging, good for fiction."),
    ("af_nicole", "Nicole", "Soft and intimate, easy on long listens."),
    ("af_sarah", "Sarah", "Clear and friendly."),
    ("af_sky", "Sky", "Light and bright."),
    ("af_nova", "Nova", "Crisp and confident."),
    ("am_adam", "Adam", "Deep and steady."),
    ("am_michael", "Michael", "Grounded and authoritative, strong for nonfiction."),
    ("am_eric", "Eric", "Calm and measured."),
    ("am_liam", "Liam", "Relaxed and conversational."),
    ("am_onyx", "Onyx", "Low and resonant."),
    ("bf_emma", "Emma", "Polished British narrator."),
    ("bf_isabella", "Isabella", "Warm British storyteller."),
    ("bf_lily", "Lily", "Gentle and bright, good for children's books."),
    ("bm_george", "George", "Classic British narrator, great for classics."),
    ("bm_fable", "Fable", "Storyteller quality."),
    ("bm_lewis", "Lewis", "Clear and measured."),
    ("bm_daniel", "Daniel", "Smooth and articulate."),
]

VOICES = [
    {"id": vid, "name": name, "tagline": tagline,
     "accent": "British" if vid[0] == "b" else "American",
     "gender": "Female" if vid[1] == "f" else "Male"}
    for vid, name, tagline in _VOICES
]

_model = None
_lock = threading.Lock()  # one ONNX session; onnxruntime already uses all cores


def _load():
    global _model
    if _model is None:
        if not (MODEL_PATH.exists() and VOICES_PATH.exists()):
            raise RuntimeError("Kokoro model files are missing. Run: python scripts/download_models.py")
        from kokoro_onnx import Kokoro
        _model = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
    return _model


def rate_to_speed(rate: str) -> float:
    """'+10%' -> 1.1, '-15%' -> 0.85."""
    return max(0.5, min(2.0, 1 + int(rate.strip().rstrip("%")) / 100))


def synthesize(text: str, voice: str, rate: str, out_path: Path) -> None:
    """Synthesize text to a WAV file."""
    lang = "en-gb" if voice.startswith("b") else "en-us"
    with _lock:
        samples, sample_rate = _load().create(text, voice=voice, speed=rate_to_speed(rate), lang=lang)
    sf.write(str(out_path), samples, sample_rate)


def synthesize_all(work: List[Tuple[str, Path]], voice: str, rate: str,
                   on_progress: Optional[Callable[[int, int], None]] = None) -> None:
    """Synthesize (text, wav_path) pairs in order. Existing files are skipped, so an interrupted run resumes."""
    for done, (text, path) in enumerate(work, start=1):
        if not (path.exists() and path.stat().st_size > 0):
            synthesize(text, voice, rate, path)
        if on_progress:
            on_progress(done, len(work))


def list_voices() -> List[str]:
    return sorted(_load().get_voices())


# --- Estimates (rough; the live progress stream reports a real ETA) ---

WORDS_PER_MINUTE = 150
SECONDS_PER_CHUNK = 6.0  # CPU synthesis of a ~1000-char chunk; varies a lot by machine


def estimate_audio(total_words: int) -> dict:
    minutes = max(total_words / WORDS_PER_MINUTE, 0.1)
    size_mb = (BITRATE_KBPS * 1000 / 8) * minutes * 60 / (1024 * 1024)
    return {"estimated_minutes": round(minutes, 1), "estimated_size_mb": round(size_mb, 1)}


def estimate_conversion_seconds(total_chunks: int) -> Tuple[float, float]:
    """Rough (low, high) wall-clock seconds range for synthesis plus merging."""
    base = total_chunks * SECONDS_PER_CHUNK + 5
    return (base * 0.5, base * 1.8)
