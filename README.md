<div align="center">

# Indra

**Web intelligence that only thinks when the web changes.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Powered by Bright Data](https://img.shields.io/badge/Powered%20by-Bright%20Data-orange)](https://brightdata.com)

</div>

---

Indra fetches live web data through Bright Data on every run — no stale snapshots, no geo-blocks, no bot detection failures. It stores a fingerprint of what it saw. Next run, if the page hasn't changed, the LLM is skipped entirely. If it has, the LLM sees only the diff.

```
Run 1:  fetch 10 pages via Bright Data → analyse all 10 → cache insights
Run 2:  fetch 10 pages via Bright Data → 8 unchanged → 2 changed → LLM fires twice
Run 3:  fetch 10 pages via Bright Data → 9 unchanged → 1 changed → LLM fires once
```

Over 24 hours of hourly checks across 10 pages: **240 Bright Data fetches, ~20 LLM calls** instead of 240.

```bash
pip install indra-ai
export BRIGHTDATA_API_KEY="your-key"
python examples/competitor_monitor_demo.py
```

---

## How it works

Every monitored URL goes through three steps on each run:

**1. Fetch live via Bright Data**
Bright Data's Web Unlocker bypasses bot detection, CAPTCHAs, and geo-blocks. Every check uses fresh data — there is no local cache of the web content itself.

**2. Fingerprint and compare**
Indra hashes the response and compares it to the last stored hash. This is instant and costs nothing.

**3. LLM only on change**
- **No change** → return the cached insight. Zero tokens, sub-millisecond.
- **Changed** → extract the diff, send *only the delta* to your LLM. Tokens proportional to what changed, not the full page.

```python
import indra

agent = indra.init(brightdata_api_key="your-key")

result = agent.watch(
    url="https://competitor.com/pricing",
    question="Did any prices change? What are the implications?",
    generation_fn=my_llm_call,   # only called when the page actually changed
)

print(result.changed)          # True / False
print(result.insight)          # LLM analysis, or cached answer if unchanged
print(result.diff)             # what changed (empty if no change)
print(result.tokens_saved)     # tokens skipped this run
```

---

## The demo

`examples/competitor_monitor_demo.py` watches 5 real pages across 3 rounds:

```
Round 1 — Baseline (first run)
  unchanged · openai.com/api/pricing/ .............. first run
  unchanged · anthropic.com/pricing ................ first run
  unchanged · news.ycombinator.com/ ................ first run
  unchanged · techcrunch.com/ai/ ................... first run
  unchanged · github.com/trending .................. first run

Round 2 — Incremental check
  unchanged · openai.com/api/pricing/ .............. saved 1500 tokens
  unchanged · anthropic.com/pricing ................ saved 1500 tokens
  CHANGED ↑  · news.ycombinator.com/ ............... LLM fired · saved 1200 tokens on diff
  unchanged · techcrunch.com/ai/ ................... saved 1500 tokens
  unchanged · github.com/trending .................. saved 1500 tokens

──────────────────────────────────────────────────
  Indra Session Summary
──────────────────────────────────────────────────
  Bright Data fetches : 15
  Changes detected    : 1
  LLM calls fired     : 6
  Cache hits          : 9
  Tokens saved        : 12,000
  Cost saved          : $0.0360
  Efficiency          : 80%
──────────────────────────────────────────────────
```

---

## Quick Start

```bash
pip install indra-ai
```

Set your API keys:

```bash
# Required — Bright Data account (brightdata.com)
export BRIGHTDATA_API_KEY="your-bright-data-api-key"
export BRIGHTDATA_UNLOCKER_ZONE="web_unlocker1"   # zone name from your Bright Data dashboard

# LLM — pick one
export GROQ_API_KEY="your-groq-key"       # groq.com — free tier available
export GROK_API_KEY="your-grok-key"       # xAI
export ANTHROPIC_API_KEY="your-key"       # Anthropic
```

Run the built-in demo:

```bash
indra demo
```

---

## Live Demo Output

Real run on 2026-05-29 — 4 pages monitored, 3 rounds, Bright Data Web Unlocker + Groq LLM:

```
============================================================
  Indra  -  Web Intelligence That Only Thinks When
            the Web Changes
  Powered by Bright Data + Mnemon
============================================================

  Fetch mode : Bright Data Web Unlocker
  LLM        : Groq llama-3.1-8b-instant
  Pages      : 4
  Rounds     : 3  (gap: 30s)

============================================================
  Round 1 / 3  -  Baseline (first observation)
============================================================
  unchanged   openai.com/api/pricing/                               first observation
  unchanged   www.anthropic.com/pricing                             first observation
  unchanged   techcrunch.com/category/artificial-intelligence/      first observation
  unchanged   github.com/trending                                   first observation

  Running total:  4 fetches  |  4 LLM calls  |  0 tokens saved  |  $0.0000 saved

============================================================
  Round 2 / 3  -  Incremental check
============================================================

  *** CHANGED *** https://openai.com/api/pricing/
  Summary  : +1 lines, -1 lines
  Insight  : No changes in API prices were found in the provided diff.
  Tokens   : saved 1200 tokens on diff

  unchanged   www.anthropic.com/pricing                             saved 1500 tokens
  unchanged   techcrunch.com/category/artificial-intelligence/      saved 1500 tokens

  *** CHANGED *** https://github.com/trending
  Summary  : +1 lines, -1 lines
  Insight  : Today, several new AI/ML repositories are trending,
             including Leonxlnx's Taste-Skill, which gives your AI
             good taste, and hardikpandya's stop-slop skill file that
             removes AI tells from prose.
  Tokens   : saved 1200 tokens on diff

  Running total:  8 fetches  |  6 LLM calls  |  5,400 tokens saved  |  $0.0162 saved

============================================================
  Round 3 / 3  -  Incremental check
============================================================

  *** CHANGED *** https://openai.com/api/pricing/
  Summary  : +1 lines, -1 lines
  Insight  : No changes in API prices were found in the provided diff.
  Tokens   : saved 1200 tokens on diff

  unchanged   www.anthropic.com/pricing                             saved 1500 tokens
  unchanged   techcrunch.com/category/artificial-intelligence/      saved 1500 tokens

  *** CHANGED *** https://github.com/trending
  Summary  : +1 lines, -1 lines
  Insight  : Today, several new AI/ML repositories are trending,
             including Leonxlnx's Taste-Skill, which gives your AI
             good taste, and hardikpandya's stop-slop skill file that
             removes AI tells from prose.
  Tokens   : saved 1200 tokens on diff

  Running total:  12 fetches  |  8 LLM calls  |  10,800 tokens saved  |  $0.0324 saved

--------------------------------------------------
  Indra Session Summary
--------------------------------------------------
  Bright Data fetches : 12
  Changes detected    : 4
  LLM calls fired     : 8
  Cache hits          : 4
  Tokens saved        : 10,800
  Cost saved          : $0.0324
  Efficiency          : 60%
--------------------------------------------------

  Naive approach : 12 LLM calls for 12 pages.
  Indra          : 8 LLM calls — 33% reduction.
```

---

## Install

```bash
pip install indra-ai
```

**Required:** A [Bright Data](https://brightdata.com) account with a Web Unlocker zone (`BRIGHTDATA_API_KEY` + `BRIGHTDATA_UNLOCKER_ZONE`).

**LLM:** Groq (free tier at groq.com), xAI Grok, or Anthropic — set whichever key you have.

---

## API

### `indra.init()`

```python
agent = indra.init(
    brightdata_api_key="...",   # or set BRIGHTDATA_API_KEY env var
    db_path="indra.db",         # where snapshots are stored
    silent=False,               # suppress per-URL console output
)
```

### `agent.watch(url, question, generation_fn)`

Watch a single URL. Returns a `WatchResult`.

```python
result = agent.watch(
    url="https://example.com",
    question="What changed and why does it matter?",
    generation_fn=my_llm_fn,    # fn(prompt: str) -> str
    render_js=False,            # True for JS-heavy pages (Bright Data headless)
    ttl=3600,                   # skip Bright Data fetch if snapshot < ttl seconds old
)
```

### `agent.watch_all(urls, question, generation_fn)`

Watch multiple URLs in one call.

```python
results = agent.watch_all(
    urls=["https://site1.com", "https://site2.com"],
    question="Any significant changes?",
    generation_fn=my_llm_fn,
)
```

### `agent.search_watch(query, question, generation_fn)`

Watch live SERP results for a query. Fires LLM only when the result set changes.

```python
result = agent.search_watch(
    query="openai new model announcement",
    question="Is there a major new release?",
    generation_fn=my_llm_fn,
)
```

### `WatchResult`

| Field | Type | Description |
|---|---|---|
| `changed` | bool | Whether content changed since last run |
| `insight` | str | LLM analysis (or cached answer if unchanged) |
| `diff` | str | Unified diff of what changed |
| `tokens_saved` | int | Tokens skipped this run |
| `cost_saved_usd` | float | Dollar value of skipped tokens |
| `latency_ms` | float | Total time for this watch call |
| `brightdata_called` | bool | Whether Bright Data was queried |
| `change_count` | int | Total times this URL has changed |
| `summary` | str | Human-readable change summary |

### `agent.stats()` / `agent.print_stats()`

```python
agent.print_stats()
# ──────────────────────────────────────────────────
#   Indra Session Summary
# ──────────────────────────────────────────────────
#   Bright Data fetches : 24
#   Changes detected    : 3
#   LLM calls fired     : 3
#   Cache hits          : 21
#   Tokens saved        : 31,500
#   Cost saved          : $0.0945
#   Efficiency          : 87%
# ──────────────────────────────────────────────────
```

---

## Use cases

**Competitor pricing monitor** — check 20 competitor pages every hour. LLM summarises only when a price changes.

**News and signal tracker** — watch industry news sites. Alert only when genuinely new stories appear, not every hourly check.

**Supply chain watcher** — monitor supplier pages for stock or lead time changes. Zero noise on stable days.

**Regulatory tracker** — watch government or compliance pages. LLM fires when policy text changes; silent otherwise.

**SEO and ranking monitor** — SERP watch for branded or competitive queries. Analyse only when rankings shift.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Your agent / script                            │
└────────────────────┬────────────────────────────┘
                     │ agent.watch(url, question)
┌────────────────────▼────────────────────────────┐
│  Indra                                          │
│                                                 │
│  1. Fetch via Bright Data Web Unlocker          │
│     (bypasses bot detection, geo-blocks)        │
│                                                 │
│  2. Fingerprint content (SHA-256)               │
│     Compare to stored hash in SQLite            │
│                                                 │
│  3a. No change → return cached insight          │
│      0 tokens · sub-millisecond                 │
│                                                 │
│  3b. Changed → extract diff → LLM(diff only)   │
│      tokens ∝ what changed, not page size       │
└─────────────────────────────────────────────────┘
```

Indra is built on [Mnemon](https://github.com/smartass-4ever/Mnemon) — an execution cache for LLM agents.

---

## Why Bright Data

Standard web fetching breaks on modern sites: JavaScript rendering, bot detection, CAPTCHAs, geo-restrictions. Monitoring agents that hit these walls silently return stale or empty content — and the LLM never knows.

Bright Data solves all of this transparently. Every `agent.watch()` call reaches the live page regardless of what protection it has. The change detection layer is only useful if the data underneath is actually fresh — Bright Data guarantees that.

---

## License

MIT — free to use and build on.

Built for the [Web Data UNLOCKED Hackathon](https://lablab.ai/ai-hackathons/brightdata-ai-agents-web-data-hackathon) by [Mahika Jadhav](https://github.com/smartass-4ever).

Questions: mahikajadhav22@gmail.com
