"""
Market data via yfinance for the finance agent (JSON-serializable summaries).
Not financial advice; data may be delayed or incomplete.
"""
from __future__ import annotations

from typing import Any

_VALID_PERIODS = frozenset({"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"})
_VALID_INTERVALS = frozenset({"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"})

_INFO_KEYS = [
    "symbol",
    "shortName",
    "longName",
    "currency",
    "exchange",
    "quoteType",
    "sector",
    "industry",
    "marketCap",
    "enterpriseValue",
    "trailingPE",
    "forwardPE",
    "pegRatio",
    "priceToBook",
    "dividendYield",
    "dividendRate",
    "exDividendDate",
    "fiftyTwoWeekHigh",
    "fiftyTwoWeekLow",
    "200dayAverage",
    "50dayAverage",
    "beta",
    "targetMeanPrice",
    "recommendationKey",
    "totalRevenue",
    "revenuePerShare",
    "profitMargins",
    "operatingMargins",
    "returnOnEquity",
    "debtToEquity",
    "currentRatio",
    "earningsQuarterlyGrowth",
    "website",
    "longBusinessSummary",
]


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    return str(v)[:500]


def _trim_info(info: dict) -> dict:
    out: dict[str, Any] = {}
    for k in _INFO_KEYS:
        if k not in info:
            continue
        v = info[k]
        if v is None:
            continue
        out[k] = _jsonable(v)
    # Cap long text fields
    if "longBusinessSummary" in out and isinstance(out["longBusinessSummary"], str):
        s = out["longBusinessSummary"]
        if len(s) > 1200:
            out["longBusinessSummary"] = s[:1200] + "…"
    return out


def _normalize_period(p: str) -> str:
    x = (p or "6mo").strip().lower()
    return x if x in _VALID_PERIODS else "6mo"


def _normalize_interval(i: str) -> str:
    x = (i or "1d").strip().lower()
    return x if x in _VALID_INTERVALS else "1d"


def fetch_finance_bundle(
    tickers: list[str],
    *,
    history_period: str = "6mo",
    history_interval: str = "1d",
    include_financials: bool = False,
) -> dict[str, Any]:
    """
    Fetch one bundle per ticker: trimmed info, optional history stats, optional quarterly financials head.
    """
    import yfinance as yf

    period = _normalize_period(history_period)
    interval = _normalize_interval(history_interval)
    result: dict[str, Any] = {"tickers": [], "errors": [], "fetch_params": {"period": period, "interval": interval}}

    seen: set[str] = set()
    for raw in tickers[:8]:
        sym = (raw or "").strip().upper()
        if not sym or len(sym) > 10 or sym in seen:
            continue
        seen.add(sym)
        block: dict[str, Any] = {"symbol": sym}
        try:
            t = yf.Ticker(sym)
        except Exception as e:
            result["errors"].append({"symbol": sym, "error": str(e)})
            continue

        try:
            fi = getattr(t, "fast_info", None)
            if fi is not None:
                if hasattr(fi, "items"):
                    block["fast_info"] = {str(k): _jsonable(v) for k, v in fi.items()}
                else:
                    block["fast_info"] = _jsonable(fi) if fi else {}
        except Exception:
            block["fast_info"] = {}

        try:
            block["info"] = _trim_info(dict(t.info or {}))
        except Exception as e:
            block["info"] = {}
            block["info_error"] = str(e)

        try:
            hist = t.history(period=period, interval=interval)
            if hist is not None and not hist.empty:
                tail = hist.tail(200)
                close = tail["Close"] if "Close" in tail.columns else None
                block["history"] = {
                    "period": period,
                    "interval": interval,
                    "bars": len(tail),
                    "last_close": float(close.iloc[-1]) if close is not None and len(close) else None,
                    "first_close": float(close.iloc[0]) if close is not None and len(close) else None,
                    "high": float(tail["High"].max()) if "High" in tail.columns else None,
                    "low": float(tail["Low"].min()) if "Low" in tail.columns else None,
                    "volume_avg": float(tail["Volume"].mean()) if "Volume" in tail.columns else None,
                }
                cols = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in tail.columns]
                block["history_tail"] = tail[cols].round(4).tail(8).to_string()
        except Exception as e:
            block["history_error"] = str(e)

        if include_financials:
            try:
                qf = t.quarterly_financials
                if qf is not None and not qf.empty:
                    block["quarterly_financials_sample"] = qf.iloc[:12, :min(6, qf.shape[1])].to_string()[:4500]
            except Exception as e:
                block["financials_error"] = str(e)

        result["tickers"].append(block)

    return result
