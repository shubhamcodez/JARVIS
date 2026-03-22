"""Supervisor agent: decides whether to run an agent at all, which one (desktop/coding/shell/finance), and the next steps."""
from __future__ import annotations

import json
import re
from typing import Optional

from agents.models import chat_completion_limit_kwargs, get_llm_client
from tools.shell_runner import is_shell_enabled

_SUPERVISOR_SYSTEM = """You are the JARVIS supervisor. You decide how to handle each user message.

You have five options:
1. **chat** – Answer with conversation only (questions, explanations, summarize, chat). No code execution or computer control. Use for web questions, links, "what is X", search-style questions answered in text (there is no separate Playwright browser agent).
2. **desktop** – Control the **GUI** with the **mouse cursor** and **keyboard**: click, double-click, right-click, type text, press keys (Enter, Tab, arrows, etc.), shortcuts (Ctrl+C, Alt+F4, …)—taskbar, apps, visible browser windows. Use when they need **physical** mouse/keyboard on their display.
3. **coding** – Run **Python in the sandbox**: math/scripts, **numpy/pandas**, **matplotlib** charts (headless), **yfinance inside code** when needed—regressions, correlations, backtests, simulations, “analyze with Python”. **NOT** desktop automation. Use **finance** (not coding) only for quick fetched data + prose, no custom analysis code.
4. **shell** – Run **real terminal / host shell** commands (mkdir, rm, ls, drives, git, npm, PowerShell, bash). Only when the user wants the **actual machine** shell—not the sandbox. **Requires** the server to have shell tools enabled; if unsure, prefer **chat** to explain.
5. **finance** – **Market data + short factual commentary** via **yfinance**: quotes, key stats, P/E, YTD, simple comparisons, dividends, fundamentals—**read out data and explain in prose**. If they want **plots, heavy statistics, or scripted analysis**, use **coding**.

Reply with ONLY a JSON object, no markdown or other text. Use this exact shape:
{
  "run_agent": true or false,
  "agent": "desktop" or "coding" or "shell" or "finance" or null,
  "goal": "one clear sentence describing the task" or null,
  "reasoning": "one sentence why you chose this",
  "next_steps": "short list of steps I will take"
}

Rules:
- Questions, hello, explain, summarize (no action): run_agent false, agent null, goal null.
- **Open a website / search Google / use a web app on their machine**: run_agent true, agent **"desktop"** if they need the on-screen browser automated; otherwise **chat** to give URLs, steps, or explanations.
- **Programming / run Python / script / factorial / calculate with code / execute code / matplotlib / pandas / plot or chart data**: run_agent true, agent **"coding"** — never "desktop" for these.
- **Terminal / mkdir / rm / list drives / bash / PowerShell / git clone / npm** on the host: run_agent true, agent **"shell"** (not desktop, not coding sandbox).
- **Stock price, ticker, P/E, market cap, dividend, simple compare NVDA vs AMD, SPY quote, BTC-USD** (data + explanation, no plots/code): run_agent true, agent **"finance"**. If they ask to **plot, regress, simulate, backtest, correlation matrix, run statistical analysis** on tickers → **"coding"** (not finance).
- Desktop when the user needs **mouse/keyboard on their screen** (taskbar, apps, visible browser windows).
- Be decisive. Output only valid JSON."""


def _finance_quant_coding_signals(low: str) -> bool:
    """
    True when the user wants scripted / quantitative / visual analysis on market data
    (coding agent), not a prose + yfinance summary (finance agent).
    """
    if any(
        k in low
        for k in (
            "matplotlib",
            "pyplot",
            "numpy",
            "pandas",
            "dataframe",
            "histogram",
            "scatter plot",
            "scatterplot",
            "regression",
            "correlation matrix",
            "linear regression",
            "logistic regression",
            "plot ",
            "chart ",
            "graph of",
            "rolling mean",
            "rolling average",
            "moving average",
            "bollinger",
            "backtest",
            "monte carlo",
            "sharpe",
            "drawdown",
            "simulate ",
            "simulation of",
            "covariance",
            "heatmap",
            "volatility of returns",
            "standard deviation of returns",
            "ARIMA",
            "cointegration",
        )
    ):
        return True
    if "correlation" in low and any(
        w in low for w in ("stock", "ticker", "equity", "return", "price", "portfolio", "spy", "etf", "nvda", "aapl", "msft")
    ):
        return True
    if "numpy" in low and any(
        w in low for w in ("stock", "ticker", "return", "price", "portfolio", "yfinance", "equity", "etf")
    ):
        return True
    if "pandas" in low and any(
        w in low
        for w in (
            "stock",
            "ticker",
            "return",
            "price",
            "portfolio",
            "yfinance",
            "equity",
            "etf",
            "aapl",
            "msft",
            "nvda",
            "tsla",
            "spy",
            "qqq",
        )
    ):
        return True
    analysis_phrases = (
        "run an analysis",
        "run analysis",
        "do an analysis",
        "code to analyze",
        "python to analyze",
        "analyze with python",
        "statistical analysis",
        "quantitative analysis",
    )
    if any(p in low for p in analysis_phrases) and any(
        w in low
        for w in (
            "stock",
            "ticker",
            "market",
            "return",
            "price",
            "equity",
            "portfolio",
            "etf",
            "spy",
            "yfinance",
            "aapl",
            "msft",
            "nvda",
            "tsla",
        )
    ):
        return True
    return False


def _heuristic_coding_task(message: str) -> Optional[dict]:
    """
    Strong signals for programmatic work; avoids sending "run a python script" to the desktop agent.
    Skips when the message looks like a URL-first browser task.
    """
    m = (message or "").strip()
    if not m:
        return None
    low = m.lower()
    if re.search(r"https?://\S+", low):
        return None
    # Browser-y phrases that mention python in URL context
    if "python.org" in low and "open" in low:
        return None

    if _finance_quant_coding_signals(low):
        return {
            "run_agent": True,
            "agent": "coding",
            "goal": m,
            "reasoning": "Heuristic: quantitative or visualization analysis (sandbox), not finance prose-only fetch.",
            "next_steps": "1. Plan analysis 2. Python (numpy/pandas/matplotlib/yfinance) 3. Sandbox run",
        }

    signals: list[tuple[str, bool]] = [
        ("python script", True),
        ("execute a python", True),
        ("execute python", True),
        ("run a python", True),
        ("run python script", True),
        ("run the script", True),
        ("factorial", True),
        ("write python", True),
        ("python code", True),
        ("in the sandbox", True),
        ("coding agent", True),
        (".py", "run" in low or "execute" in low),
        ("calculate", "python" in low),
        ("compute", "python" in low),
    ]
    for phrase, ok in signals:
        if not ok:
            continue
        if phrase in low:
            return {
                "run_agent": True,
                "agent": "coding",
                "goal": m,
                "reasoning": "Heuristic: task is code/computation (sandbox), not GUI desktop control.",
                "next_steps": "1. Generate Python for the goal 2. Run in sandbox 3. Return output",
            }
    return None


def _heuristic_shell_task(message: str) -> Optional[dict]:
    """Strong signals for host shell; only when JARVIS_ENABLE_SHELL is on."""
    if not is_shell_enabled():
        return None
    m = (message or "").strip()
    if not m:
        return None
    low = m.lower()
    hints = [
        "bash ",
        " in bash",
        "run bash",
        "powershell",
        "pwsh ",
        "terminal",
        "shell command",
        "command line",
        "mkdir ",
        "rmdir ",
        "rm -rf",
        "rm -r ",
        "wsl ",
        "diskpart",
        "which drive",
        "list drives",
        "list disk",
        "get-psdrive",
        "git clone",
        "git pull",
        "npm install",
        "pnpm ",
        "brew install",
        "apt install",
        "run in terminal",
        "execute ls",
        "run ls",
        "run dir",
    ]
    for h in hints:
        if h in low:
            return {
                "run_agent": True,
                "agent": "shell",
                "goal": m,
                "reasoning": "Heuristic: host terminal / filesystem / package command.",
                "next_steps": "1. Plan safe shell steps 2. Run commands in workdir 3. Summarize output",
            }
    return None


def _heuristic_finance_task(message: str) -> Optional[dict]:
    """Route stock/market data questions to the finance agent (yfinance)."""
    m = (message or "").strip()
    if not m:
        return None
    low = m.lower()
    if _finance_quant_coding_signals(low):
        return None

    hints = [
        "yfinance",
        "yahoo finance",
        "stock price",
        "share price",
        "market cap",
        "p/e ratio",
        "pe ratio",
        "dividend yield",
        "ticker",
        "nasdaq",
        "nyse",
        "s&p 500",
        "s&p500",
        "etf ",
        " mutual fund",
        "earnings",
        "quarterly revenue",
        "ytd performance",
        "52 week high",
        "52-week",
        "compare aapl",
        "btc-usd",
        "eth-usd",
        "how is nvda",
        "how is tsla",
        "quote for ",
        "price of ",
    ]
    if any(h in low for h in hints):
        return {
            "run_agent": True,
            "agent": "finance",
            "goal": m,
            "reasoning": "Heuristic: market/stock data and analysis (yfinance).",
            "next_steps": "1. Resolve tickers 2. Fetch yfinance 3. Analyze",
        }
    # Uppercase ticker + finance-ish words
    if re.search(r"\b[A-Z]{2,5}\b", m) and any(
        w in low for w in ("stock", "stocks", "equity", "trading", "invest", "portfolio", "quote", "chart")
    ):
        return {
            "run_agent": True,
            "agent": "finance",
            "goal": m,
            "reasoning": "Heuristic: ticker symbol + investment context.",
            "next_steps": "1. Resolve tickers 2. Fetch yfinance 3. Analyze",
        }
    return None


def supervisor_decision(api_key: str, provider: str, user_message: str) -> dict:
    """
    Ask the supervisor LLM to decide: chat vs desktop vs coding vs shell vs finance agent.
    Returns dict with: run_agent (bool), agent ("desktop"|"coding"|"shell"|"finance"|null), goal (str|null),
    reasoning (str), next_steps (str).
    """
    user_message = (user_message or "").strip()
    if not user_message:
        return {
            "run_agent": False,
            "agent": None,
            "goal": None,
            "reasoning": "",
            "next_steps": "",
        }

    hinted = _heuristic_coding_task(user_message)
    if hinted:
        g = (hinted.get("goal") or user_message).strip()
        return {
            "run_agent": True,
            "agent": "coding",
            "goal": g,
            "reasoning": str(hinted.get("reasoning") or ""),
            "next_steps": str(hinted.get("next_steps") or ""),
        }

    hinted_shell = _heuristic_shell_task(user_message)
    if hinted_shell:
        g = (hinted_shell.get("goal") or user_message).strip()
        return {
            "run_agent": True,
            "agent": "shell",
            "goal": g,
            "reasoning": str(hinted_shell.get("reasoning") or ""),
            "next_steps": str(hinted_shell.get("next_steps") or ""),
        }

    hinted_finance = _heuristic_finance_task(user_message)
    if hinted_finance:
        g = (hinted_finance.get("goal") or user_message).strip()
        return {
            "run_agent": True,
            "agent": "finance",
            "goal": g,
            "reasoning": str(hinted_finance.get("reasoning") or ""),
            "next_steps": str(hinted_finance.get("next_steps") or ""),
        }

    mod = get_llm_client(provider)
    client = mod._client(api_key)
    model = getattr(mod, "CHAT_MODEL", "gpt-4o")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SUPERVISOR_SYSTEM},
            {"role": "user", "content": user_message},
        ],
        **chat_completion_limit_kwargs(provider, model, 400),
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw)
    raw = raw.strip()
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "run_agent": False,
            "agent": None,
            "goal": None,
            "reasoning": "Could not parse supervisor response.",
            "next_steps": "",
        }

    run_agent = bool(out.get("run_agent"))
    agent = out.get("agent")
    if agent == "browser":
        agent = None
        run_agent = False
    elif agent not in ("desktop", "coding", "shell", "finance"):
        agent = None
    if agent == "shell" and not is_shell_enabled():
        agent = None
        run_agent = False
    if not run_agent:
        agent = None
    goal = (out.get("goal") or "").strip() or None
    if not goal and agent:
        goal = user_message

    reasoning = (out.get("reasoning") or "").strip()
    next_steps = (out.get("next_steps") or "").strip()

    # LLM sometimes picks desktop for pure coding tasks; never automate the GUI for these.
    if agent == "desktop":
        low = user_message.lower()
        coding_override = any(
            k in low
            for k in (
                "factorial",
                "python script",
                "execute python",
                "run python",
                "run a script",
                "write a program",
                "write python",
                "coding task",
                "in python",
                "sandbox",
            )
        ) or (".py" in low and ("run" in low or "execute" in low))
        if coding_override:
            agent = "coding"
            reasoning = (reasoning + " " if reasoning else "") + "(Rerouted to coding agent: programmatic task.)"

    # LLM sometimes picks desktop for mkdir / terminal-style tasks.
    if agent == "desktop" and is_shell_enabled():
        low = user_message.lower()
        shell_reroute = any(
            k in low
            for k in (
                "mkdir ",
                "rmdir ",
                "rm -",
                "bash",
                "powershell",
                "pwsh",
                "terminal",
                "wsl ",
                "diskpart",
                "git clone",
                "npm install",
                "pnpm ",
                "which drive",
                "list drives",
                "list disk",
                "get-psdrive",
                "shell command",
            )
        )
        if shell_reroute:
            agent = "shell"
            reasoning = (reasoning + " " if reasoning else "") + "(Rerouted to shell agent: terminal/filesystem task.)"

    if agent == "finance" and _finance_quant_coding_signals(user_message.lower()):
        agent = "coding"
        reasoning = (reasoning + " " if reasoning else "") + "(Rerouted to coding agent: scripted/plotted analysis.)"

    return {
        "run_agent": run_agent and agent is not None and bool(goal),
        "agent": agent,
        "goal": goal,
        "reasoning": reasoning.strip(),
        "next_steps": next_steps,
    }
