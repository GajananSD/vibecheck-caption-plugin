"""Settings, read from .env / environment."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
# VibeCheck gives us 5 s in total; keep the LLM well under that.
GEMINI_TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT_S", "3.0"))
USE_GEMINI = os.getenv("USE_GEMINI", "1") == "1" and bool(GEMINI_API_KEY)

DB_PATH = os.getenv("PLUGIN_DB_PATH", str(BASE_DIR / "captions.db"))
# Re-download a team's posts from VibeCheck at most this often.
POSTS_REFRESH_S = int(os.getenv("POSTS_REFRESH_S", "1800"))
FETCH_POSTS = os.getenv("FETCH_POSTS", "1") == "1"
# Override the api_base VibeCheck sends (e.g. it says localhost but runs on another laptop).
VIBECHECK_API_BASE = os.getenv("VIBECHECK_API_BASE", "").strip()

N_CAPTIONS = 4
# Every caption gets at least this many hashtags / emojis, even if the team's
# past captions use fewer (more are used when the team's habit is higher).
MIN_HASHTAGS = int(os.getenv("MIN_HASHTAGS", "2"))
MIN_EMOJIS = int(os.getenv("MIN_EMOJIS", "1"))
# Caption length floor/ceiling in words (hashtags not counted). A team whose past
# captions are shorter than MIN_WORDS still gets full Instagram-style captions.
MIN_WORDS = int(os.getenv("MIN_WORDS", "15"))
MAX_WORDS = int(os.getenv("MAX_WORDS", "40"))
