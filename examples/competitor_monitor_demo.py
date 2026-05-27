"""
Indra Demo: Competitor Intelligence Monitor
============================================

Watches 5 competitor/news pages via Bright Data.
Simulates 3 rounds of checks (as if running hourly).
Only fires the LLM when a page actually changes.

Run:
    export BRIGHTDATA_API_KEY="your-key"
    export ANTHROPIC_API_KEY="your-key"   # or set any LLM
    python examples/competitor_monitor_demo.py

What to watch for:
  - Round 1: all pages fetched, all analysed (baseline run)
  - Round 2: most pages unchanged → LLM skipped, tokens saved
  - Round 3: same — savings stack up
  - Final dashboard shows total cost saved vs naive approach
"""

import os
import time

import anthropic

import indra

# ── Config ────────────────────────────────────────────────────────────────────

BRIGHTDATA_API_KEY = os.environ.get("BRIGHTDATA_API_KEY", "")
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")

# Pages to monitor — real public sites, variety of change frequency
MONITORED_PAGES = [
    {
        "url":      "https://openai.com/api/pricing/",
        "question": "Did any API prices change? List specific model prices if changed.",
    },
    {
        "url":      "https://www.anthropic.com/pricing",
        "question": "Did any model prices or tiers change?",
    },
    {
        "url":      "https://news.ycombinator.com/",
        "question": "What are the top 3 AI or infrastructure stories right now?",
    },
    {
        "url":      "https://techcrunch.com/category/artificial-intelligence/",
        "question": "Are there any major AI funding or product announcements?",
    },
    {
        "url":      "https://github.com/trending",
        "question": "What new AI/ML repositories are trending today?",
    },
]

ROUNDS    = 3      # simulates 3 hourly checks
ROUND_GAP = 2      # seconds between rounds in demo (would be 3600 in production)


# ── LLM setup ────────────────────────────────────────────────────────────────

def make_llm_fn():
    if not ANTHROPIC_API_KEY:
        print("[DEMO] No ANTHROPIC_API_KEY — insights will show raw diffs instead of LLM analysis.")
        return None

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def call_llm(prompt: str) -> str:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    return call_llm


# ── Demo runner ───────────────────────────────────────────────────────────────

def run_demo():
    print("\n" + "=" * 60)
    print("  Indra — Web Intelligence That Only Thinks When")
    print("  the Web Changes")
    print("  Powered by Bright Data + Mnemon")
    print("=" * 60 + "\n")

    if not BRIGHTDATA_API_KEY:
        print("ERROR: Set BRIGHTDATA_API_KEY environment variable to run this demo.")
        print("  export BRIGHTDATA_API_KEY='your-bright-data-key'")
        return

    agent   = indra.init(brightdata_api_key=BRIGHTDATA_API_KEY, db_path="demo_indra.db")
    llm_fn  = make_llm_fn()
    question_map = {p["url"]: p["question"] for p in MONITORED_PAGES}

    for round_num in range(1, ROUNDS + 1):
        print(f"\n{'─'*60}")
        print(f"  Round {round_num} — {'Baseline (first run)' if round_num == 1 else 'Incremental check'}")
        print(f"{'─'*60}")

        for page in MONITORED_PAGES:
            url      = page["url"]
            question = page["question"]

            result = agent.watch(
                url=url,
                question=question,
                generation_fn=llm_fn,
            )

            status = "CHANGED ↑" if result.changed else "unchanged ·"
            saved  = f"saved {result.tokens_saved} tokens" if result.tokens_saved else "first run"
            print(f"  {status} {url[:55]:<55} {saved}")

            if result.changed and result.insight:
                print(f"           → {result.insight[:120]}...")

        s = agent.stats()
        print(
            f"\n  Running total: "
            f"{s['brightdata_fetches']} BD fetches | "
            f"{s['llm_calls_fired']} LLM calls | "
            f"{s['tokens_saved']:,} tokens saved | "
            f"${s['cost_saved_usd']:.4f} saved"
        )

        if round_num < ROUNDS:
            print(f"\n  (waiting {ROUND_GAP}s before next round...)")
            time.sleep(ROUND_GAP)

    agent.print_stats()

    # Show the value prop clearly
    s = agent.stats()
    naive_calls  = s["brightdata_fetches"]
    actual_calls = s["llm_calls_fired"]
    if naive_calls > 0 and actual_calls < naive_calls:
        reduction = round(100 * (1 - actual_calls / naive_calls))
        print(f"  Naive approach would have fired {naive_calls} LLM calls.")
        print(f"  Indra fired {actual_calls} — a {reduction}% reduction.\n")

    agent.close()


if __name__ == "__main__":
    run_demo()
