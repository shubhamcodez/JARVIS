"""Paths for observability data (traces, evals, optimization)."""
from pathlib import Path

# Project root (parent of backend)
_ROOT = Path(__file__).resolve().parent.parent.parent
OBS_DIR = _ROOT / "jarvis-observability"
TRACES_DIR = OBS_DIR / "traces"
EVALS_DIR = OBS_DIR / "evals"
OPT_DIR = OBS_DIR / "optimization"


def ensure_dirs():
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    EVALS_DIR.mkdir(parents=True, exist_ok=True)
    OPT_DIR.mkdir(parents=True, exist_ok=True)
