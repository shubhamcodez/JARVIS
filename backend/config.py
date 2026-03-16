"""Load env and config paths."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (parent of backend/)
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

# LLM provider: "openai" or "xai"
LLM_PROVIDER_FILE = _ROOT / "jarvis-llm-provider.txt"


def get_llm_provider() -> str:
    """Current LLM provider: 'openai' or 'xai'. Default openai."""
    if LLM_PROVIDER_FILE.exists():
        p = LLM_PROVIDER_FILE.read_text(encoding="utf-8").strip().lower()
        if p in ("openai", "xai"):
            return p
    return "openai"


def set_llm_provider(provider: str) -> None:
    """Set LLM provider to 'openai' or 'xai'."""
    p = (provider or "").strip().lower()
    if p not in ("openai", "xai"):
        raise ValueError("provider must be 'openai' or 'xai'")
    LLM_PROVIDER_FILE.parent.mkdir(parents=True, exist_ok=True)
    LLM_PROVIDER_FILE.write_text(p, encoding="utf-8")


def get_openai_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip().strip('"')
    if not key:
        raise ValueError("OPENAI_API_KEY not set. Add it to a .env file in the project root.")
    return key


def get_xai_api_key() -> str:
    key = (
        os.environ.get("xAI_API_KEY") or os.environ.get("XAI_API_KEY") or ""
    ).strip().strip('"')
    if not key:
        raise ValueError("xAI_API_KEY not set. Add it to a .env file in the project root.")
    return key


def get_llm_api_key() -> str:
    """API key for the current LLM provider."""
    if get_llm_provider() == "xai":
        return get_xai_api_key()
    return get_openai_api_key()


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
