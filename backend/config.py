"""Load env and config paths."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (parent of backend/)
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

def get_openai_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip().strip('"')
    if not key:
        raise ValueError("OPENAI_API_KEY not set. Add it to a .env file in the project root.")
    return key


def chats_config_path() -> Path:
    """Path to file storing custom chats directory."""
    return _ROOT / "jarvis-chats-dir.txt"


def chats_dir() -> Path:
    """Directory where chat logs are stored."""
    p = chats_config_path()
    if p.exists():
        s = p.read_text(encoding="utf-8").strip()
        if s:
            d = Path(s)
            if d.is_dir() or not d.exists():
                return d
    return _ROOT / "chats"
