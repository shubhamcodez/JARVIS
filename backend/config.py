"""Load env (secrets), paths, and jarvis-config.yaml (provider + app settings)."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Repo root (parent of backend/)
_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_ROOT = Path(__file__).resolve().parent
load_dotenv(_REPO_ROOT / ".env")

CONFIG_YAML = _BACKEND_ROOT / "jarvis-config.yaml"

# Legacy paths at repo root (used only if jarvis-config.yaml is missing)
_LEGACY_LLM_PROVIDER_FILE = _REPO_ROOT / "jarvis-llm-provider.txt"
_LEGACY_GREP_ROOT_FILE = _REPO_ROOT / "jarvis-grep-root.txt"


_DEFAULTS: dict[str, Any] = {
    "llm_provider": "openai",
    "chat": {
        "history_limit": 120,
        "memory_query_recent_turns": 12,
    },
    "grep": {
        "default_root": None,
    },
}


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def _load_raw_user_config() -> dict[str, Any]:
    """YAML file if present; otherwise legacy .txt files at repo root."""
    if CONFIG_YAML.exists():
        with CONFIG_YAML.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    legacy: dict[str, Any] = {}
    if _LEGACY_LLM_PROVIDER_FILE.exists():
        p = _LEGACY_LLM_PROVIDER_FILE.read_text(encoding="utf-8").strip().lower()
        if p in ("openai", "xai"):
            legacy["llm_provider"] = p
    if _LEGACY_GREP_ROOT_FILE.exists():
        s = _LEGACY_GREP_ROOT_FILE.read_text(encoding="utf-8").strip()
        if s:
            legacy.setdefault("grep", {})["default_root"] = s
    return legacy


def _merged_config() -> dict[str, Any]:
    return _deep_merge(copy.deepcopy(_DEFAULTS), _load_raw_user_config())


def get_llm_provider() -> str:
    """Current LLM provider: 'openai' or 'xai'. From jarvis-config.yaml (or legacy txt if no yaml)."""
    prov = str(_merged_config().get("llm_provider") or "openai").strip().lower()
    return prov if prov in ("openai", "xai") else "openai"


def set_llm_provider(provider: str) -> None:
    """Set LLM provider to 'openai' or 'xai'; writes jarvis-config.yaml."""
    p = (provider or "").strip().lower()
    if p not in ("openai", "xai"):
        raise ValueError("provider must be 'openai' or 'xai'")
    CONFIG_YAML.parent.mkdir(parents=True, exist_ok=True)
    raw: dict[str, Any] = {}
    if CONFIG_YAML.exists():
        with CONFIG_YAML.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    raw["llm_provider"] = p
    merged = _deep_merge(copy.deepcopy(_DEFAULTS), raw)
    with CONFIG_YAML.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            merged,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


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
    return _REPO_ROOT / "jarvis-chats-dir.txt"


def chats_dir() -> Path:
    """Directory where chat logs are stored."""
    p = chats_config_path()
    if p.exists():
        s = p.read_text(encoding="utf-8").strip()
        if s:
            d = Path(s)
            if d.is_dir() or not d.exists():
                return d
    return _REPO_ROOT / "chats"


def get_grep_root() -> Path | None:
    """
    Optional default search root for file grep: jarvis-config.yaml grep.default_root,
    or legacy jarvis-grep-root.txt if yaml is missing.
    """
    raw = (_merged_config().get("grep") or {}).get("default_root")
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    p = Path(s).expanduser().resolve()
    return p if p.is_dir() else None


def get_chat_history_limit() -> int:
    """Max chat log messages sent to the LLM each turn (clamped 1–500)."""
    v = (_merged_config().get("chat") or {}).get("history_limit", 120)
    try:
        n = int(v)
        return max(1, min(n, 500))
    except (TypeError, ValueError):
        return 120


def get_memory_query_recent_turns() -> int:
    """Recent messages folded into vector-memory retrieval query (clamped 1–80)."""
    v = (_merged_config().get("chat") or {}).get("memory_query_recent_turns", 12)
    try:
        n = int(v)
        return max(1, min(n, 80))
    except (TypeError, ValueError):
        return 12
