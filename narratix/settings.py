"""
narratix/settings.py

Manages the library folder where finished audiobooks are saved (one
sub-folder per book). Uploads and scratch files live in the OS temp dir. The folder is user-configurable from the web UI (with
a native "Browse..." dialog) and persists across restarts in a small JSON
file next to this module.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "narratix_settings.json"
DEFAULT_DATA_DIR = Path.home() / "Narratix Audiobooks"
WORK_DIR = Path(tempfile.gettempdir()) / "narratix"


class Settings:
    def __init__(self) -> None:
        self.data_dir = self._load_data_dir()
        self._ensure_dirs()

    def _load_data_dir(self) -> Path:
        env_dir = os.environ.get("NARRATIX_DATA_DIR")
        if env_dir:
            return Path(env_dir).expanduser()
        if CONFIG_PATH.exists():
            try:
                cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                if cfg.get("data_dir"):
                    return Path(cfg["data_dir"]).expanduser()
            except Exception:
                pass
        return DEFAULT_DATA_DIR

    def _ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def uploads_dir(self) -> Path:
        return WORK_DIR / "uploads"

    @property
    def jobs_dir(self) -> Path:
        return WORK_DIR / "jobs"

    def set_data_dir(self, new_dir: Path) -> None:
        """Switch to a new data folder, validating it's usable, and persist the choice."""
        new_dir = Path(new_dir).expanduser()
        new_dir.mkdir(parents=True, exist_ok=True)

        probe = new_dir / ".narratix_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()

        self.data_dir = new_dir
        self._ensure_dirs()
        CONFIG_PATH.write_text(json.dumps({"data_dir": str(new_dir)}, indent=2), encoding="utf-8")

    def is_default(self) -> bool:
        return self.data_dir.resolve() == DEFAULT_DATA_DIR.resolve()


def pick_folder_dialog() -> Optional[str]:
    """Opens a native OS folder picker (blocking) and returns the chosen path, or None if canceled.
    Only meant to be called from a worker thread, never the asyncio event loop."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        path = filedialog.askdirectory(title="Choose a folder for Narratix data")
    finally:
        root.destroy()
    return path or None


settings = Settings()
