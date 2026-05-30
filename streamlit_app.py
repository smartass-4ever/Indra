"""
Indra — Live Demo
Web monitoring agent: fetch via Bright Data, pay only for what changed.
"""

import streamlit as st
import os
import time

st.set_page_config(
    page_title="Indra — Web Monitor",
    page_icon="🔍",
    layout="wide",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-box {
        background: #1e1e2e;
        border: 1px solid #313244;
        border-radius: 8px;
        padding: 16px 20px;
        text-align: center;
    }
    .metric-value { font-size: 28px; font-weight: 700; color: #cba6f7; }
    .metric-label { font-size: 12px; color: #6c7086; margin-top: 4px; }
    .changed-badge {
        background: #a6e3a1; color: #1e1e2e;
        padding: 2px 10px; border-radius: 12px;
        font-size: 12px; font-weight: 600;
    }
    .unchanged-badge {
        background: #313244; color: #cdd6f4;
        padding: 2px 10px; border-radius: 12px;
        font-size: 12px; font-weight: 600;
    }
    .diff-block {
        background: #1e1e2e;
        border-left: 3px solid #cba6f7;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        font-family: monospace;
        font-size: 13px;
        white-space: pre-wrap;
    }
    .insight-block {
        background: #1e1e2e;
        border-left: 3px solid #a6e3a1;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        font-size: 14px;
    }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.title("Indra")
st.markdown("**Web monitoring agent built on Bright Data.** Fetches every time. Calls the LLM only when something changes.")
st.markdown("`pip install indra-ai` · [GitHub](https://github.com/smartass-4ever/Indra) · [PyPI](https://pypi.org/project/indra-ai/)")
st.divider()

# ── API Key config ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Configuration")

    brightdata_key = st.text_input(
        "Bright Data API Key",
        value=os.getenv("BRIGHTDATA_API_KEY", ""),
        type="password",
        help="From your Bright Data dashboard"
    )
    unlocker_zone = st.text_input(
        "Web Unlocker Zone",
        value=os.getenv("BRIGHTDATA_UNLOCKER_ZONE", "web_unlocker1"),
        help="Your Bright Data Web Unlocker zone name"
    )
    groq_key = st.text_input(
        "Groq API Key",
        value=os.getenv("GROQ_API_KEY", ""),
        type="password",
        help="For LLM analysis on changes"
    )

    st.divider()
    st.caption("Keys are used only for this session and never stored.")

    st.divider()
    st.markdown("**How it works**")
    st.markdown("""
1. Bright Data fetches the page
2. SHA-256 fingerprint vs last snapshot
3. **Unchanged** → cached insight, 0 tokens
4. **Changed** → diff only sent to LLM (~300 tokens vs 1,500)
    """)

# ── Agent init ────────────────────────────────────────────────────────────────
def get_agent():
    key = brightdata_key or os.getenv("BRIGHTDATA_API_KEY")
    zone = unlocker_zone or os.getenv("BRIGHTDATA_UNLOCKER_ZONE")
    if "agent" not in st.session_state or st.session_state.get("agent_key") != key:
        try:
            import indra
            agent = indra.init(
                brightdata_api_key=key,
                unlocker_zone=zone,
                db_path="indra_streamlit.db",
                silent=True,
            )
            st.session_state.agent = agent
            st.session_state.agent_key = key
        except Exception as e:
            st.error(f"Failed to init Indra: {e}")
            return None
    return st.session_state.agent


def get_llm_fn():
    key = groq_key or os.getenv("GROQ_API_KEY")
    if not key:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=key)
        def generate(prompt: str) -> str:
            msg = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.choices[0].message.content
        return generate
    except Exception:
        return None


# ── Watch history ─────────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []
if "preset_url" not in st.session_state:
    st.session_state.preset_url = ""
if "preset_question" not in st.session_state:
    st.session_state.preset_question = ""

# ── Preset URLs ───────────────────────────────────────────────────────────────
st.caption("Try a preset:")
preset_cols = st.columns(4)
presets = [
    ("OpenAI Pricing", "https://openai.com/api/pricing/", "Did API prices change?"),
    ("Anthropic Pricing", "https://www.anthropic.com/pricing", "Did pricing change?"),
    ("GitHub Trending", "https://github.com/trending", "What are the top trending repos?"),
    ("HN Front Page", "https://news.ycombinator.com/", "What are the top stories?"),
]
for i, (label, preset_url, preset_q) in enumerate(presets):
    if preset_cols[i].button(label, use_container_width=True):
        st.session_state.preset_url = preset_url
        st.session_state.preset_question = preset_q

# ── Main input ────────────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    url = st.text_input(
        "URL to watch",
        value=st.session_state.preset_url,
        placeholder="https://competitor.com/pricing",
        label_visibility="collapsed"
    )
with col2:
    render_js = st.checkbox("Render JS", value=False, help="Enable for JavaScript-heavy pages")

question = st.text_input(
    "Question",
    value=st.session_state.preset_question,
    placeholder="What changed? Did prices update?",
    label_visibility="collapsed"
)

watch_btn = st.button("Watch", type="primary", use_container_width=True)

st.divider()

# ── Run watch ─────────────────────────────────────────────────────────────────
if watch_btn and url and question:
    agent = get_agent()
    if agent:
        llm_fn = get_llm_fn()
        if not llm_fn:
            st.warning("No Anthropic API key — showing raw diff without LLM analysis.")

        with st.spinner(f"Fetching {url} via Bright Data..."):
            t0 = time.time()
            try:
                result = agent.watch(
                    url=url,
                    question=question,
                    generation_fn=llm_fn,
                    render_js=render_js,
                )
                elapsed = (time.time() - t0) * 1000
                st.session_state.history.insert(0, result)
            except Exception as e:
                st.error(f"Watch failed: {e}")
                result = None

        if result:
            # Status badge
            if result.changed:
                st.markdown('<span class="changed-badge">CHANGED</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="unchanged-badge">NO CHANGE</span>', unsafe_allow_html=True)

            st.caption(f"{result.url} · {result.summary} · {result.latency_ms:.0f}ms")

            # Metrics row
            m1, m2, m3, m4 = st.columns(4)
            m1.markdown(f'<div class="metric-box"><div class="metric-value">{result.tokens_saved:,}</div><div class="metric-label">Tokens Saved</div></div>', unsafe_allow_html=True)
            m2.markdown(f'<div class="metric-box"><div class="metric-value">${result.cost_saved_usd:.4f}</div><div class="metric-label">Cost Saved</div></div>', unsafe_allow_html=True)
            m3.markdown(f'<div class="metric-box"><div class="metric-value">{"Yes" if result.brightdata_called else "No"}</div><div class="metric-label">Bright Data Called</div></div>', unsafe_allow_html=True)
            m4.markdown(f'<div class="metric-box"><div class="metric-value">{result.change_count}</div><div class="metric-label">Total Changes Seen</div></div>', unsafe_allow_html=True)

            st.markdown("")

            # Insight + Diff
            if result.insight:
                st.markdown("**LLM Insight**")
                st.markdown(f'<div class="insight-block">{result.insight}</div>', unsafe_allow_html=True)
                st.markdown("")

            if result.diff:
                st.markdown("**Diff** (what changed)")
                st.markdown(f'<div class="diff-block">{result.diff}</div>', unsafe_allow_html=True)
            elif not result.changed:
                st.info("Page is identical to last snapshot — cached insight returned, 0 tokens spent.")

elif watch_btn:
    st.warning("Enter a URL and a question first.")

# ── Session stats ─────────────────────────────────────────────────────────────
if st.session_state.history:
    st.divider()
    st.subheader("Session Stats")

    agent = get_agent()
    if agent:
        try:
            stats = agent.stats()
            s1, s2, s3, s4, s5 = st.columns(5)
            s1.metric("Bright Data Fetches", stats.get("brightdata_fetches", 0))
            s2.metric("LLM Calls Fired", stats.get("llm_calls_fired", 0))
            s3.metric("Cache Hits", stats.get("cache_hits", 0))
            s4.metric("Tokens Saved", f"{stats.get('tokens_saved', 0):,}")
            s5.metric("Efficiency", f"{stats.get('efficiency_pct', 0)}%")
        except Exception:
            pass

    st.subheader("History")
    for r in st.session_state.history:
        with st.expander(f"{'🟢' if r.changed else '⚪'} {r.url} — {r.summary}"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Tokens Saved", r.tokens_saved)
            c2.metric("Cost Saved", f"${r.cost_saved_usd:.4f}")
            c3.metric("Latency", f"{r.latency_ms:.0f}ms")
            if r.insight:
                st.markdown(f"**Insight:** {r.insight}")
            if r.diff:
                st.code(r.diff, language="diff")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Indra · Built for the Bright Data Web Data UNLOCKED Hackathon · [github.com/smartass-4ever/Indra](https://github.com/smartass-4ever/Indra)")
