<div align="center">

<br>

```
 ██████╗ ██████╗  ██████╗ 
██╔════╝ ██╔══██╗██╔════╝ 
██║  ███╗██║  ██║██║  ███╗
██║   ██║██║  ██║██║   ██║
╚██████╔╝██████╔╝╚██████╔╝
 ╚═════╝ ╚═════╝  ╚═════╝ 
```

**Graphic Density Grounding**

*Spatial text browser execution layer for AI agents*

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
![Chrome Extension](https://img.shields.io/badge/Chrome-Extension_MV3-4285F4?logo=googlechrome&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-v20+-339933?logo=nodedotjs&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)

---

**AI agents see web pages as screenshots. We convert them to text.**<br>
Any model reads it. No vision encoder. 10-30x cheaper per step.

[Quick Start](#quick-start) · [How It Works](#how-it-works) · [API Reference](#api-reference) · [MCP Integration](#mcp-integration) · [Multi-Model CLI](#multi-model-cli) · [Benchmarks](#benchmarks) · [Architecture](#architecture)

</div>

---

## The Problem

Every browser agent today — OpenAI Operator, Anthropic Computer Use, Google Mariner — takes a screenshot, feeds it to a vision model, and hopes the model can figure out where the buttons are. This costs **10,000-15,000 tokens per page view** and introduces OCR hallucinations, spatial reasoning errors, and mandatory vision model dependencies.

## The Idea

What if the page representation was *text that looks like the page*? A character grid where element density encodes type — buttons render as `████`, inputs as `╔══╗`, links as `▸`, and layout is preserved spatially. Any text model reads it natively. No vision encoder needed.

```
         [1]              [2]  [3]
  
  ╔══[4]═══════════════════════════╗
  ╚════════════════════════════════╝

     [5]         [6]         [7]

     [8]         [9]         [10]

              [11]██████████████
              █ + New Project █
              ██████████████████
```

The model sees spatial layout, element types, and numbered targets in **~1,000 tokens**. It says `{"action": "click", "element": 11}` and the extension executes it.

## Validation

We tested graphic density output on 11 different products — GitHub, ChatGPT, Gmail, Google Docs, Reddit, Namecheap, Convex, Supabase, Cloudflare, and more. A text-only model with **zero instructions** correctly identified every product, located primary actions, and understood visual hierarchy.

Then we benchmarked against WebArena-style tasks:

| Run | Score | Tokens | Time | What Changed |
|-----|-------|--------|------|--------------|
| Run 1 | 0/5 (0%) | 394K | 33 min | Baseline — broken agent loop |
| Run 2 | 2/5 (40%) | 172K | 5.8 min | Prompt + budget fixes only |
| Run 3 | **3/5 (60%)** | **172K** | **10 min** | Read mode — agent can see text content |

0% to 60% in one day. Same token budget. No task-specific tuning.

## Properties

Fourteen properties fall out of the spatial text encoding:

| Property | How |
|----------|-----|
| **No vision model needed** | Any text model reads the character grid natively |
| **Spatial layout** | Elements appear where they are on screen |
| **Action targeting** | Numbered elements resolve to coordinates |
| **10-30x cheaper** | ~1,000 tokens vs ~10,000-15,000 for screenshots |
| **Model-agnostic** | Claude, GPT, Llama, Gemini — anything that reads text |
| **Anti-bot invisible** | Runs in user's real browser via extension, zero fingerprint |
| **Scroll containers** | Independent scrollable regions as first-class elements |
| **State diffable** | Two text grids diff trivially — 90% token reduction per step |
| **Multi-step planning** | Hidden DOM scan reveals entire SPA flows in one shot |
| **Iframe pipelining** | Prefetch next page state, eliminate inter-step latency |
| **Action sandboxing** | Fork state in iframe, preview consequences before committing |
| **Injection resistant** | Non-interactive text compressed away — attack payloads stripped |
| **Cross-platform** | Same technique works with OS accessibility trees (desktop, mobile) |
| **Page type detection** | Heuristic classification from element composition |

---

## Quick Start

### 1. Load the Extension

```bash
git clone https://github.com/Badgerion/GDG-browser.git
```

1. Open Chrome → `chrome://extensions/`
2. Enable **Developer Mode** (top right)
3. Click **Load unpacked** → select the cloned folder
4. Navigate to any website → click the extension icon → **Scan Page**

### 2. Set Up the API Bridge

```bash
cd bridge
chmod +x install.sh server.js
./install.sh <your-extension-id>  # ID from chrome://extensions
```

Reload the extension. Test the connection:

```bash
curl http://127.0.0.1:7080/health
```

### 3. Drive It from Python

```bash
pip install requests anthropic
```

```python
from gd_client import GraphicDensity

gd = GraphicDensity()

# See the page
gd.print_state(mode="read")

# Navigate and interact
gd.navigate("https://github.com")
gd.fill(3, "search query")
gd.click(4)

# Read data from the page
state = gd.read()
print(state["content"])   # visible text
print(state["tables"])    # extracted table data
```

---

## How It Works

### The Core Loop

```
1. GET /state?mode=numbered  →  model sees spatial map + element registry
2. Model decides             →  {"action": "click", "element": 11}
3. POST /action              →  extension executes, waits for DOM to settle
4. Returns new state         →  model sees what happened
5. Repeat
```

### Five Render Modes

| Mode | Purpose | Tokens | Use When |
|------|---------|--------|----------|
| `full` | Complete page with density typing | ~3,000-5,000 | Initial page understanding |
| `actions_only` | Only interactive elements | ~500-800 | Cheapest navigation |
| `numbered` | Interactive elements with IDs | ~1,000-2,000 | Standard agent operation |
| `numbered_v2` | + action hints, forms, layers | ~1,200-2,500 | Complex UIs with modals |
| `read` | + visible text + table extraction | ~2,000-4,000 | Reading data, finding answers |

### Adaptive Two-Phase Strategy

```
Navigate Phase (numbered mode — cheap, spatial)
  → Click menus, fill search bars, navigate to target page

Read Phase (read mode — rich, content-aware)
  → Extract text, read tables, find specific data values
```

The model switches modes mid-task: `{"action": "switch_mode", "mode": "read"}`

### v0.2 Enhancements

**Interaction hints** — every element shows what actions it supports:
```
[5]  button  "Submit"           click → submit
[12] input   "Search"           fill, clear
[17] link    "Documentation"    click → nav
[22] select  "Country"          select
```

**Form grouping** — elements inside `<form>` tags are linked:
```
[7]  input   "Email"            fill    {form:login}
[8]  input   "Password"         fill    {form:login}
[9]  button  "Sign in"          click → submit  {form:login}
```

**Layer awareness** — modals and overlays are detected:
```
⚠ MODAL ACTIVE — interact with elements 41, 42 first

[41] button  "Cancel"     click     [modal]
[42] button  "Confirm"    click     [modal]
[1]  button  "Menu"       click     [blocked]
```

**Table extraction** — structured data with pagination:
```
── Table 1 (Showing 1-20 of 2,048 results) ──
| Name | Email | Status |
|---|---|---|
| Veronica Costello | veronica@example.com | Active |
| ...
```

---

## API Reference

The bridge exposes a local HTTP API on `127.0.0.1:7080`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/state?mode=read` | Page state (map + registry + content) |
| `GET` | `/environment` | Full state + history + page type |
| `POST` | `/action` | Execute action: `{"action":"click","element":5}` |
| `POST` | `/batch` | Execute sequence, stops on first failure |
| `POST` | `/navigate` | Go to URL, returns new state |
| `GET` | `/tabs` | List all open browser tabs |
| `GET` | `/history` | Action history for current tab |
| `DELETE` | `/history` | Clear action history |
| `GET` | `/health` | Connection status |

### Action Types

```json
{"action": "click", "element": 5}
{"action": "fill", "element": 3, "value": "hello"}
{"action": "clear", "element": 3}
{"action": "select", "element": 7, "value": "Option text"}
{"action": "hover", "element": 12}
{"action": "scroll", "direction": "down"}
{"action": "scroll", "container": 14, "direction": "down"}
{"action": "keypress", "key": "Enter"}
{"action": "keypress", "key": "a", "modifiers": {"ctrl": true}}
{"action": "back"}
{"action": "forward"}
{"action": "wait", "duration": 1000}
```

---

## MCP Integration

Connect GDG to Claude Desktop, Cursor, or any MCP client:

```json
{
  "mcpServers": {
    "gdg-browser": {
      "command": "node",
      "args": ["/path/to/bridge/mcp-server.js"]
    }
  }
}
```

Tools: `gdg_get_state`, `gdg_click`, `gdg_fill`, `gdg_select`, `gdg_scroll`, `gdg_navigate`, `gdg_keypress`, `gdg_back`, `gdg_hover`, `gdg_tabs`

---

## Multi-Model CLI

One script, any AI provider:

```bash
python bridge/gdg-agent.py "What's trending on GitHub?"
python bridge/gdg-agent.py -m openai/gpt-4o "Find flights to Tokyo"
python bridge/gdg-agent.py -m ollama/llama3 "Check Hacker News"
python bridge/gdg-agent.py -m groq/llama-3.3-70b-versatile "Search Amazon"
python bridge/gdg-agent.py -m gemini/gemini-2.0-flash "Go to Reddit"
python bridge/gdg-agent.py -m sambanova/Meta-Llama-3.1-70B-Instruct "Check weather"
```

Supports: Anthropic, OpenAI, Groq, Ollama (local), Sambanova, Gemini

---

## Benchmarks

Tested against WebArena-style tasks on a Magento admin panel (multi-step navigation, data retrieval, form interaction):

**WebArena — Magento admin panel** (multi-step navigation, data retrieval, form interaction):

| Run | Score | Tokens | Time | What Changed |
|-----|-------|--------|------|--------------|
| Run 1 | 0/5 (0%) | 394K | 33 min | Baseline — broken agent loop |
| Run 2 | 2/5 (40%) | 172K | 5.8 min | Prompt + budget fixes only |
| Run 3 | **3/5 (60%)** | **172K** | **10 min** | Read mode — agent can see text content |

0% to 60% in one day. Same token budget. No task-specific tuning.

**WebVoyager — GitHub tasks:**

| Task | Intent | Steps | Result |
|------|--------|-------|--------|
| gh_001 | Open issues in anthropics/anthropic-sdk-python | 2 | ✓ Found count |
| gh_002 | Most-used language in microsoft/vscode | 8 | ✓ TypeScript |
| gh_003 | Latest release of openai/openai-python | 2 | ✓ v2.29.0 |
| gh_004 | Contributor count for facebook/react | 25 | ✗ Hit step limit |
| gh_005 | About section of huggingface/transformers | 2 | ✓ Found description |

**Score: 80% (4/5)** — three tasks completed in just 2 steps.

**Comparison to screenshot-based agents:**

| Approach | Tokens/step | Vision required | Cost/step |
|----------|-------------|-----------------|-----------|
| Screenshot + GPT-4o | 10,000-15,000 | Yes | $0.01-0.04 |
| DOM tree (rtrvr.ai) | 2,000-3,000 | No | $0.003-0.006 |
| **Graphic Density (numbered)** | **800-1,500** | **No** | **$0.001-0.003** |
| **Graphic Density (actions_only)** | **400-800** | **No** | **$0.0005-0.001** |

---

## Architecture

```
External Process (Python, curl, any language)
  ↕ HTTP (localhost:7080)
bridge/server.js         ← Native messaging host + HTTP server
  ↕ stdin/stdout (Chrome native messaging)
background.js            ← Service worker, tab routing, navigation
  ↕ chrome.tabs.sendMessage
renderer.js              ← Scanner + classifier + renderer + executor
  ↕ DOM / accessibility tree
Web Page
```

### Key Design Decisions

**Extension-based, not CDP.** Chrome Extension APIs are first-class browser citizens — sandboxed execution, no automation fingerprint, session persistence across crashes. CDP (Puppeteer/Playwright) is a debugging backdoor with detectable fingerprints.

**Text output, not images.** Any model that reads text can drive the browser. No vision encoder, no image preprocessing, no OCR. Token cost scales with page complexity, not pixel count.

**Semantic density, not raw DOM.** Elements are classified by role and rendered with visual weight. Buttons are heavy (`████`), inputs have borders (`╔══╗`), links are light (`▸`). The model perceives UI hierarchy from character density without needing CSS or computed styles.

---

## File Structure

```
GDG-browser/
├── manifest.json           Chrome extension manifest (MV3)
├── renderer.js             Core: scanner + classifier + 5 render modes + action executor
├── background.js           Service worker: message routing, native messaging, tab management
├── popup.html              Testing UI with State/Actions/History tabs
├── popup.js                Popup controller
├── icons/                  Extension icons
├── bridge/
│   ├── server.js           Native messaging host + HTTP API server
│   ├── mcp-server.js       MCP server for Claude Desktop / Cursor integration
│   ├── install.sh          One-time setup for native messaging registration
│   ├── gd_client.py        Python client library
│   ├── gdg-agent.py        Universal multi-model browser agent CLI
│   ├── agent_example.py    Example AI agent loop
│   └── benchmark.py        WebArena benchmark harness
└── README.md
```

---

## Roadmap

- [x] **v0.1** — Spatial renderer + action executor + popup testing UI
- [x] **v0.2** — Read mode, interaction hints, form grouping, layer awareness, table extraction
- [x] **API** — HTTP bridge + Python client + agent example
- [x] **v0.2.1** — MCP server (Claude Desktop / Cursor), multi-model CLI (Anthropic, OpenAI, Groq, Ollama, Gemini, Sambanova)
- [ ] **v0.3** — State diff (send only changes), hidden DOM flow scan, iframe pipelining
- [ ] **Sessions** — Checkpoint/restore across model context resets
- [ ] **Desktop** — macOS/Windows accessibility tree → spatial text (same technique, native apps)
- [ ] **Framework integrations** — Browser Use, LangChain adapters

---

## Contributing

This is early-stage infrastructure. If you're building AI agents and hit a page the renderer can't handle, [open an issue](https://github.com/Badgerion/GDG-browser/issues) with the URL and what broke. Edge cases are how this gets better.

---

## License

[AGPL-3.0](LICENSE) — Use it, modify it, build on it. If you run it as a service, share your changes.

For commercial licensing, [open an issue](https://github.com/Badgerion/GDG-browser/issues) or reach out.
