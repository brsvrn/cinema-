"""Runtime configuration. All secrets come from environment variables only."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parent.parent
ASSETS = WORKER_ROOT / "assets"
FONTS = ASSETS / "fonts"
MODELS_DIR = Path(os.environ.get("STUDIO_MODELS_DIR", WORKER_ROOT / ".models"))
DATA_DIR = Path(os.environ.get("STUDIO_DATA_DIR", WORKER_ROOT / "data"))
WORK_DIR = Path(os.environ.get("STUDIO_WORK_DIR", WORKER_ROOT / "work"))

FPS = int(os.environ.get("STUDIO_FPS", "30"))
SAMPLE_RATE = 48000

# --- external services (all optional; engine degrades to free/local paths) ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "studio")

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY", "")
RUNPOD_ENDPOINT_ID = os.environ.get("RUNPOD_ENDPOINT_ID", "")
# GPU / paid engines must be explicitly allowed (user approval) even if keys exist.
ALLOW_PAID = os.environ.get("STUDIO_ALLOW_PAID", "0") == "1"


def supabase_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def r2_enabled() -> bool:
    return bool(R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET)


def font_path(bold: bool = True) -> str:
    f = FONTS / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    return str(f)


def rhubarb_bin() -> str | None:
    env = os.environ.get("RHUBARB_BIN")
    if env and Path(env).exists():
        return env
    cand = MODELS_DIR / "rhubarb" / "rhubarb"
    if cand.exists():
        return str(cand)
    return shutil.which("rhubarb")


def ffmpeg_bin() -> str:
    return os.environ.get("FFMPEG_BIN", shutil.which("ffmpeg") or "ffmpeg")
