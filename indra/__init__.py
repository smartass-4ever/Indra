"""
Indra — Web intelligence that only thinks when the web changes.

Every monitored page is fetched live via Bright Data (no stale data,
no bot detection failures). Indra fingerprints the response and compares
it to the last stored hash. If unchanged: return the cached LLM insight
instantly, zero tokens. If changed: extract the diff, send only the
delta to your LLM, cache the new insight via Mnemon.

Usage:
    import indra

    agent = indra.init(brightdata_api_key="your-key")

    result = agent.watch(
        url="https://competitor.com/pricing",
        question="Did prices change? What are the implications?",
        generation_fn=my_llm_call,
    )

    print(result.changed)        # True / False
    print(result.insight)        # LLM analysis, or cached if unchanged
    print(result.tokens_saved)   # tokens skipped this run
"""

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

from mnemon import MnemonSync

from .web.brightdata import BrightDataClient, BrightDataError
from .web.change_detector import (
    build_change_prompt,
    extract_diff,
    fingerprint,
    has_changed,
    summarise_change,
)
from .web.store import WebSnapshotStore

logger = logging.getLogger(__name__)


_COST_PER_TOKEN   = 0.000003
_FULL_PAGE_TOKENS = 1500
_DIFF_TOKENS      = 300


class WatchResult:
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
        self.cost_saved_usd    = round(tokens_saved * _COST_PER_TOKEN, 4)
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
    Web intelligence agent built on Bright Data + Mnemon.

    Bright Data fetches live content (bypasses bot detection, geo-blocks).
    Mnemon caches LLM insights so identical questions on identical diffs
    never hit the LLM twice — even across restarts.
    """

    def __init__(
        self,
        brightdata_api_key: Optional[str] = None,
        db_path: str = "indra.db",
        unlocker_zone: Optional[str] = None,
        serp_zone: Optional[str] = None,
        silent: bool = False,
    ):
        self._bd = BrightDataClient(
            api_key=brightdata_api_key,
            unlocker_zone=unlocker_zone,
            serp_zone=serp_zone,
        )

        self._store = WebSnapshotStore(db_path=db_path)
        self._store.connect()

        db_dir = os.path.dirname(os.path.abspath(db_path)) or "."
        self._mnemon = MnemonSync(
            tenant_id="indra",
            db_dir=db_dir,
            silent=True,
            prewarm_templates=False,
            prewarm_fragments=False,
            enable_telemetry=False,
        )
        self._mnemon.__enter__()

        self._silent = silent

        self.session_fetches      = 0
        self.session_llm_calls    = 0
        self.session_cache_hits   = 0
        self.session_tokens_saved = 0
        self.session_changes      = 0

    # ── watch ─────────────────────────────────────────────────────────────

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

        generation_fn signature: fn(prompt: str) -> str
        Only called when content has changed since the last run.
        """
        t0       = time.time()
        snapshot = self._store.get(url)

        # TTL shortcut — skip Bright Data fetch if snapshot is fresh enough
        if ttl and snapshot and (time.time() - snapshot["fetched_at"]) < ttl:
            self.session_cache_hits   += 1
            self.session_tokens_saved += _FULL_PAGE_TOKENS
            return WatchResult(
                url=url, changed=False,
                insight=snapshot.get("last_insight", ""),
                diff="", tokens_saved=_FULL_PAGE_TOKENS,
                latency_ms=(time.time() - t0) * 1000,
                brightdata_called=False,
                change_count=snapshot["change_count"],
                summary="snapshot still fresh (TTL not expired)",
            )

        # Fetch live via Bright Data
        try:
            content = self._bd.fetch(url, render_js=render_js)
            self.session_fetches += 1
        except BrightDataError as e:
            logger.warning(f"Indra: Bright Data fetch failed for {url}: {e}")
            return WatchResult(
                url=url, changed=False, insight="", diff="",
                tokens_saved=0, latency_ms=(time.time() - t0) * 1000,
                brightdata_called=True,
                change_count=snapshot["change_count"] if snapshot else 0,
                summary=f"fetch error: {e}",
            )

        new_hash = fingerprint(content)

        # First time seeing this URL — store baseline
        if not snapshot:
            self._store.upsert(url, new_hash, content, changed=False)
            insight = self._analyse(url, content[:3000], question, generation_fn, is_diff=False)
            self._store.set_insight(url, insight)
            self.session_llm_calls += 1
            return WatchResult(
                url=url, changed=False, insight=insight, diff="",
                tokens_saved=0, latency_ms=(time.time() - t0) * 1000,
                brightdata_called=True, change_count=0,
                summary="first observation — baseline stored",
            )

        # No change
        if not has_changed(snapshot["hash"], new_hash):
            self._store.upsert(url, new_hash, content, changed=False)
            self.session_cache_hits   += 1
            self.session_tokens_saved += _FULL_PAGE_TOKENS
            if not self._silent:
                print(f"Indra: {url[:60]} - unchanged - {_FULL_PAGE_TOKENS} tokens saved")
            return WatchResult(
                url=url, changed=False,
                insight=snapshot.get("last_insight", ""),
                diff="", tokens_saved=_FULL_PAGE_TOKENS,
                latency_ms=(time.time() - t0) * 1000,
                brightdata_called=True,
                change_count=snapshot["change_count"],
                summary="no change detected",
            )

        # Changed — extract diff, run LLM on delta only
        diff    = extract_diff(snapshot["content"], content)
        summary = summarise_change(snapshot["content"], content)
        self._store.upsert(url, new_hash, content, changed=True)
        self.session_changes += 1

        insight = self._analyse_diff(url, diff, question, generation_fn)
        self._store.set_insight(url, insight)
        self.session_llm_calls += 1

        tokens_saved = max(0, _FULL_PAGE_TOKENS - _DIFF_TOKENS)
        self.session_tokens_saved += tokens_saved

        if not self._silent:
            print(f"Indra: {url[:60]} - CHANGED ({summary}) - LLM fired - {tokens_saved} tokens saved on diff")

        return WatchResult(
            url=url, changed=True, insight=insight, diff=diff,
            tokens_saved=tokens_saved,
            latency_ms=(time.time() - t0) * 1000,
            brightdata_called=True,
            change_count=snapshot["change_count"] + 1,
            summary=summary,
        )

    def watch_all(
        self,
        urls: List[str],
        question: str,
        generation_fn: Optional[Callable] = None,
        render_js: bool = False,
        ttl: Optional[float] = None,
    ) -> List[WatchResult]:
        """Monitor multiple URLs in one call."""
        return [
            self.watch(url, question=question, generation_fn=generation_fn,
                       render_js=render_js, ttl=ttl)
            for url in urls
        ]

    def search_watch(
        self,
        query: str,
        question: str,
        generation_fn: Optional[Callable] = None,
        num_results: int = 10,
    ) -> WatchResult:
        """
        Run a live SERP query via Bright Data, detect if results changed,
        run LLM only when the result set is different from last time.
        """
        t0        = time.time()
        cache_key = f"serp:{query}"
        snapshot  = self._store.get(cache_key)

        results  = self._bd.search(query, num_results=num_results)
        content  = "\n".join(
            f"{r['title']} — {r['url']}\n{r['snippet']}" for r in results
        )
        new_hash = fingerprint(content)
        self.session_fetches += 1

        if not snapshot:
            self._store.upsert(cache_key, new_hash, content, changed=False)
            insight = self._analyse(cache_key, content, question, generation_fn, is_diff=False)
            self._store.set_insight(cache_key, insight)
            self.session_llm_calls += 1
            return WatchResult(
                url=cache_key, changed=False, insight=insight, diff="",
                tokens_saved=0, latency_ms=(time.time() - t0) * 1000,
                brightdata_called=True, change_count=0,
                summary="first SERP baseline stored",
            )

        if not has_changed(snapshot["hash"], new_hash):
            self._store.upsert(cache_key, new_hash, content, changed=False)
            self.session_cache_hits   += 1
            self.session_tokens_saved += _FULL_PAGE_TOKENS
            return WatchResult(
                url=cache_key, changed=False,
                insight=snapshot.get("last_insight", ""),
                diff="", tokens_saved=_FULL_PAGE_TOKENS,
                latency_ms=(time.time() - t0) * 1000,
                brightdata_called=True,
                change_count=snapshot["change_count"],
                summary="SERP results unchanged",
            )

        diff    = extract_diff(snapshot["content"], content)
        summary = summarise_change(snapshot["content"], content)
        self._store.upsert(cache_key, new_hash, content, changed=True)
        self.session_changes += 1

        insight = self._analyse_diff(cache_key, diff, question, generation_fn)
        self._store.set_insight(cache_key, insight)
        self.session_llm_calls += 1

        return WatchResult(
            url=cache_key, changed=True, insight=insight, diff=diff,
            tokens_saved=max(0, _FULL_PAGE_TOKENS - _DIFF_TOKENS),
            latency_ms=(time.time() - t0) * 1000,
            brightdata_called=True,
            change_count=snapshot["change_count"] + 1,
            summary=summary,
        )

    # ── stats ──────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        total     = max(self.session_fetches * _FULL_PAGE_TOKENS, 1)
        cost_saved = self.session_tokens_saved * _COST_PER_TOKEN
        return {
            "brightdata_fetches": self.session_fetches,
            "llm_calls_fired":    self.session_llm_calls,
            "cache_hits":         self.session_cache_hits,
            "changes_detected":   self.session_changes,
            "tokens_saved":       self.session_tokens_saved,
            "cost_saved_usd":     round(cost_saved, 4),
            "efficiency_pct":     round(100 * self.session_tokens_saved / total),
        }

    def print_stats(self) -> None:
        s   = self.stats()
        sep = "-" * 50
        print(
            f"\n{sep}\n"
            f"  Indra Session Summary\n"
            f"{sep}\n"
            f"  Bright Data fetches : {s['brightdata_fetches']}\n"
            f"  Changes detected    : {s['changes_detected']}\n"
            f"  LLM calls fired     : {s['llm_calls_fired']}\n"
            f"  Cache hits          : {s['cache_hits']}\n"
            f"  Tokens saved        : {s['tokens_saved']:,}\n"
            f"  Cost saved          : ${s['cost_saved_usd']:.4f}\n"
            f"  Efficiency          : {s['efficiency_pct']}%\n"
            f"{sep}\n"
        )

    def close(self) -> None:
        global _instance
        self._mnemon.__exit__(None, None, None)
        self._store.close()
        if _instance is self:
            _instance = None

    # ── internal ───────────────────────────────────────────────────────────

    def _analyse(
        self,
        url: str,
        content: str,
        question: str,
        generation_fn: Optional[Callable],
        is_diff: bool,
    ) -> str:
        if generation_fn is None:
            return ""
        prompt = (
            f"You are a web monitoring assistant. Reply with plain English only — "
            f"no JSON, no code blocks, no bullet points. Write exactly 1-2 sentences.\n\n"
            f"URL: {url}\n\nContent:\n{content[:3000]}\n\n"
            f"Question: {question}\n\n"
            f"Answer (1-2 plain sentences):"
        )
        return self._call_via_mnemon(prompt, url, generation_fn)

    def _analyse_diff(
        self,
        url: str,
        diff: str,
        question: str,
        generation_fn: Optional[Callable],
    ) -> str:
        if generation_fn is None:
            return diff
        prompt = build_change_prompt(url, diff, question)
        return self._call_via_mnemon(prompt, url, generation_fn)

    def _call_via_mnemon(self, prompt: str, url: str, generation_fn: Callable) -> str:
        """
        Run generation_fn through Mnemon so identical prompts hit the cache.
        Same URL + same diff + same question = zero LLM cost, even after restart.
        """
        def gen_fn(goal, inputs, context, caps, constraints):
            return generation_fn(goal)

        try:
            result = self._mnemon.run(
                goal=prompt,
                inputs={"url": url},
                generation_fn=gen_fn,
            )
            return result.get("output") or ""
        except Exception as e:
            logger.warning(f"Indra: Mnemon run failed, calling LLM directly: {e}")
            try:
                return str(generation_fn(prompt))
            except Exception as e2:
                logger.error(f"Indra: generation_fn failed: {e2}")
                return ""


# ── global convenience ────────────────────────────────────────────────────────

_instance: Optional[Indra] = None


def init(
    brightdata_api_key: Optional[str] = None,
    db_path: str = "indra.db",
    unlocker_zone: Optional[str] = None,
    serp_zone: Optional[str] = None,
    silent: bool = False,
    **kwargs,
) -> Indra:
    """
    One-line setup.

        agent = indra.init(brightdata_api_key="...")
        result = agent.watch("https://competitor.com/pricing", question="...")
    """
    global _instance
    if _instance is not None:
        return _instance
    _instance = Indra(
        brightdata_api_key=brightdata_api_key,
        db_path=db_path,
        unlocker_zone=unlocker_zone,
        serp_zone=serp_zone,
        silent=silent,
        **kwargs,
    )
    return _instance


def get() -> Indra:
    if _instance is None:
        raise RuntimeError("indra.get() called before indra.init(). Call indra.init() first.")
    return _instance


__all__ = ["Indra", "WatchResult", "init", "get"]
