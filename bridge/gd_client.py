"""
Graphic Density — Python Client

Simple client for driving the browser execution layer from Python.
Connects to the local API bridge running on http://127.0.0.1:7080.

Usage:
    from gd_client import GraphicDensity

    gd = GraphicDensity()

    # See the page
    state = gd.state()
    print(state['map'])

    # Click element 5
    result = gd.click(5)

    # Fill a form field
    result = gd.fill(3, "hello world")

    # Navigate somewhere
    result = gd.navigate("https://github.com")

    # Run a full sequence
    results = gd.batch([
        {"action": "fill", "element": 3, "value": "search query"},
        {"action": "click", "element": 4},
    ])
"""

import json
import requests
from typing import Optional

class GraphicDensity:
    def __init__(self, host="127.0.0.1", port=7080):
        self.base = f"http://{host}:{port}"
        self._verify_connection()

    def _verify_connection(self):
        try:
            r = requests.get(f"{self.base}/health", timeout=3)
            data = r.json()
            if not data.get("extensionConnected"):
                print("[GD] Warning: Bridge running but extension not connected.")
        except requests.ConnectionError:
            raise ConnectionError(
                "Cannot connect to Graphic Density bridge.\n"
                "Make sure:\n"
                "  1. Chrome is open with the extension loaded\n"
                "  2. The native bridge is installed (run bridge/install.sh)\n"
                "  3. The extension has been reloaded after install"
            )

    # ── State ─────────────────────────────────────────────────────

    def state(self, mode="numbered", tab_id=None):
        """Get current page state as graphic density map + registry."""
        params = {"mode": mode}
        if tab_id:
            params["tab"] = tab_id
        r = requests.get(f"{self.base}/state", params=params)
        return r.json()

    def environment(self, tab_id=None):
        """Get full environment summary including history and page type."""
        params = {}
        if tab_id:
            params["tab"] = tab_id
        r = requests.get(f"{self.base}/environment", params=params)
        return r.json()

    # ── Actions ───────────────────────────────────────────────────

    def action(self, action_dict):
        """Execute a raw action dict."""
        r = requests.post(f"{self.base}/action", json=action_dict)
        return r.json()

    def click(self, element):
        """Click an element by its registry number."""
        return self.action({"action": "click", "element": element})

    def fill(self, element, value):
        """Fill an input element with text."""
        return self.action({"action": "fill", "element": element, "value": value})

    def clear(self, element):
        """Clear an input element."""
        return self.action({"action": "clear", "element": element})

    def select(self, element, value):
        """Select a dropdown option."""
        return self.action({"action": "select", "element": element, "value": value})

    def hover(self, element):
        """Hover over an element."""
        return self.action({"action": "hover", "element": element})

    def scroll(self, direction="down", container=None, amount=None):
        """Scroll the page or a specific container."""
        action = {"action": "scroll", "direction": direction}
        if container is not None:
            action["container"] = container
        if amount is not None:
            action["amount"] = amount
        return self.action(action)

    def keypress(self, key, ctrl=False, shift=False, alt=False, meta=False):
        """Send a keypress."""
        return self.action({
            "action": "keypress",
            "key": key,
            "modifiers": {"ctrl": ctrl, "shift": shift, "alt": alt, "meta": meta},
        })

    def back(self):
        """Browser back."""
        return self.action({"action": "back"})

    def forward(self):
        """Browser forward."""
        return self.action({"action": "forward"})

    def wait(self, duration_ms=1000):
        """Wait for a duration."""
        return self.action({"action": "wait", "duration": duration_ms})

    # ── Batch ─────────────────────────────────────────────────────

    def batch(self, actions):
        """Execute a sequence of actions. Stops on first failure."""
        r = requests.post(f"{self.base}/batch", json={"actions": actions})
        return r.json()

    # ── Navigation ────────────────────────────────────────────────

    def navigate(self, url, tab_id=None):
        """Navigate to a URL and return the new page state."""
        body = {"url": url}
        if tab_id:
            body["tabId"] = tab_id
        r = requests.post(f"{self.base}/navigate", json=body)
        return r.json()

    # ── Tabs ──────────────────────────────────────────────────────

    def tabs(self):
        """List all open browser tabs."""
        r = requests.get(f"{self.base}/tabs")
        return r.json()

    # ── History ───────────────────────────────────────────────────

    def history(self):
        """Get action history for current tab."""
        r = requests.get(f"{self.base}/history")
        return r.json()

    def clear_history(self):
        """Clear action history."""
        r = requests.delete(f"{self.base}/history")
        return r.json()

    # ── Convenience ───────────────────────────────────────────────

    def map(self, mode="numbered"):
        """Just get the text map, nothing else."""
        state = self.state(mode=mode)
        return state.get("map", "")

    def read(self):
        """Get full read mode: map + registry + text content + tables."""
        return self.state(mode="read")

    def registry(self, enhanced=False):
        """Just get the element registry. enhanced=True includes action hints."""
        mode = "numbered_v2" if enhanced else "numbered"
        state = self.state(mode=mode)
        return state.get("registry", [])

    def find(self, label=None, element_type=None):
        """Find elements by label or type."""
        reg = self.registry()
        results = reg
        if label:
            label_lower = label.lower()
            results = [e for e in results if label_lower in (e.get("label") or "").lower()]
        if element_type:
            results = [e for e in results if e.get("type") == element_type]
        return results

    def print_state(self, mode="numbered"):
        """Print the current page state to console."""
        state = self.state(mode=mode)
        print(state.get("map", ""))
        if state.get("registry"):
            print("\n── Registry ──")
            for e in state["registry"]:
                parts = [f"  [{e['id']}] {e['type']:18s} {e.get('label', '')}"]
                if e.get("actions"):
                    parts.append(f"  {', '.join(e['actions'])}")
                if e.get("form"):
                    parts.append(f"  {{{e['form']}}}")
                if e.get("layer"):
                    parts.append(f"  [{e['layer']['layer']}]")
                if e.get("scrollState"):
                    s = e["scrollState"]
                    parts.append(f"  [scroll:{s['scrollPercent']}%]")
                print("".join(parts))
        if state.get("content"):
            print("\n── Content ──")
            print(state["content"][:500])
        if state.get("tables"):
            print("\n── Tables ──")
            print(state["tables"][:500])
        if state.get("scroll"):
            s = state["scroll"]
            print(f"\nScroll: {s['scrollPercent']}% | Page {s['currentPage']}/{s['totalPages']}")
        if state.get("meta", {}).get("hasModal"):
            print(f"\n⚠ MODAL ACTIVE — elements: {state['meta']['modalElements']}")


# ── Quick test ────────────────────────────────────────────────────

if __name__ == "__main__":
    gd = GraphicDensity()
    print("Connected to Graphic Density bridge.\n")
    gd.print_state()
