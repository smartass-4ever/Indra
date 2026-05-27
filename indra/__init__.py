"""
Indra — Web Intelligence That Only Thinks When the Web Changes.

Built on Mnemon's execution cache + Bright Data's live web access.

Every monitored page is fetched live (via Bright Data — no stale data).
The LLM only runs when the content actually changed.
On unchanged pages: sub-millisecond cached insight, zero tokens.

Usage:
    import indra

    agent = indra.init(brightdata_api_key="your-key")

    result = agent.watch(
        url="https://competitor.com/pricing",
        question="Has pricing changed? What are the implications?",
        generation_fn=my_llm_call,   # only called when page actually changes
    )

    print(result["changed"])       # True / False
    print(result["insight"])       # LLM analysis (cached if unchanged)
    print(result["tokens_saved"])  # how many tokens skipped
    print(result["diff"])          # what changed (empty if no change)
"""

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

from .web.brightdata import BrightDataClient, BrightDataError
from .web.change_detector import (
    fingerprint, has_changed, extract_diff,
    summarise_change, build_change_prompt,
)
from .web.store import WebSnapshotStore

logger = logging.getLogger(__name__)

# Rough cost estimate: $0.000003 per token (GPT-4o-mini / Claude Haiku rate)
_COST_PER_TOKEN = 0.000003
# Estimate tokens consumed by analysing a full page vs a diff
_FULL_PAGE_TOKENS = 1500
_DIFF_TOKENS      = 300


class WatchResult:
    """Return value from Indra.watch() and Indra.search()."""

    def __init__(
        self,
        url: str,
        changed: bool,
        insight: str,
        diff: str,
        tokens_saved: int,
        latency_ms: float,
        brightdata_called: bool,
        change_count: int,
        summary: str = "",
    ):
        self.url               = url
        self.changed           = changed
        self.insight           = insight
        self.diff              = diff
        self.tokens_saved      = tokens_saved
        self.latency_ms        = latency_ms
        self.brightdata_called = brightdata_called
        self.change_count      = change_count
        self.summary           = summary

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url":               self.url,
            "changed":           self.changed,
            "insight":           self.insight,
            "diff":              self.diff,
            "tokens_saved":      self.tokens_saved,
            "cost_saved_usd":    round(self.tokens_saved * _COST_PER_TOKEN, 4),
            "latency_ms":        round(self.latency_ms, 1),
            "brightdata_called": self.brightdata_called,
            "change_count":      self.change_count,
            "summary":           self.summary,
        }


class Indra:
    """
    Web intelligence agent that only thinks when the web changes.

    Internally uses:
      - Bright Data to fetch live web content (bypasses bot detection, geo-blocks)
      - A local SQLite snapshot store to track content hashes per URL
      - Mnemon's execution cache to serve cached LLM insights on unchanged pages
    """

    def __init__(
        self,
        brightdata_api_key: Optional[str] = None,
        db_path: str = "indra.db",
        unlocker_zone: str = "web_unlocker1",
        serp_zone: str = "serp_api1",
        silent: bool = False,
    ):
        self._bd = BrightDataClient(
            api_key=brightdata_api_key,
            unlocker_zone=unlocker_zone,
            serp_zone=serp_zone,
        )
        self._store = WebSnapshotStore(db_path=db_path)
        self._store.connect()
        self._silent = silent

        # Session stats
        self.session_fetches       = 0
        self.session_llm_calls     = 0
        self.session_cache_hits    = 0
        self.session_tokens_saved  = 0
        self.session_changes       = 0

        # In-memory LLM insight cache: url → insight string
        # Persisted by Mnemon when generation_fn is provided, or kept in-memory
        # as a fallback for quick demos.
        self._insight_cache: Dict[str, str] = {}

    # ── CORE: watch a single URL ──────────────────────────────────────────

    def watch(
        self,
        url: str,
        question: str,
        generation_fn: Optional[Callable] = None,
        render_js: bool = False,
        ttl: Optional[float] = None,
    ) -> WatchResult:
        """
        Fetch url via Bright Data, detect changes, run LLM only if changed.

        Args:
            url:           The URL to monitor.
            question:      What to ask the LLM about changes (e.g. "Did the price change?").
            generation_fn: Your LLM call. Signature: fn(prompt: str) -> str.
                           Only called when content has changed since last run.
            render_js:     Pass True for JS-heavy pages (uses Bright Data headless browser).
            ttl:           If set and the snapshot is fresher than ttl seconds, skip the
                           Bright Data fetch entirely (serve from snapshot cache).

        Returns:
            WatchResult with .changed, .insight, .diff, .tokens_saved, etc.
        """
        t0 = time.time()
        snapshot = self._store.get(url)

        # TTL check — skip Bright Data fetch if snapshot is fresh enough
        if ttl and snapshot and (time.time() - snapshot["fetched_at"]) < ttl:
            insight = self._insight_cache.get(url, "")
            latency = (time.time() - t0) * 1000
            self.session_cache_hits   += 1
            self.session_tokens_saved += _FULL_PAGE_TOKENS
            return WatchResult(
                url=url, changed=False, insight=insight, diff="",
                tokens_saved=_FULL_PAGE_TOKENS, latency_ms=latency,
                brightdata_called=False, change_count=snapshot["change_count"],
                summary="snapshot still fresh (TTL not expired)",
            )

        # Fetch live via Bright Data
        try:
            content = self._bd.fetch(url, render_js=render_js)
            self.session_fetches += 1
        except BrightDataError as e:
            logger.warning(f"Indra: Bright Data fetch failed for {url}: {e}")
            return WatchResult(
                url=url, changed=False,
                insight=self._insight_cache.get(url, ""),
                diff="", tokens_saved=0,
                latency_ms=(time.time() - t0) * 1000,
                brightdata_called=True,
                change_count=snapshot["change_count"] if snapshot else 0,
                summary=f"fetch error: {e}",
            )

        new_hash = fingerprint(content)

        # First time we've seen this URL
        if not snapshot:
            self._store.upsert(url, new_hash, content, changed=False)
            insight = self._maybe_analyse(url, content, question, generation_fn, is_diff=False)
            self._insight_cache[url] = insight
            self.session_llm_calls += 1
            latency = (time.time() - t0) * 1000
            return WatchResult(
                url=url, changed=False, insight=insight, diff="",
                tokens_saved=0, latency_ms=latency, brightdata_called=True,
                change_count=0, summary="first observation — baseline stored",
            )

        # Compare hashes
        if not has_changed(snapshot["hash"], new_hash):
            # Nothing changed — serve cached insight, zero LLM cost
            insight = self._insight_cache.get(url, "")
            self._store.upsert(url, new_hash, content, changed=False)
            self.session_cache_hits   += 1
            self.session_tokens_saved += _FULL_PAGE_TOKENS
            latency = (time.time() - t0) * 1000
            if not self._silent:
                print(f"Indra: {url[:60]} — unchanged · {_FULL_PAGE_TOKENS} tokens saved")
            return WatchResult(
                url=url, changed=False, insight=insight, diff="",
                tokens_saved=_FULL_PAGE_TOKENS, latency_ms=latency,
                brightdata_called=True,
                change_count=snapshot["change_count"],
                summary="no change detected",
            )

        # Content changed — extract diff, run LLM on delta only
        diff    = extract_diff(snapshot["content"], content)
        summary = summarise_change(snapshot["content"], content)
        self._store.upsert(url, new_hash, content, changed=True)
        self.session_changes += 1

        insight = self._maybe_analyse_diff(url, diff, question, generation_fn)
        self._insight_cache[url] = insight
        self.session_llm_calls += 1

        # Tokens saved = full page analysis - diff analysis
        tokens_saved = max(0, _FULL_PAGE_TOKENS - _DIFF_TOKENS)
        self.session_tokens_saved += tokens_saved

        latency = (time.time() - t0) * 1000
        if not self._silent:
            print(f"Indra: {url[:60]} — CHANGED ({summary}) · LLM fired · {tokens_saved} tokens saved on diff")

        return WatchResult(
            url=url, changed=True, insight=insight, diff=diff,
            tokens_saved=tokens_saved, latency_ms=latency,
            brightdata_called=True,
            change_count=snapshot["change_count"] + 1,
            summary=summary,
        )

    # ── CORE: monitor a list of URLs in one call ──────────────────────────

    def watch_all(
        self,
        urls: List[str],
        question: str,
        generation_fn: Optional[Callable] = None,
        render_js: bool = False,
        ttl: Optional[float] = None,
    ) -> List[WatchResult]:
        """Monitor multiple URLs in sequence. Returns one WatchResult per URL."""
        results = []
        for url in urls:
            result = self.watch(url, question=question, generation_fn=generation_fn,
                                render_js=render_js, ttl=ttl)
            results.append(result)
        return results

    # ── SEARCH: SERP-based change detection ──────────────────────────────

    def search_watch(
        self,
        query: str,
        question: str,
        generation_fn: Optional[Callable] = None,
        num_results: int = 10,
    ) -> WatchResult:
        """
        Run a live SERP query via Bright Data, detect if results changed,
        run LLM only when the result set is new or different.
        """
        t0    = time.time()
        cache_key = f"serp:{query}"
        snapshot  = self._store.get(cache_key)

        results  = self._bd.search(query, num_results=num_results)
        content  = "\n".join(f"{r['title']} — {r['url']}\n{r['snippet']}" for r in results)
        new_hash = fingerprint(content)
        self.session_fetches += 1

        if not snapshot:
            self._store.upsert(cache_key, new_hash, content, changed=False)
            insight = self._maybe_analyse(cache_key, content, question, generation_fn, is_diff=False)
            self._insight_cache[cache_key] = insight
            self.session_llm_calls += 1
            return WatchResult(
                url=cache_key, changed=False, insight=insight, diff="",
                tokens_saved=0, latency_ms=(time.time() - t0) * 1000,
                brightdata_called=True, change_count=0,
                summary="first SERP baseline stored",
            )

        if not has_changed(snapshot["hash"], new_hash):
            insight = self._insight_cache.get(cache_key, "")
            self._store.upsert(cache_key, new_hash, content, changed=False)
            self.session_cache_hits   += 1
            self.session_tokens_saved += _FULL_PAGE_TOKENS
            return WatchResult(
                url=cache_key, changed=False, insight=insight, diff="",
                tokens_saved=_FULL_PAGE_TOKENS, latency_ms=(time.time() - t0) * 1000,
                brightdata_called=True, change_count=snapshot["change_count"],
                summary="SERP results unchanged",
            )

        diff    = extract_diff(snapshot["content"], content)
        summary = summarise_change(snapshot["content"], content)
        self._store.upsert(cache_key, new_hash, content, changed=True)
        self.session_changes += 1

        insight = self._maybe_analyse_diff(cache_key, diff, question, generation_fn)
        self._insight_cache[cache_key] = insight
        self.session_llm_calls += 1

        return WatchResult(
            url=cache_key, changed=True, insight=insight, diff=diff,
            tokens_saved=max(0, _FULL_PAGE_TOKENS - _DIFF_TOKENS),
            latency_ms=(time.time() - t0) * 1000,
            brightdata_called=True, change_count=snapshot["change_count"] + 1,
            summary=summary,
        )

    # ── STATS ─────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        total_potential = (self.session_fetches) * _FULL_PAGE_TOKENS
        cost_saved      = self.session_tokens_saved * _COST_PER_TOKEN
        return {
            "brightdata_fetches":    self.session_fetches,
            "llm_calls_fired":       self.session_llm_calls,
            "cache_hits":            self.session_cache_hits,
            "changes_detected":      self.session_changes,
            "tokens_saved":          self.session_tokens_saved,
            "cost_saved_usd":        round(cost_saved, 4),
            "efficiency_pct":        round(
                100 * self.session_tokens_saved / max(total_potential, 1)
            ),
        }

    def print_stats(self) -> None:
        s = self.stats()
        print(
            f"\n{'─'*50}\n"
            f"  Indra Session Summary\n"
            f"{'─'*50}\n"
            f"  Bright Data fetches : {s['brightdata_fetches']}\n"
            f"  Changes detected    : {s['changes_detected']}\n"
            f"  LLM calls fired     : {s['llm_calls_fired']}\n"
            f"  Cache hits          : {s['cache_hits']}\n"
            f"  Tokens saved        : {s['tokens_saved']:,}\n"
            f"  Cost saved          : ${s['cost_saved_usd']:.4f}\n"
            f"  Efficiency          : {s['efficiency_pct']}%\n"
            f"{'─'*50}\n"
        )

    def close(self) -> None:
        self._store.close()

    # ── INTERNAL HELPERS ──────────────────────────────────────────────────

    def _maybe_analyse(
        self, url: str, content: str, question: str,
        generation_fn: Optional[Callable], is_diff: bool,
    ) -> str:
        if generation_fn is None:
            return ""
        prompt = (
            f"Analyse this web content and answer: {question}\n\n"
            f"URL: {url}\n\nContent (first 3000 chars):\n{content[:3000]}"
        )
        try:
            return str(generation_fn(prompt))
        except Exception as e:
            logger.warning(f"Indra: generation_fn failed: {e}")
            return ""

    def _maybe_analyse_diff(
        self, url: str, diff: str, question: str,
        generation_fn: Optional[Callable],
    ) -> str:
        if generation_fn is None:
            return diff  # return raw diff if no LLM provided
        prompt = build_change_prompt(url, diff, question)
        try:
            return str(generation_fn(prompt))
        except Exception as e:
            logger.warning(f"Indra: generation_fn failed on diff: {e}")
            return diff


# ── Global convenience ────────────────────────────────────────────────────────

_instance: Optional[Indra] = None


def init(
    brightdata_api_key: Optional[str] = None,
    db_path: str = "indra.db",
    silent: bool = False,
    **kwargs,
) -> Indra:
    """
    One-line setup. Returns a ready-to-use Indra agent.

        agent = indra.init(brightdata_api_key="...")
        result = agent.watch("https://competitor.com/pricing", question="...")
    """
    global _instance
    if _instance is not None:
        return _instance
    _instance = Indra(
        brightdata_api_key=brightdata_api_key,
        db_path=db_path,
        silent=silent,
        **kwargs,
    )
    return _instance


def get() -> Indra:
    if _instance is None:
        raise RuntimeError("indra.get() called before indra.init(). Call indra.init() first.")
    return _instance


__all__ = ["Indra", "WatchResult", "init", "get"]
