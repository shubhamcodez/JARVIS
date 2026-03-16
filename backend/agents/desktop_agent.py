"""Desktop agent: screenshot + vision model + pyautogui. Optional: only if pyautogui/mss available."""
import base64
from typing import Optional

from agents.models import get_llm_client
from observability.guards import should_stop_streak

try:
    import mss
    import mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


def capture_screen_base64() -> str:
    """Capture screen as PNG base64."""
    if not HAS_MSS:
        raise RuntimeError("mss not installed. pip install mss")
    with mss.mss() as sct:
        mon = sct.monitors[0]
        shot = sct.grab(mon)
        img = mss.tools.to_png(shot.rgb, shot.size)
    return base64.b64encode(img).decode("ascii")


def capture_screen_with_size() -> tuple[str, int, int]:
    """Capture screen as PNG base64 and return (base64_string, width, height) for precise coordinate mapping."""
    if not HAS_MSS:
        raise RuntimeError("mss not installed. pip install mss")
    with mss.mss() as sct:
        mon = sct.monitors[0]
        width = mon["width"]
        height = mon["height"]
        shot = sct.grab(mon)
        img = mss.tools.to_png(shot.rgb, shot.size)
    return base64.b64encode(img).decode("ascii"), width, height


def execute_action(action: dict) -> Optional[str]:
    """Execute one desktop action (click/type/scroll). Returns result message or None."""
    if not HAS_PYAUTOGUI:
        return "pyautogui not installed; skipping execution"
    act = (action.get("action") or "").lower()
    if act == "done":
        return None
    if act == "click":
        x = action.get("x")
        y = action.get("y")
        if x is None or y is None:
            return "Click requires x and y coordinates"
        x = int(round(float(x)))
        y = int(round(float(y)))
        pyautogui.click(x, y)
        return f"Clicked at ({x}, {y})"
    if act == "type":
        text = action.get("text") or ""
        pyautogui.write(text, interval=0.02)
        return f"Typed: {text}"
    if act == "scroll":
        amount = action.get("scroll_amount") or 3
        pyautogui.scroll(-amount)  # pyautogui: positive = up
        return f"Scrolled {amount}"
    return f"Unknown action: {act}"


def run_desktop_agent(
    goal: str,
    max_steps: int = 10,
    on_step=None,
    api_key: Optional[str] = None,
    provider: str = "openai",
) -> str:
    """
    Run desktop agent loop: screenshot -> vision -> execute -> emit step.
    on_step(step, thought, action, description, result, done, screenshot_base64=None) is called each step.
    """
    if api_key is None:
        from config import get_llm_api_key
        api_key = get_llm_api_key()
    client = get_llm_client(provider)
    trace = []
    last_result: Optional[str] = None
    achieved = False
    action_history = []

    for step in range(1, max_steps + 1):
        image_b64, screen_width, screen_height = capture_screen_with_size()
        action = client.vision_desktop_action(
            api_key, image_b64, goal, step, last_result,
            image_width=screen_width, image_height=screen_height,
        )

        thought = action.get("thought") or action.get("description") or action.get("action")
        desc = action.get("description") or action.get("action")
        act = (action.get("action") or "").lower()

        trace.append(f"Step {step} — Thought: {thought}\n  Action: {desc}")

        if act == "done":
            trace.append("Goal achieved.")
            achieved = True
            if on_step:
                on_step(step, thought, "done", desc, None, True, screenshot_base64=image_b64)
            break

        action_history.append({"action": act, "thought": thought})
        if should_stop_streak(act, thought, action_history, streak_limit=3):
            trace.append("Loop guard: repeated action; stopping.")
            if on_step:
                on_step(step, thought, "done", "Stopped (repeated action)", None, True, screenshot_base64=image_b64)
            break

        result = execute_action(action)
        if result:
            last_result = result
            trace.append(f"  → {result}")

        if on_step:
            on_step(step, thought, action.get("action"), desc, last_result, False, screenshot_base64=image_b64)

    if not achieved:
        trace.append(f"Stopped after {max_steps} steps (goal not yet achieved).")

    return f"Desktop task (goal: {goal}).\n\nAgent thought process:\n\n" + "\n\n".join(trace)
