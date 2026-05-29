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


def _load_env():
    """Load .env file from current directory if present."""
    env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val

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
        "url":      "https://techcrunch.com/category/artificial-intelligence/",
        "question": "Are there any major AI funding or product announcements?",
    },
    {
        "url":      "https://github.com/trending",
        "question": "What new AI/ML repositories are trending today?",
    },
]

ROUNDS    = 3
ROUND_GAP = int(os.environ.get("INDRA_DEMO_GAP", "30"))  # seconds between rounds (30 = HN will change)


def _make_llm_fn():
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if groq_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")

            def call_groq(prompt: str) -> str:
                msg = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.choices[0].message.content

            print("[demo] LLM: Groq (llama-3.1-8b-instant)")
            return call_groq
        except ImportError:
            print("[demo] openai package not installed — pip install openai")
            return None

    grok_key = os.environ.get("GROK_API_KEY", "")
    if grok_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=grok_key, base_url="https://api.x.ai/v1")

            def call_grok(prompt: str) -> str:
                msg = client.chat.completions.create(
                    model="grok-3-mini",
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.choices[0].message.content

            print("[demo] LLM: Grok (grok-3-mini)")
            return call_grok
        except ImportError:
            print("[demo] openai package not installed — pip install openai")
            return None

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)

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

    print("[demo] No GROQ_API_KEY, GROK_API_KEY, or ANTHROPIC_API_KEY — showing raw diffs instead of LLM analysis.")
    return None


def _countdown(seconds: int) -> None:
    """Print a live countdown so the terminal isn't silent during waits."""
    for remaining in range(seconds, 0, -1):
        print(f"\r  Next check in {remaining:3d}s ... ", end="", flush=True)
        time.sleep(1)
    print("\r" + " " * 30 + "\r", end="", flush=True)


def run_demo():
    _load_env()
    import indra

    api_key = os.environ.get("BRIGHTDATA_API_KEY", "")
    if not api_key:
        print("Error: set BRIGHTDATA_API_KEY before running the demo.")
        print("  export BRIGHTDATA_API_KEY='your-bright-data-key'")
        return

    print("\n" + "=" * 60)
    print("  Indra  -  Web Intelligence That Only Thinks When")
    print("            the Web Changes")
    print("  Powered by Bright Data + Mnemon")
    print("=" * 60)

    agent  = indra.init(brightdata_api_key=api_key, db_path="indra_demo.db")
    llm_fn = _make_llm_fn()

    bd_mode = "Bright Data Web Unlocker" if agent._bd.using_brightdata else "direct requests (no zone configured)"
    print(f"\n  Fetch mode : {bd_mode}")
    if os.environ.get("GROQ_API_KEY"):
        llm_label = "Groq llama-3.1-8b-instant"
    elif os.environ.get("GROK_API_KEY"):
        llm_label = "Grok grok-3-mini"
    elif llm_fn:
        llm_label = "Anthropic claude-haiku-4-5-20251001"
    else:
        llm_label = "disabled (set GROQ_API_KEY, GROK_API_KEY, or ANTHROPIC_API_KEY)"
    print(f"  LLM        : {llm_label}")
    print(f"  Pages      : {len(MONITORED_PAGES)}")
    print(f"  Rounds     : {ROUNDS}  (gap: {ROUND_GAP}s)")

    for round_num in range(1, ROUNDS + 1):
        print(f"\n{'=' * 60}")
        print(f"  Round {round_num} / {ROUNDS}  -  {'Baseline (first observation)' if round_num == 1 else 'Incremental check'}")
        print(f"{'=' * 60}")

        changed_this_round = 0
        for page in MONITORED_PAGES:
            result = agent.watch(
                url=page["url"],
                question=page["question"],
                generation_fn=llm_fn,
            )
            if result.changed:
                changed_this_round += 1
                saved = f"saved {result.tokens_saved} tokens on diff"
                print(f"\n  *** CHANGED *** {result.url[:50]}")
                print(f"  Summary  : {result.summary}")
                if result.insight:
                    # wrap at 70 chars
                    words  = result.insight.split()
                    line   = "  Insight  : "
                    lines  = []
                    for w in words:
                        if len(line) + len(w) + 1 > 72:
                            lines.append(line)
                            line = "             " + w + " "
                        else:
                            line += w + " "
                    if line.strip():
                        lines.append(line)
                    print("\n".join(lines))
                print(f"  Tokens   : {saved}\n")
            else:
                saved = f"saved {result.tokens_saved} tokens" if result.tokens_saved else "first observation"
                label = result.url.replace("https://", "").replace("http://", "")
                print(f"  unchanged   {label[:52]:<52}  {saved}")

        s = agent.stats()
        print(
            f"\n  Running total:  "
            f"{s['brightdata_fetches']} fetches  |  "
            f"{s['llm_calls_fired']} LLM calls  |  "
            f"{s['tokens_saved']:,} tokens saved  |  "
            f"${s['cost_saved_usd']:.4f} saved"
        )

        if round_num < ROUNDS:
            _countdown(ROUND_GAP)

    agent.print_stats()

    s = agent.stats()
    if s["brightdata_fetches"] > 0 and s["llm_calls_fired"] < s["brightdata_fetches"]:
        reduction = round(100 * (1 - s["llm_calls_fired"] / s["brightdata_fetches"]))
        print(f"  Naive approach : {s['brightdata_fetches']} LLM calls for {s['brightdata_fetches']} pages.")
        print(f"  Indra          : {s['llm_calls_fired']} LLM calls — {reduction}% reduction.\n")

    agent.close()


QUICK_PAGES = [
    {
        "url":      "https://techcrunch.com/category/artificial-intelligence/",
        "question": "Are there any major AI funding or product announcements?",
    },
    {
        "url":      "https://www.anthropic.com/pricing",
        "question": "Did any model prices or tiers change?",
    },
    {
        "url":      "https://github.com/trending",
        "question": "What new AI/ML repositories are trending today?",
    },
]


def run_quick_demo():
    _load_env()
    import indra

    api_key = os.environ.get("BRIGHTDATA_API_KEY", "")
    if not api_key:
        print("Error: set BRIGHTDATA_API_KEY before running the demo.")
        return

    # Fresh start every time — clear demo and Mnemon DBs
    import glob as _glob
    patterns = ["indra_demo*.db*", "mnemon_*_indra.db*", "mnemon_bus_indra.json"]
    for pattern in patterns:
        for f in _glob.glob(pattern):
            try:
                os.remove(f)
            except OSError:
                pass

    print("\n" + "=" * 60)
    print("  Indra  —  Web Intelligence That Only Thinks")
    print("            When the Web Changes")
    print("  Powered by Bright Data")
    print("=" * 60)

    agent  = indra.init(
        brightdata_api_key=api_key,
        db_path="indra_demo.db",
        unlocker_zone=os.environ.get("BRIGHTDATA_UNLOCKER_ZONE", ""),
        silent=True,
    )
    llm_fn = _make_llm_fn()

    bd_mode = "Bright Data Web Unlocker" if agent._bd.using_brightdata else "direct requests"
    print(f"\n  Fetching via : {bd_mode}")
    print(f"  Pages        : {len(QUICK_PAGES)}")

    # Round 1 — baseline
    print(f"\n{'=' * 60}")
    print("  Round 1 — Fetching baselines")
    print(f"{'=' * 60}")
    for page in QUICK_PAGES:
        result = agent.watch(url=page["url"], question=page["question"], generation_fn=llm_fn)
        print(f"  fetched   {result.url.replace('https://','')[:55]}")

    # Round 2 — detect changes immediately
    print(f"\n{'=' * 60}")
    print("  Round 2 — Checking for changes")
    print(f"{'=' * 60}")
    for page in QUICK_PAGES:
        result = agent.watch(url=page["url"], question=page["question"], generation_fn=llm_fn)
        if result.changed:
            print(f"\n  *** CHANGED *** {result.url.replace('https://','')[:50]}")
            if result.insight:
                words, line, lines = result.insight.split(), "  Insight : ", []
                for w in words:
                    if len(line) + len(w) + 1 > 72:
                        lines.append(line)
                        line = "             " + w + " "
                    else:
                        line += w + " "
                if line.strip():
                    lines.append(line)
                print("\n".join(lines))
            print(f"  Saved    : {result.tokens_saved} tokens  (${result.cost_saved_usd:.4f})\n")
        else:
            saved = f"saved {result.tokens_saved} tokens" if result.tokens_saved else "no prior snapshot"
            print(f"  unchanged {result.url.replace('https://','')[:52]:<52}  {saved}")

    # Round 3 — check again immediately, nothing changed, 0 LLM calls
    print(f"\n{'=' * 60}")
    print("  Round 3 — Checking again (no time has passed)")
    print(f"{'=' * 60}")
    for page in QUICK_PAGES:
        result = agent.watch(url=page["url"], question=page["question"], generation_fn=llm_fn)
        print(f"  unchanged {result.url.replace('https://','')[:52]:<52}  saved {result.tokens_saved} tokens")

    s = agent.stats()
    naive = s["brightdata_fetches"]
    reduction = round(100 * (1 - s["llm_calls_fired"] / naive)) if naive > 0 else 0
    print(f"\n{'=' * 60}")
    print(f"  Bright Data fetches : {s['brightdata_fetches']}")
    print(f"  LLM calls fired     : {s['llm_calls_fired']}  (naive would be {naive})")
    print(f"  Tokens saved        : {s['tokens_saved']:,}")
    print(f"  Cost saved          : ${s['cost_saved_usd']:.4f}")
    print(f"  Reduction           : {reduction}% fewer LLM calls")
    print(f"{'=' * 60}\n")

    agent.close()
