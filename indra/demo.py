"""
Indra demo: Competitor Intelligence Monitor.

Watches 5 real pages via Bright Data across 3 rounds.
Shows change detection + LLM savings in real time.

    export BRIGHTDATA_API_KEY="your-key"
    export ANTHROPIC_API_KEY="your-key"
    indra demo
"""

import os
import time

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

ROUNDS    = 3
ROUND_GAP = 2  # seconds (would be 3600 in production)


def _make_llm_fn():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[demo] No ANTHROPIC_API_KEY — showing raw diffs instead of LLM analysis.")
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        def call_llm(prompt: str) -> str:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text

        return call_llm
    except ImportError:
        print("[demo] anthropic package not installed — pip install anthropic")
        return None


def run_demo():
    import indra

    api_key = os.environ.get("BRIGHTDATA_API_KEY", "")
    if not api_key:
        print("Error: set BRIGHTDATA_API_KEY before running the demo.")
        print("  export BRIGHTDATA_API_KEY='your-bright-data-key'")
        return

    print("\n" + "=" * 60)
    print("  Indra — Web Intelligence That Only Thinks When")
    print("  the Web Changes")
    print("  Powered by Bright Data + Mnemon")
    print("=" * 60)

    agent  = indra.init(brightdata_api_key=api_key, db_path="indra_demo.db")
    llm_fn = _make_llm_fn()

    for round_num in range(1, ROUNDS + 1):
        print(f"\n{'-'*60}")
        print(f"  Round {round_num} — {'Baseline (first run)' if round_num == 1 else 'Incremental check'}")
        print(f"{'-'*60}")

        for page in MONITORED_PAGES:
            result = agent.watch(
                url=page["url"],
                question=page["question"],
                generation_fn=llm_fn,
            )
            status = "CHANGED ↑ " if result.changed else "unchanged ·"
            saved  = f"saved {result.tokens_saved} tokens" if result.tokens_saved else "first run"
            print(f"  {status} {result.url[:55]:<55} {saved}")

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
            print(f"\n  (waiting {ROUND_GAP}s...)")
            time.sleep(ROUND_GAP)

    agent.print_stats()

    s = agent.stats()
    if s["brightdata_fetches"] > 0 and s["llm_calls_fired"] < s["brightdata_fetches"]:
        reduction = round(100 * (1 - s["llm_calls_fired"] / s["brightdata_fetches"]))
        print(f"  Naive: {s['brightdata_fetches']} LLM calls.")
        print(f"  Indra: {s['llm_calls_fired']} — {reduction}% reduction.\n")

    agent.close()
