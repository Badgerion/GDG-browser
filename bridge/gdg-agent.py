#!/usr/bin/env python3
"""
GDG Universal Browser Agent
One script. Any model. Any task.

Usage:
  python gdg-agent.py "Find trending repos on GitHub"
  python gdg-agent.py --model groq/llama-3.3-70b-versatile "Search for USB-C cables on Amazon"
  python gdg-agent.py --model ollama/llama3 "What's on Hacker News right now?"
  python gdg-agent.py --model openai/gpt-4o "Navigate to my Gmail and count unread emails"
  python gdg-agent.py --model anthropic/claude-sonnet-4-20250514 "Go to GitHub and star the top trending repo"
  python gdg-agent.py --model sambanova/Meta-Llama-3.1-70B-Instruct "Check the weather in Victoria BC"
  python gdg-agent.py --model gemini/gemini-2.0-flash "Find the cheapest flight to London on Google Flights"

Supported providers:
  anthropic/*     (needs ANTHROPIC_API_KEY)
  openai/*        (needs OPENAI_API_KEY)
  groq/*          (needs GROQ_API_KEY)
  ollama/*        (needs ollama running locally)
  sambanova/*     (needs SAMBANOVA_API_KEY)
  gemini/*        (needs GOOGLE_API_KEY or GEMINI_API_KEY)

The GDG bridge must be running on localhost:7080.
"""

import argparse
import json
import os
import re
import sys
import requests

# ── GDG Bridge Client ─────────────────────────────────────────────

BRIDGE = "http://127.0.0.1:7080"

def gdg_state(mode="numbered"):
    r = requests.get(f"{BRIDGE}/state", params={"mode": mode}, timeout=30)
    return r.json()

def gdg_action(action):
    r = requests.post(f"{BRIDGE}/action", json=action, timeout=30)
    return r.json()

def gdg_navigate(url):
    r = requests.post(f"{BRIDGE}/navigate", json={"url": url}, timeout=30)
    return r.json()

def gdg_health():
    try:
        r = requests.get(f"{BRIDGE}/health", timeout=3)
        return r.json()
    except:
        return None

# ── State Formatting ──────────────────────────────────────────────

def format_state(state):
    parts = []
    parts.append(f"URL: {state.get('url', '?')}")
    parts.append(f"Title: {state.get('title', '?')}")

    scroll = state.get("scroll", {})
    if scroll:
        parts.append(f"Scroll: {scroll.get('scrollPercent', 0)}% | Page {scroll.get('currentPage', 1)}/{scroll.get('totalPages', 1)}")

    parts.append("")
    parts.append(state.get("map", ""))

    registry = state.get("registry", [])
    if registry:
        parts.append("\n── Elements ──")
        for e in registry:
            line = f"  [{e['id']}] {e['type']:15s} {e.get('label', '')}"
            if e.get("actions"):
                line += f"  {', '.join(e['actions'])}"
            parts.append(line)

    if state.get("content"):
        parts.append("\n── Page content ──")
        parts.append(state["content"][:3000])

    if state.get("tables"):
        parts.append("\n── Tables ──")
        parts.append(state["tables"][:2000])

    return "\n".join(parts)

# ── System Prompt ─────────────────────────────────────────────────

SYSTEM = """You are a browser automation agent. You control a real Chrome browser through a spatial text representation.

You receive a text map showing page layout and a numbered registry of interactive elements.

Respond with ONLY a JSON object. Available actions:

{"action": "click", "element": 5}
{"action": "fill", "element": 3, "value": "search text"}
{"action": "select", "element": 7, "value": "Option"}
{"action": "scroll", "direction": "down"}
{"action": "scroll", "container": 14, "direction": "down"}
{"action": "keypress", "key": "Enter"}
{"action": "back"}
{"action": "navigate", "url": "https://..."}
{"action": "switch_mode", "mode": "read"}
{"action": "answer", "value": "The answer is..."}
{"action": "done", "value": "Task completed"}

Rules:
- Respond with ONLY a JSON object, no other text
- Use element numbers from the registry
- Use "navigate" to go to websites
- Use "switch_mode" with "read" when you need to read text content on the page
- When you have the answer, use "answer" immediately
- When the task is complete, use "done" immediately
- Be efficient — take the shortest path"""

# ── Provider Adapters ─────────────────────────────────────────────

def call_anthropic(model, messages, system):
    import anthropic
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=500,
        system=system,
        messages=messages,
    )
    return response.content[0].text.strip()

def call_openai(model, messages, system):
    from openai import OpenAI
    client = OpenAI()
    msgs = [{"role": "system", "content": system}] + messages
    response = client.chat.completions.create(
        model=model,
        messages=msgs,
        max_tokens=500,
    )
    return response.choices[0].message.content.strip()

def call_groq(model, messages, system):
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ.get("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )
    msgs = [{"role": "system", "content": system}] + messages
    response = client.chat.completions.create(
        model=model,
        messages=msgs,
        max_tokens=500,
    )
    return response.choices[0].message.content.strip()

def call_ollama(model, messages, system):
    msgs = [{"role": "system", "content": system}] + messages
    response = requests.post(
        "http://localhost:11434/api/chat",
        json={"model": model, "messages": msgs, "stream": False},
        timeout=120,
    )
    return response.json()["message"]["content"].strip()

def call_sambanova(model, messages, system):
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ.get("SAMBANOVA_API_KEY"),
        base_url="https://api.sambanova.ai/v1",
    )
    msgs = [{"role": "system", "content": system}] + messages
    response = client.chat.completions.create(
        model=model,
        messages=msgs,
        max_tokens=500,
    )
    return response.choices[0].message.content.strip()

def call_gemini(model, messages, system):
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    # Convert messages to Gemini format
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    response = requests.post(url, json={
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 500},
    }, timeout=60)

    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()

PROVIDERS = {
    "anthropic": call_anthropic,
    "openai": call_openai,
    "groq": call_groq,
    "ollama": call_ollama,
    "sambanova": call_sambanova,
    "gemini": call_gemini,
}

# ── Action Parser ─────────────────────────────────────────────────

def parse_action(text):
    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown code blocks
    text_clean = text
    if "```" in text_clean:
        text_clean = re.sub(r'```(?:json)?\s*', '', text_clean)
        text_clean = text_clean.replace('```', '')
        try:
            return json.loads(text_clean.strip())
        except json.JSONDecodeError:
            pass

    # Try finding JSON object in the text
    match = re.search(r'\{[^{}]+\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None

# ── Agent Loop ────────────────────────────────────────────────────

def run(task, provider, model, max_steps=25, start_url=None, verbose=True):
    # Verify bridge
    health = gdg_health()
    if not health or not health.get("extensionConnected"):
        print("✗ GDG bridge not connected. Is the Chrome extension running?")
        sys.exit(1)

    if verbose:
        print(f"\n{'='*60}")
        print(f"  Task: {task}")
        print(f"  Model: {provider}/{model}")
        print(f"{'='*60}\n")

    # Navigate to start URL if provided
    if start_url:
        if verbose:
            print(f"  → Navigating to {start_url}")
        nav = gdg_navigate(start_url)
        state = nav.get("state") or gdg_state()
    else:
        state = gdg_state()

    current_mode = "numbered"
    messages = []
    call_fn = PROVIDERS[provider]

    for step in range(max_steps):
        # Format state for the model
        state_text = format_state(state)

        if step == 0:
            user_msg = f"Task: {task}\n\nCurrent page:\n{state_text}"
        else:
            user_msg = f"Page after action:\n{state_text}"

        messages.append({"role": "user", "content": user_msg})

        # Call the model
        try:
            response_text = call_fn(model, messages, SYSTEM)
        except Exception as e:
            if verbose:
                print(f"  Step {step+1}: Model error: {e}")
            break

        messages.append({"role": "assistant", "content": response_text})

        # Parse action
        action = parse_action(response_text)
        if not action:
            if verbose:
                print(f"  Step {step+1}: Could not parse: {response_text[:80]}")
            continue

        action_type = action.get("action", "?")

        if verbose:
            detail = action.get("value", action.get("element", action.get("direction", action.get("url", ""))))
            print(f"  Step {step+1}: {action_type} {detail}")

        # Terminal actions
        if action_type in ("answer", "done"):
            if verbose:
                print(f"\n  ✓ {action.get('value', 'Complete')}\n")
            return {"success": True, "steps": step + 1, "result": action.get("value")}

        if action_type == "fail":
            if verbose:
                print(f"\n  ✗ {action.get('reason', 'Failed')}\n")
            return {"success": False, "steps": step + 1, "reason": action.get("reason")}

        # Mode switch
        if action_type == "switch_mode":
            current_mode = action.get("mode", "read")
            state = gdg_state(mode=current_mode)
            if verbose:
                print(f"         → switched to {current_mode} mode")
            continue

        # Navigate
        if action_type == "navigate":
            nav = gdg_navigate(action["url"])
            state = nav.get("state") or gdg_state(mode=current_mode)
            continue

        # Execute action
        result = gdg_action(action)

        if not result.get("success"):
            if verbose:
                print(f"         ⚠ {result.get('error', 'Unknown error')}")

        # Get new state
        state = result.get("newState") or gdg_state(mode=current_mode)

    if verbose:
        print(f"\n  ✗ Max steps ({max_steps}) reached\n")
    return {"success": False, "steps": max_steps, "reason": "max_steps"}

# ── CLI ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="GDG Universal Browser Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "What's trending on GitHub?"
  %(prog)s --model groq/llama-3.3-70b-versatile "Search Amazon for headphones"
  %(prog)s --model ollama/llama3 "Check Hacker News front page"
  %(prog)s --model openai/gpt-4o "Find flights to Tokyo on Google Flights"
  %(prog)s --model gemini/gemini-2.0-flash "Go to Reddit and find top post on r/programming"

Providers: anthropic, openai, groq, ollama, sambanova, gemini
        """,
    )
    parser.add_argument("task", help="What to do in the browser")
    parser.add_argument("--model", "-m", default="anthropic/claude-sonnet-4-20250514",
                        help="provider/model (default: anthropic/claude-sonnet-4-20250514)")
    parser.add_argument("--url", "-u", help="Start URL to navigate to first")
    parser.add_argument("--steps", "-s", type=int, default=25, help="Max steps (default: 25)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")

    args = parser.parse_args()

    # Parse provider/model
    if "/" in args.model:
        provider, model = args.model.split("/", 1)
    else:
        # Default to anthropic if no provider prefix
        provider = "anthropic"
        model = args.model

    if provider not in PROVIDERS:
        print(f"Unknown provider: {provider}")
        print(f"Available: {', '.join(PROVIDERS.keys())}")
        sys.exit(1)

    result = run(
        task=args.task,
        provider=provider,
        model=model,
        max_steps=args.steps,
        start_url=args.url,
        verbose=not args.quiet,
    )

    if not args.quiet:
        print(f"  Result: {'✓' if result['success'] else '✗'} in {result['steps']} steps")


if __name__ == "__main__":
    main()
