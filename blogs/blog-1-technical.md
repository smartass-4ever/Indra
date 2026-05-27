# Your AI Agent Is Wasting Tokens on Pages That Haven't Changed

You built a web monitoring agent. It checks competitor pricing every hour, scans news feeds for signals, watches supplier pages for stock changes.

It's working. And it's burning your API budget — on nothing.

---

## The problem nobody talks about

Here's what most web monitoring agents do on every run:

1. Fetch the page
2. Send the full content to the LLM
3. Ask "what changed?"

The page hasn't changed. The LLM doesn't know that. It reads 1,500 tokens of HTML, thinks carefully, and tells you: nothing changed.

You paid for that. Every hour. For every URL.

If you're monitoring 10 pages hourly, that's 240 LLM calls a day — most of them pointless.

---

## What the right architecture looks like

The fix is straightforward: **don't call the LLM unless the page actually changed.**

```
Run 1:  fetch 10 pages → analyse all 10 → cache insights
Run 2:  fetch 10 pages → 8 unchanged → 2 changed → LLM fires twice
Run 3:  fetch 10 pages → 9 unchanged → 1 changed → LLM fires once
```

Over 24 hours of hourly checks across 10 pages: **240 fetches, ~20 LLM calls** instead of 240. That's an 80%+ reduction without losing a single real signal.

The mechanics:
- Fetch the page live on every run (you need fresh data, not a cache)
- Hash the content (SHA-256, fast, free)
- Compare to the last stored hash
- If identical → return cached insight, skip the LLM entirely
- If changed → extract the diff, send **only the delta** to the LLM

The second part matters as much as the first. When a page does change, you still shouldn't send the full page — you should send what's different. If a pricing page updates one number, the LLM needs 50 tokens, not 1,500.

---

## Why most agents don't do this

Two reasons.

**Bot detection.** Consistent fetching from a static IP gets blocked fast. Most developers hit a wall here and either throttle to the point of uselessness or pay for proxy infrastructure separately. The fetching layer is genuinely hard.

**Boilerplate.** Hashing, diffing, caching, storing snapshots — it's not hard code, but it's 200 lines you have to write, test, and maintain before you've done anything useful. Most people skip it and just call the LLM every time.

---

## Indra

I built [Indra](https://github.com/smartass-4ever/Indra) to solve both problems in one library.

It uses [Bright Data](https://brightdata.com)'s Web Unlocker on every fetch — bot detection, CAPTCHAs, geo-blocks, JavaScript rendering, all handled transparently. And it wraps the full hash-diff-cache pipeline so you don't have to.

```python
import indra
import anthropic

client = anthropic.Anthropic()

def llm(prompt: str) -> str:
    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

agent = indra.init(brightdata_api_key="your-key")

result = agent.watch(
    url="https://competitor.com/pricing",
    question="Did any prices change? What are the implications?",
    generation_fn=llm,
)

print(result.changed)        # True / False
print(result.insight)        # LLM analysis, or cached answer if unchanged
print(result.tokens_saved)   # tokens skipped this run
print(result.cost_saved_usd) # dollar value of what was skipped
```

The `generation_fn` is only called when the page actually changed. On unchanged runs it returns instantly with the cached answer — zero tokens, sub-millisecond.

---

## Watching multiple pages

```python
results = agent.watch_all(
    urls=[
        "https://openai.com/api/pricing/",
        "https://anthropic.com/pricing",
        "https://competitor.com/pricing",
    ],
    question="Did any prices change?",
    generation_fn=llm,
)

agent.print_stats()
```

Output after a few runs:

```
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

## Watching search results

Indra also supports SERP monitoring — fire the LLM only when the ranking itself changes:

```python
result = agent.search_watch(
    query="openai new model announcement",
    question="Is there a major new release?",
    generation_fn=llm,
)
```

Same pattern: fetch live SERP results, hash them, skip the LLM if rankings haven't shifted.

---

## Install

```bash
pip install indra-ai
```

It's early — rough edges exist, and we're fixing them fast. If you're building web monitoring into an agent and burning tokens on unchanged pages, give it a try.

- [GitHub](https://github.com/smartass-4ever/Indra)
- [PyPI](https://pypi.org/project/indra-ai/)
