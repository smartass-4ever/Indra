"""
Bright Data client for Indra.

Supports Web Unlocker (fetch any URL, bypasses bot detection) and SERP API.
Falls back to direct requests when no zone is configured — useful for local
development and demos before a Bright Data zone is set up.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

BRIGHTDATA_API_BASE   = "https://api.brightdata.com"
DEFAULT_FETCH_TIMEOUT = 30
DEFAULT_SERP_TIMEOUT  = 20


class BrightDataError(Exception):
    pass


class BrightDataClient:
    """
    Fetches live web content via Bright Data Web Unlocker and SERP API.

    If no zone is configured (account not yet set up), falls back to
    direct requests so development and demos work without friction.
    Bright Data is the production path — bypasses bot detection,
    CAPTCHAs, geo-blocks on any public website.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        unlocker_zone: Optional[str] = None,
        serp_zone: Optional[str] = None,
    ):
        self.api_key      = api_key or os.environ.get("BRIGHTDATA_API_KEY", "")
        self.unlocker_zone = unlocker_zone or os.environ.get("BRIGHTDATA_UNLOCKER_ZONE", "")
        self.serp_zone     = serp_zone     or os.environ.get("BRIGHTDATA_SERP_ZONE", "")

        # Bright Data is active when we have a key AND a zone
        self._bd_active = bool(self.api_key and self.unlocker_zone)

        self._session = requests.Session()
        if self.api_key:
            self._session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type":  "application/json",
            })
        self._session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

        self.total_fetches  = 0
        self.total_searches = 0
        self._fallback_count = 0

        if not self._bd_active:
            logger.info(
                "Bright Data zone not configured — using direct requests as fallback. "
                "Set BRIGHTDATA_UNLOCKER_ZONE to enable production mode."
            )

    @property
    def using_brightdata(self) -> bool:
        return self._bd_active

    def fetch(self, url: str, render_js: bool = False) -> str:
        """
        Fetch a URL. Uses Bright Data Web Unlocker when a zone is configured,
        otherwise falls back to direct requests.
        """
        self.total_fetches += 1

        if self._bd_active:
            return self._fetch_brightdata(url, render_js)
        return self._fetch_direct(url)

    def search(self, query: str, num_results: int = 10) -> List[Dict]:
        """
        Fetch live SERP results. Uses Bright Data SERP API when a zone is
        configured, otherwise falls back to scraping a search results page.
        """
        self.total_searches += 1

        if self._bd_active and self.serp_zone:
            return self._search_brightdata(query, num_results)
        return self._search_direct(query, num_results)

    def _fetch_brightdata(self, url: str, render_js: bool) -> str:
        payload: Dict[str, Any] = {"url": url, "zone": self.unlocker_zone}
        if render_js:
            payload["render_js"] = True
        try:
            resp = self._session.post(
                f"{BRIGHTDATA_API_BASE}/request",
                json=payload,
                timeout=DEFAULT_FETCH_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.text
        except requests.HTTPError as e:
            raise BrightDataError(f"Bright Data fetch failed [{resp.status_code}]: {url}") from e
        except requests.RequestException as e:
            raise BrightDataError(f"Bright Data fetch error: {url} — {e}") from e

    def _fetch_direct(self, url: str) -> str:
        try:
            resp = self._session.get(url, timeout=DEFAULT_FETCH_TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            self._fallback_count += 1
            return resp.text
        except requests.RequestException as e:
            raise BrightDataError(f"Direct fetch failed: {url} — {e}") from e

    def _search_brightdata(self, query: str, num_results: int) -> List[Dict]:
        try:
            resp = self._session.get(
                f"{BRIGHTDATA_API_BASE}/serp/google/search",
                params={"q": query, "zone": self.serp_zone, "num": num_results},
                timeout=DEFAULT_SERP_TIMEOUT,
            )
            resp.raise_for_status()
            data    = resp.json()
            organic = data.get("organic", data.get("results", []))
            return [
                {
                    "title":   r.get("title", ""),
                    "url":     r.get("link", r.get("url", "")),
                    "snippet": r.get("snippet", r.get("description", "")),
                }
                for r in organic[:num_results]
            ]
        except requests.RequestException as e:
            raise BrightDataError(f"Bright Data search failed: {query!r} — {e}") from e

    def _search_direct(self, query: str, num_results: int) -> List[Dict]:
        # Fallback: fetch DuckDuckGo HTML and return the URL as a single result.
        # Not structured — but keeps the demo running without a SERP zone.
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        try:
            resp = self._session.get(url, timeout=DEFAULT_SERP_TIMEOUT)
            self._fallback_count += 1
            return [{"title": query, "url": url, "snippet": resp.text[:500]}]
        except requests.RequestException as e:
            raise BrightDataError(f"Direct search failed: {query!r} — {e}") from e

    def get_stats(self) -> Dict:
        return {
            "total_fetches":   self.total_fetches,
            "total_searches":  self.total_searches,
            "brightdata_mode": self._bd_active,
            "fallback_count":  self._fallback_count,
        }
