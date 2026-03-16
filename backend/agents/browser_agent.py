"""Browser agent: Playwright-based control — open URL, describe page, execute click/type/scroll from LLM."""
from __future__ import annotations

import asyncio
import base64
import json
import re
from typing import Optional

from openai import OpenAI

from config import get_openai_api_key

# Max steps per browser session
DEFAULT_MAX_STEPS = 10

# JS to get a compact list of interactive elements for the LLM
PAGE_SUMMARY_SCRIPT = """
() => {
  const items = [];
  const sel = 'a[href], button, input, textarea, [role="button"], [role="link"], [role="textbox"], [role="searchbox"], [contenteditable="true"]';
  document.querySelectorAll(sel).forEach((el, i) => {
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute('role') || (tag === 'a' ? 'link' : tag === 'input' ? 'textbox' : tag);
    const name = el.getAttribute('aria-label') || el.textContent?.trim().slice(0, 80) || el.value?.slice(0, 40) || el.placeholder || '';
    const placeholder = el.getAttribute('placeholder') || '';
    const type = el.getAttribute('type') || (tag === 'input' ? 'text' : '');
    const href = el.getAttribute('href') || '';
    if (!name && !placeholder && !href && type !== 'submit') return;
    items.push({ i, role, name: name.slice(0, 60), placeholder: placeholder.slice(0, 40), type, href: href.slice(0, 80) });
  });
  return JSON.stringify({ title: document.title, url: window.location.href, items });
}
"""


def _extract_url_from_goal(goal: str) -> Optional[str]:
    """Extract a URL from the goal text, or build one for common intents."""
    goal_lower = goal.lower().strip()
    # Explicit URL
    m = re.search(r"https?://[^\s]+", goal_lower, re.IGNORECASE)
    if m:
        return m.group(0).rstrip(".,;:)")
    # "open example.com" -> https://example.com
    m = re.search(r"(?:open|go to|navigate to)\s+([a-z0-9][-a-z0-9.]*\.[a-z]{2,})(?:\s|$)", goal_lower)
    if m:
        return "https://" + m.group(1)
    # "search google for X" or "google X"
    if "search google" in goal_lower or goal_lower.startswith("google "):
        q = re.sub(r"(?:search google for|google)\s+", "", goal_lower).strip()
        from urllib.parse import quote_plus
        return f"https://www.google.com/search?q={quote_plus(q)}"
    return None


def _get_next_browser_action(api_key: str, goal: str, page_summary: str, step: int, last_result: Optional[str]) -> dict:
    """Ask OpenAI for the next browser action given page summary and goal."""
    system = """You are a browser automation assistant. You receive a JSON summary of the current page (title, url, and a list of interactive elements with index i, role, name, placeholder, type, href).

Your task: choose ONE action to get closer to the user's goal. Reply with ONLY a JSON object, no markdown or explanation.

Actions:
- {"action": "click", "index": N} — click the element at index N (from the items list)
- {"action": "type", "index": N, "text": "..."} — type into the element at index N (e.g. search box, input)
- {"action": "scroll", "direction": "up"|"down"} — scroll the page
- {"action": "done", "summary": "..."} — goal is achieved; provide a one-line summary

Use the "items" array indexes (field "i") to refer to elements. Prefer clicking links/buttons by index, and typing into inputs by index. If the goal is already achieved, respond with action "done"."""

    user = f"Goal: {goal}\nStep: {step}\n"
    if last_result:
        user += f"Last result: {last_result}\n"
    user += f"Current page:\n{page_summary}\n\nReply with ONLY the JSON object."

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=300,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"action": "done", "summary": "Could not parse response."}


async def run_browser_agent(
    goal: str,
    max_steps: int = DEFAULT_MAX_STEPS,
    on_step=None,
    headless: bool = False,
) -> str:
    """
    Run the browser agent: extract URL, open in Playwright, then loop (page summary -> LLM -> action) until done.
    on_step(step, thought, action, description, result, done) is called for each step.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return "Playwright is not installed. Run: poetry add playwright && poetry run playwright install chromium"

    api_key = get_openai_api_key()
    url = _extract_url_from_goal(goal)
    if not url:
        return f"I couldn't find a URL in the goal: \"{goal}\". Try saying e.g. \"open https://example.com\" or \"search google for weather\"."

    trace = []
    last_result: Optional[str] = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            trace.append(f"Opened {url}")
            if on_step:
                try:
                    shot = await page.screenshot(type="png")
                    shot_b64 = base64.b64encode(shot).decode("ascii")
                except Exception:
                    shot_b64 = None
                on_step(1, f"Opened {url}", "navigate", f"Opened {url}", None, False, screenshot_base64=shot_b64)
            step = 2
            while step <= max_steps:
                try:
                    page_summary = await page.evaluate(PAGE_SUMMARY_SCRIPT)
                except Exception as e:
                    last_result = str(e)
                    trace.append(f"Error getting page: {e}")
                    break

                try:
                    shot = await page.screenshot(type="png")
                    shot_b64 = base64.b64encode(shot).decode("ascii")
                except Exception:
                    shot_b64 = None

                action_obj = await asyncio.to_thread(
                    _get_next_browser_action, api_key, goal, page_summary, step, last_result
                )
                act = (action_obj.get("action") or "done").lower()

                thought = action_obj.get("summary") or action_obj.get("thought") or act
                desc = f"Action: {act}"

                if act == "done":
                    trace.append(f"Done: {action_obj.get('summary', '')}")
                    if on_step:
                        on_step(step, thought, "done", desc, action_obj.get("summary"), True, screenshot_base64=shot_b64)
                    break

                result_msg = None
                try:
                    if act == "click":
                        idx = action_obj.get("index", 0)
                        # Click by index: we need to map index back to selector
                        selector = f"a[href], button, input, textarea, [role=button], [role=link], [role=textbox], [role=searchbox], [contenteditable=true]"
                        loc = page.locator(selector).nth(idx)
                        await loc.click(timeout=5000)
                        result_msg = f"Clicked element {idx}"
                    elif act == "type":
                        idx = action_obj.get("index", 0)
                        text = action_obj.get("text", "")
                        selector = "a[href], button, input, textarea, [role=button], [role=link], [role=textbox], [role=searchbox], [contenteditable=true]"
                        loc = page.locator(selector).nth(idx)
                        await loc.fill(text, timeout=5000)
                        result_msg = f"Typed into element {idx}"
                    elif act == "scroll":
                        direction = action_obj.get("direction", "down")
                        if direction == "up":
                            await page.mouse.wheel(0, -400)
                        else:
                            await page.mouse.wheel(0, 400)
                        result_msg = f"Scrolled {direction}"
                except Exception as e:
                    result_msg = f"Error: {e}"

                last_result = result_msg
                trace.append(f"Step {step}: {desc} → {result_msg}")
                if on_step:
                    try:
                        shot_after = await page.screenshot(type="png")
                        shot_after_b64 = base64.b64encode(shot_after).decode("ascii")
                    except Exception:
                        shot_after_b64 = None
                    on_step(step, thought, act, desc, result_msg, False, screenshot_base64=shot_after_b64)
                step += 1
                await asyncio.sleep(0.5)
        finally:
            await browser.close()

    return "Browser task:\n\n" + "\n".join(trace)
