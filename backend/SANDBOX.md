# Python sandbox (coding agent)

The coding agent runs model-generated Python in a **child process** with a **timeout**, restricted **builtins**, and an **import allowlist** (`tools/sandbox_worker.py`).

## Allowed packages (high level)

- **Stdlib helpers:** `math`, `json`, `itertools`, `collections`, `statistics`, `datetime`, `random`, `re`, `io`, `base64`, `csv`, `hashlib`, `typing`, `warnings`, and related small stdlib modules used by HTTP clients.
- **Data / charts / market data:** `numpy`, `pandas`, `matplotlib` (set **`MPLBACKEND=Agg`** in the runner for headless use), `yfinance`, plus their typical dependencies (`requests`, `urllib3`, `lxml`, `curl_cffi`, etc.).

`tools/python_sandbox.py` sets `MPLBACKEND=Agg` so plots do not require a display.

## Security

This is **not** a cryptographic sandbox. Allowing **HTTP** (yfinance / requests) means outbound network access from the worker. Do not expose to untrusted users without extra isolation (VM/container).

## Timeouts

The coding agent uses a **45s** sandbox timeout by default (network fetches can be slow).
