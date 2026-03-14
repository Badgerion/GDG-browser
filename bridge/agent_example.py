"""
Graphic Density — Example Agent Loop

Demonstrates the core execution cycle:
  1. Get page state (graphic density map + registry)
  2. Send to any LLM with the task
  3. Parse the model's action
  4. Execute via the extension
  5. Repeat until done

Uses Anthropic's API as the example, but swap in any model.
"""

import json
import os
from gd_client import GraphicDensity

# pip install anthropic
import anthropic

SYSTEM_PROMPT = """You are a browser automation agent. You interact with web pages through a spatial text representation.

You will receive:
- A character-grid map showing the page layout
- A numbered registry of interactive elements with coordinates
- Scroll context showing your position on the page

To interact, respond with a JSON action. Examples:
  {"action": "click", "element": 5}
  {"action": "fill", "element": 3, "value": "search query"}
  {"action": "scroll", "direction": "down"}
  {"action": "scroll", "container": 14, "direction": "down"}
  {"action": "done", "result": "Task completed successfully"}
  {"action": "fail", "reason": "Could not find the login button"}

Rules:
- Always respond with a single JSON object, nothing else
- Use element numbers from the registry
- If you need to see more of the page, scroll first
- When the task is complete, use the "done" action
- If the task is impossible, use the "fail" action
"""

def build_state_message(state):
    """Format page state for the model."""
    parts = []
    parts.append(f"URL: {state.get('url', 'unknown')}")
    parts.append(f"Title: {state.get('title', 'unknown')}")

    if state.get('scroll'):
        s = state['scroll']
        parts.append(f"Scroll: {s['scrollPercent']}% | Page {s['currentPage']}/{s['totalPages']}")

    parts.append(f"\n{state.get('map', '')}")

    if state.get('registry'):
        parts.append("\n── Element Registry ──")
        for e in state['registry']:
            line = f"  [{e['id']}] {e['type']:18s} {e.get('label', '')}"
            if e.get('scrollState'):
                sc = e['scrollState']
                line += f" [scroll: {sc['scrollPercent']}%]"
            parts.append(line)

    return "\n".join(parts)


def run_agent(task, start_url=None, max_steps=20, model="claude-sonnet-4-20250514"):
    """Run an agent loop to complete a task."""

    gd = GraphicDensity()
    client = anthropic.Anthropic()

    # Navigate to start URL if provided
    if start_url:
        print(f"Navigating to {start_url}...")
        nav = gd.navigate(start_url)
        state = nav.get("state", gd.state())
    else:
        state = gd.state()

    messages = []
    total_tokens = 0

    for step in range(max_steps):
        # Build the user message with current state
        state_text = build_state_message(state)
        user_msg = f"Task: {task}\n\nCurrent page state:\n{state_text}"

        if step == 0:
            messages.append({"role": "user", "content": user_msg})
        else:
            messages.append({"role": "user", "content": f"Action executed. New state:\n{state_text}"})

        # Ask the model
        response = client.messages.create(
            model=model,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        assistant_text = response.content[0].text
        messages.append({"role": "assistant", "content": assistant_text})
        total_tokens += response.usage.input_tokens + response.usage.output_tokens

        # Parse action
        try:
            action = json.loads(assistant_text.strip())
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            match = re.search(r'\{[^}]+\}', assistant_text)
            if match:
                action = json.loads(match.group())
            else:
                print(f"Step {step + 1}: Could not parse action: {assistant_text[:100]}")
                continue

        print(f"Step {step + 1}: {json.dumps(action)}")

        # Check for terminal actions
        if action.get("action") == "done":
            print(f"\n✓ Task completed: {action.get('result', 'No details')}")
            print(f"  Steps: {step + 1} | Tokens: {total_tokens:,}")
            return {"success": True, "steps": step + 1, "tokens": total_tokens, "result": action.get("result")}

        if action.get("action") == "fail":
            print(f"\n✗ Task failed: {action.get('reason', 'No details')}")
            print(f"  Steps: {step + 1} | Tokens: {total_tokens:,}")
            return {"success": False, "steps": step + 1, "tokens": total_tokens, "reason": action.get("reason")}

        # Execute the action
        result = gd.action(action)

        if not result.get("success"):
            print(f"  Action failed: {result.get('error')}")

        # Get new state from action result, or re-fetch
        state = result.get("newState") or gd.state()

    print(f"\n✗ Max steps ({max_steps}) reached")
    return {"success": False, "steps": max_steps, "tokens": total_tokens, "reason": "max_steps"}


# ── Example Usage ─────────────────────────────────────────────────

if __name__ == "__main__":
    # Example: Search for something on GitHub
    result = run_agent(
        task="Search for 'graphic density' on GitHub and tell me how many results there are",
        start_url="https://github.com",
        max_steps=10,
    )

    print(f"\nFinal result: {json.dumps(result, indent=2)}")
