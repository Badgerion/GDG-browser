"""
Graphic Density — WebArena Benchmark Harness

Loads WebArena tasks, drives the browser via Graphic Density,
uses an LLM for decisions, and produces output files compatible
with WebArena-Verified's evaluator.

Setup:
  1. WebArena sites running in Docker (shopping on :7770, etc.)
  2. Graphic Density extension loaded in Chrome + bridge running
  3. pip install anthropic requests

Usage:
  # Run a single task
  python benchmark.py --task-id 1

  # Run first 10 tasks
  python benchmark.py --start 0 --end 10

  # Run all shopping tasks
  python benchmark.py --site shopping

  # Run with a different model
  python benchmark.py --task-id 1 --model claude-sonnet-4-20250514
"""

import json
import os
import sys
import time
import argparse
from pathlib import Path

import requests

# Add bridge directory to path for gd_client
sys.path.insert(0, os.path.dirname(__file__))
from gd_client import GraphicDensity

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


# ── Configuration ─────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a web automation agent. You interact with websites through a spatial text map and numbered element registry.

You receive:
- A character-grid map showing page layout
- A numbered registry of interactive elements
- Scroll context (your position on the page)

Respond with a single JSON object. Available actions:

INTERACT WITH ELEMENTS:
  {"action": "click", "element": 5}
  {"action": "fill", "element": 3, "value": "search text"}
  {"action": "select", "element": 7, "value": "Option text"}
  {"action": "clear", "element": 3}

NAVIGATE:
  {"action": "scroll", "direction": "down"}
  {"action": "scroll", "container": 14, "direction": "down"}
  {"action": "keypress", "key": "Enter"}
  {"action": "back"}

COMPLETE THE TASK:
  {"action": "answer", "value": "The price is $19.99"}
  {"action": "done", "value": "Task completed - form submitted"}
  {"action": "fail", "reason": "Cannot find the requested item"}

Rules:
- Respond with ONLY a JSON object, no other text
- Use element numbers from the registry
- Scroll to find content not yet visible
- When you have the answer to the task, use the "answer" action immediately
- If a task asks you to DO something (not find something), use "done" when finished
- If the task is impossible, use "fail" with a reason
- Be efficient — take the shortest path to complete the task
"""


# ── Task Loading ──────────────────────────────────────────────────

def load_tasks(tasks_file):
    """Load WebArena task configs from JSON file."""
    with open(tasks_file) as f:
        tasks = json.load(f)
    return tasks


def filter_tasks(tasks, task_id=None, site=None, start=None, end=None):
    """Filter tasks by ID, site, or index range."""
    if task_id is not None:
        return [t for t in tasks if t["task_id"] == task_id]
    if site:
        tasks = [t for t in tasks if site in t.get("sites", [])]
    if start is not None or end is not None:
        tasks = tasks[start:end]
    return tasks


# ── State Formatting ──────────────────────────────────────────────

def format_state_for_model(state):
    """Format page state into a compact string for the LLM."""
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
            if e.get("scrollState"):
                s = e["scrollState"]
                line += f" [scroll:{s['scrollPercent']}%]"
            parts.append(line)

    return "\n".join(parts)


# ── Agent Loop ────────────────────────────────────────────────────

def run_task(gd, task, model="claude-sonnet-4-20250514", max_steps=25, verbose=True):
    """Run a single WebArena task through the Graphic Density agent."""

    task_id = task["task_id"]
    intent = task["intent"]
    start_url = task.get("start_urls", [None])[0]

    if verbose:
        print(f"\n{'='*60}")
        print(f"Task {task_id}: {intent}")
        print(f"Start: {start_url}")
        print(f"{'='*60}")

    # Navigate to start URL
    if start_url:
        nav = gd.navigate(start_url)
        state = nav.get("state") or gd.state()
    else:
        state = gd.state()

    # Initialize LLM
    client = anthropic.Anthropic()
    messages = []
    total_tokens = 0
    start_time = time.time()
    result = None

    for step in range(max_steps):
        # Build message
        state_text = format_state_for_model(state)

        if step == 0:
            user_msg = f"Task: {intent}\n\nCurrent page:\n{state_text}"
        else:
            user_msg = f"Page after action:\n{state_text}"

        messages.append({"role": "user", "content": user_msg})

        # Call LLM
        try:
            response = client.messages.create(
                model=model,
                max_tokens=500,
                system=SYSTEM_PROMPT,
                messages=messages,
            )
        except Exception as e:
            if verbose:
                print(f"  Step {step+1}: LLM error: {e}")
            result = {"status": "ERROR", "error_details": str(e)}
            break

        assistant_text = response.content[0].text.strip()
        messages.append({"role": "assistant", "content": assistant_text})
        total_tokens += response.usage.input_tokens + response.usage.output_tokens

        # Parse action
        try:
            # Handle potential markdown wrapping
            text = assistant_text
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            action = json.loads(text)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{[^{}]+\}', assistant_text)
            if match:
                try:
                    action = json.loads(match.group())
                except json.JSONDecodeError:
                    if verbose:
                        print(f"  Step {step+1}: Parse error: {assistant_text[:80]}")
                    continue
            else:
                if verbose:
                    print(f"  Step {step+1}: No JSON found: {assistant_text[:80]}")
                continue

        action_type = action.get("action", "?")

        if verbose:
            label = action.get("value", action.get("element", action.get("direction", "")))
            print(f"  Step {step+1}: {action_type} {label}")

        # Terminal actions
        if action_type == "answer":
            result = {
                "status": "SUCCESS",
                "task_type": "RETRIEVE",
                "retrieved_data": [str(action.get("value", ""))],
            }
            break

        if action_type == "done":
            result = {
                "status": "SUCCESS",
                "task_type": "MUTATE",
                "retrieved_data": [str(action.get("value", ""))],
            }
            break

        if action_type == "fail":
            result = {
                "status": "UNACHIEVABLE",
                "error_details": action.get("reason", "Task could not be completed"),
            }
            break

        # Execute action
        exec_result = gd.action(action)

        if not exec_result.get("success"):
            if verbose:
                print(f"    ⚠ {exec_result.get('error', 'Unknown error')}")

        # Get new state
        state = exec_result.get("newState") or gd.state()

    # Default result if we hit max steps
    if result is None:
        result = {
            "status": "ERROR",
            "error_details": f"Reached max steps ({max_steps})",
        }

    elapsed = time.time() - start_time

    # Build complete result
    full_result = {
        "task_id": task_id,
        "intent": intent,
        **result,
        "metrics": {
            "steps": step + 1 if 'step' in dir() else 0,
            "total_tokens": total_tokens,
            "elapsed_seconds": round(elapsed, 1),
            "model": model,
        }
    }

    if verbose:
        status = result.get("status", "?")
        symbol = "✓" if status == "SUCCESS" else "✗"
        print(f"\n  {symbol} {status} | {step+1} steps | {total_tokens:,} tokens | {elapsed:.1f}s")
        if result.get("retrieved_data"):
            print(f"  Answer: {result['retrieved_data']}")

    return full_result


# ── Output ────────────────────────────────────────────────────────

def save_result(result, output_dir):
    """Save result in WebArena-Verified compatible format."""
    task_id = result["task_id"]
    task_dir = Path(output_dir) / str(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)

    # Agent response (WebArena-Verified format)
    agent_response = {
        "task_type": result.get("task_type", "RETRIEVE"),
        "status": result.get("status", "ERROR"),
        "retrieved_data": result.get("retrieved_data", []),
        "error_details": result.get("error_details"),
    }

    with open(task_dir / "agent_response.json", "w") as f:
        json.dump(agent_response, f, indent=2)

    # Empty HAR file (required by evaluator but we're not capturing network)
    har = {"log": {"version": "1.2", "entries": []}}
    with open(task_dir / "network.har", "w") as f:
        json.dump(har, f)

    # Our own detailed metrics
    with open(task_dir / "gd_metrics.json", "w") as f:
        json.dump(result, f, indent=2)


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Graphic Density WebArena Benchmark")
    parser.add_argument("--tasks", default="tasks.json", help="Path to tasks JSON file")
    parser.add_argument("--task-id", type=int, help="Run a specific task ID")
    parser.add_argument("--site", help="Filter by site (shopping, reddit, gitlab)")
    parser.add_argument("--start", type=int, help="Start index")
    parser.add_argument("--end", type=int, help="End index")
    parser.add_argument("--model", default="claude-sonnet-4-20250514", help="LLM model to use")
    parser.add_argument("--max-steps", type=int, default=25, help="Max steps per task")
    parser.add_argument("--output", default="output", help="Output directory")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    args = parser.parse_args()

    # Connect to Graphic Density
    print("Connecting to Graphic Density...")
    gd = GraphicDensity()
    print("Connected.\n")

    # Load tasks
    if not os.path.exists(args.tasks):
        print(f"Tasks file not found: {args.tasks}")
        print("\nTo get tasks, run:")
        print("  webarena-verified agent-input-get --config config.json --output tasks.json")
        print("\nOr for a quick test, create a minimal tasks.json:")
        print("""  echo '[{"task_id": 0, "intent": "What is the price of the cheapest item?", "sites": ["shopping"], "start_urls": ["http://localhost:7770"]}]' > tasks.json""")
        sys.exit(1)

    tasks = load_tasks(args.tasks)
    tasks = filter_tasks(tasks, task_id=args.task_id, site=args.site, start=args.start, end=args.end)

    if not tasks:
        print("No tasks matched your filters.")
        sys.exit(1)

    print(f"Running {len(tasks)} task(s) with {args.model}")
    print(f"Output: {args.output}/\n")

    # Run tasks
    results = []
    successes = 0

    for i, task in enumerate(tasks):
        result = run_task(
            gd, task,
            model=args.model,
            max_steps=args.max_steps,
            verbose=not args.quiet,
        )
        results.append(result)
        save_result(result, args.output)

        if result.get("status") == "SUCCESS":
            successes += 1

    # Summary
    total = len(results)
    total_tokens = sum(r.get("metrics", {}).get("total_tokens", 0) for r in results)
    total_time = sum(r.get("metrics", {}).get("elapsed_seconds", 0) for r in results)

    print(f"\n{'='*60}")
    print(f"RESULTS: {successes}/{total} tasks completed ({100*successes/total:.0f}%)")
    print(f"Tokens:  {total_tokens:,} total")
    print(f"Time:    {total_time:.0f}s total, {total_time/total:.1f}s avg per task")
    print(f"Output:  {args.output}/")
    print(f"{'='*60}")

    # Save summary
    summary = {
        "total": total,
        "successes": successes,
        "rate": round(successes / total, 3) if total > 0 else 0,
        "total_tokens": total_tokens,
        "total_seconds": round(total_time, 1),
        "model": args.model,
        "results": results,
    }
    with open(Path(args.output) / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nTo evaluate with WebArena-Verified:")
    print(f"  webarena-verified eval-tasks --config config.json --output-dir {args.output}")


if __name__ == "__main__":
    if not HAS_ANTHROPIC:
        print("pip install anthropic")
        sys.exit(1)
    main()
