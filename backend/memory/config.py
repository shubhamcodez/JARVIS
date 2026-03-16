"""Paths for memory stores (chunks, working state, Chroma)."""
from pathlib import Path

# Project root (parent of backend)
_ROOT = Path(__file__).resolve().parent.parent.parent  # memory -> backend -> project root
MEMORY_DIR = _ROOT / "jarvis-memory"
CHUNKS_DB = MEMORY_DIR / "chunks.db"
WORKING_STATE_DB = MEMORY_DIR / "working_state.db"
CHROMA_DIR = MEMORY_DIR / "chroma"


def ensure_memory_dir() -> None:
    """Create memory directory and Chroma dir if missing."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
