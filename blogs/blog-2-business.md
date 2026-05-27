# The Hidden LLM Cost Nobody Talks About

Everyone's watching their token usage. Model costs, prompt lengths, output sizes — developers are optimizing all of it.

And then quietly paying for thousands of LLM calls that returned the same answer as yesterday.

---

## What's actually happening

Most AI agents that monitor the web work like this: check a page, send it to the LLM, get an answer, repeat.

Every hour. Every page. Whether anything changed or not.

The LLM doesn't know the page is identical to what it saw yesterday. It reads it, thinks, and gives you the same answer it gave you last time. You paid full price for a duplicate.

This isn't a hypothetical. It's the default behavior of every naive web monitoring agent, and most production agents are naive about this.

---

## The math

Say you're running a modest setup: 20 URLs, checked every hour.

- 20 pages × 24 hours = **480 LLM calls per day**
- Average page: ~1,500 tokens to read
- Total: **720,000 tokens per day just for monitoring**

Now ask: how often do those 20 pages actually change? For most use cases — competitor pricing, news, supply chain, regulatory — maybe 5–10% of checks find a real change.

That means **90%+ of your token spend is returning answers you already have.**

At scale this compounds fast. A team running 100 monitored URLs burns through millions of tokens a week, most of it noise.

---

## Why it happens

The fix seems obvious in hindsight: check if the page changed before calling the LLM. But there are two real friction points that stop most teams from implementing it properly.

**Getting the data in the first place.** Web scraping at any consistent frequency gets blocked. Bot detection, CAPTCHAs, IP bans — a monitoring agent that can't reliably fetch pages is useless, and building around this is a real infrastructure problem.

**The boilerplate cost.** Hashing page content, storing snapshots, diffing on change, caching LLM results — none of it is hard, but it's work that sits outside whatever you actually want to build. Teams skip it and call the LLM every time because it's the path of least resistance.

The result is a system that technically works but quietly wastes most of its compute budget.

---

## What the right setup looks like

The logic is simple once you have the infrastructure:

1. Fetch the page live (fresh data on every run — no stale cache)
2. Hash the content and compare to last time
3. If identical: return the cached answer, skip the LLM entirely
4. If changed: send only the diff to the LLM, not the full page

Step 4 matters as much as step 3. When a pricing page updates one number, you don't need the LLM to read 1,500 tokens — you need it to read 50. Cost proportional to what changed, not the size of the page.

In practice this looks like:

```
24 hours, 10 pages, hourly checks:
  240 total fetches
  ~20 LLM calls (pages that actually changed)
  220 cache hits (instant, free)
  Efficiency: ~92%
```

The 240 fetches still happen — you need live data. But the LLM only fires when there's something real to analyze.

---

## Indra

This is exactly what I built [Indra](https://github.com/smartass-4ever/Indra) to do.

It handles the fetching through [Bright Data](https://brightdata.com) — so bot detection, JavaScript rendering, geo-blocks, and CAPTCHAs are dealt with transparently on every run. And it wraps the full fingerprint-diff-cache pipeline so none of that boilerplate lands in your codebase.

```python
import indra

agent = indra.init(brightdata_api_key="your-key")

result = agent.watch(
    url="https://competitor.com/pricing",
    question="Did any prices change? What are the implications?",
    generation_fn=my_llm_call,  # only fires when the page actually changed
)

print(result.insight)        # LLM answer, or cached if unchanged
print(result.tokens_saved)   # tokens skipped this run
print(result.cost_saved_usd) # dollar value of what was skipped
```

After a session across multiple pages:

```
──────────────────────────────────────────────────
  Indra Session Summary
──────────────────────────────────────────────────
  Bright Data fetches : 24
  Changes detected    : 3
  LLM calls fired     : 3
  Cache hits          : 21
  Tokens saved        : 31,500
  Cost saved          : $0.0945
  Efficiency          : 87%
──────────────────────────────────────────────────
```

87% of LLM calls eliminated. The ones that fired were the ones that mattered.

---

## Who this affects

If you're building or running any of these, this cost is already hitting you:

- **Competitor intelligence** — pricing pages, feature pages, job boards
- **News and signal monitoring** — industry sites, press releases, government sources
- **Supply chain tracking** — supplier inventory, lead times, availability
- **Regulatory and compliance** — policy pages, filing databases
- **SEO and ranking** — SERP tracking for branded or competitive queries

The common thread: you need to check frequently, but real changes are rare. The gap between check frequency and change frequency is where the waste lives.

---

## The bigger picture

LLM costs are coming down. That's true. But the pattern of calling an LLM on unchanged data isn't a cost problem — it's an architecture problem. Cheaper tokens just means you burn more of them before you notice.

Building change awareness into the monitoring layer is the right fix regardless of price. You get lower costs now, and a system that scales without linearly scaling its compute spend.

---

```bash
pip install indra-ai
```

It's early and we're still ironing things out — but if wasted monitoring tokens are already showing up in your bill, it's worth a look.

- [GitHub](https://github.com/smartass-4ever/Indra)
- [PyPI](https://pypi.org/project/indra-ai/)
