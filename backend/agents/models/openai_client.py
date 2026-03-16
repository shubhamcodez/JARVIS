"""OpenAI API: chat, classification, vision for desktop agent."""
import json
import re
from typing import Optional

from openai import OpenAI

# Use GPT-4o family; override via env OPENAI_CHAT_MODEL / OPENAI_VISION_MODEL if needed
CHAT_MODEL = "gpt-4o"
VISION_MODEL = "gpt-4o"


def _client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def chat(api_key: str, message: str, attachment_paths: Optional[list[str]] = None) -> str:
    """Chat: text-only or with file uploads (Responses API / Completions)."""
    client = _client(api_key)
    user_content = _user_content(message, attachment_paths)
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": user_content}],
    )
    return (resp.choices[0].message.content or "No response.").strip()


def _user_content(message: str, attachment_paths: Optional[list[str]] = None) -> str:
    """Build user content string for chat (shared by chat and chat_stream)."""
    message = (message or "").strip()
    if attachment_paths:
        parts = []
        for path in attachment_paths:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                with open(path, "rb") as f:
                    content = f.read().decode("utf-8", errors="replace")
            name = path.split("/")[-1].split("\\")[-1] or "file"
            parts.append(f"[Contents of {name}]\n{content}")
        if parts:
            body = "\n\n".join(parts)
            if message:
                return f"{message}\n\nAttachments:\n{body}"
            return f"Please summarize or answer based on the attached documents.\n\n{body}"
    return message or "Hello."


def chat_stream(api_key: str, message: str, attachment_paths: Optional[list[str]] = None):
    """Chat with streaming: yields content chunks (str) as they arrive."""
    client = _client(api_key)
    user_content = _user_content(message, attachment_paths)
    stream = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": user_content}],
        stream=True,
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def classify_task(api_key: str, user_message: str) -> dict:
    """Classify user message as task (agent) or normal chat. Returns {is_task, goal}."""
    user_message = (user_message or "").strip()
    if not user_message:
        return {"is_task": False, "goal": None}

    system = """You are a classifier. The user is talking to an assistant that can either (1) chat normally (answer questions, summarize, discuss) or (2) perform actions on the computer (open URLs, navigate, click, fill forms, etc.).

If the user is clearly asking the assistant to DO something on the computer (e.g. "open example.com", "go to google and search for X", "navigate to that page"), reply with a JSON object only, no other text: {"is_task": true, "goal": "one clear sentence describing the task"}.

Otherwise (general question, chat, "what is X", "summarize this", "hello", or unclear), reply with: {"is_task": false, "goal": null}.

Output ONLY the JSON object, no markdown or explanation."""

    client = _client(api_key)
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
    )
    raw = (resp.choices[0].message.content or "").strip()
    # Strip ```json ... ```
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw)
    raw = raw.strip()
    try:
        out = json.loads(raw)
        return {"is_task": bool(out.get("is_task")), "goal": out.get("goal")}
    except json.JSONDecodeError:
        return {"is_task": False, "goal": None}


def vision_desktop_action(
    api_key: str,
    image_base64: str,
    goal: str,
    step: int,
    last_result: Optional[str] = None,
    image_width: Optional[int] = None,
    image_height: Optional[int] = None,
) -> dict:
    """Vision: screenshot + goal -> next action (click/type/scroll/done). Pass image_width/height for precise click coordinates."""
    coord_rule = (
        f"- The screenshot is exactly {image_width}×{image_height} pixels. For clicks, return \"x\" and \"y\" as integer pixel coordinates in this system: x from 0 to {image_width - 1}, y from 0 to {image_height - 1}. (0,0) is top-left. Give the center of the element to click."
        if (image_width and image_height and image_width > 0 and image_height > 0)
        else "- Coordinates: (0,0) is top-left. x increases right, y increases down. Give pixel coordinates for the center of the element to click."
    )
    system = """You control the user's desktop by looking at a screenshot and deciding the next mouse/keyboard action.

RULES:
- Goal is given below. Perform ONE step at a time.
- On Windows: taskbar is usually at the BOTTOM of the screen. Icons (Chrome, etc.) are on the taskbar. The search bar (Type here to search) is on the taskbar, often left or center.
- If the app icon (e.g. Chrome) is visible on the taskbar: reply with action "click" and the (x,y) of that icon's center.
- If the app is NOT on the taskbar: use action "click" to click the taskbar search box first (give its center x,y), then on the next step use action "type" with the app name, then click the search result.
"""
    system += coord_rule + """

- Reply with ONLY a JSON object, no markdown or other text. Include "thought": a 1–2 sentence explanation. Format:
{"action": "click"|"type"|"scroll"|"done", "x": number or null, "y": number or null, "text": string or null, "scroll_amount": number or null, "description": "what you're doing", "thought": "what you see and why you're doing this"}
- Use "done" when the goal is achieved. For "done", set thought to a brief summary.
- Use "type" to type text. Use "click" to click at (x,y). Use "scroll" with scroll_amount (positive = scroll down)."""

    text = f"Goal: {goal}. Step {step}. "
    if last_result:
        text += f"Last action result: {last_result} "
    text += "Reply with ONLY the JSON object."

    client = _client(api_key)
    resp = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                ],
            },
        ],
        max_tokens=500,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw)
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"action": "done", "description": "Parse error", "thought": raw or "Unknown"}
