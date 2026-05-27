"""
Bright Data client for Indra.

Supports Web Unlocker (fetch any URL, bypasses bot detection) and SERP API.
Every call goes live through Bright Data — no stale data, no geo-blocks.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

BRIGHTDATA_API_BASE = "https://api.brightdata.com"
DEFAULT_FETCH_TIMEOUT = 30
DEFAULT_SERP_TIMEOUT  = 20


class BrightDataError(Exception):
    pass


class BrightDataClient:
    """
    Thin wrapper around Bright Data's API.

    Usage:
        client = BrightDataClient(api_key="your-key")
        html   = client.fetch("https://example.com/pricing")
        results = client.search("openai pricing 2026")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        unlocker_zone: str = "web_unlocker1",
        serp_zone: str = "serp_api1",
    ):
        self.api_key = api_key or os.environ.get("BRIGHTDATA_API_KEY", "")
        if not self.api_key:
            raise BrightDataError(
                "Bright Data API key required. "
                "Pass api_key= or set BRIGHTDATA_API_KEY env var."
            )
        self.unlocker_zone = unlocker_zone
        self.serp_zone     = serp_zone

        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        })

        # Stats
        self.total_fetches  = 0
        self.total_searches = 0

    def fetch(self, url: str, render_js: bool = False) -> str:
        """
        Fetch a URL through Bright Data Web Unlocker.
        Bypasses bot detection, CAPTCHAs, geo-blocks automatically.
        Returns HTML as a string.
        """
        payload: Dict[str, Any] = {"url": url, "zone": self.unlocker_zone}
        if render_js:
            payload["render_js"] = True

        logger.debug(f"BrightData fetch: {url}")
        try:
            resp = self._session.post(
                f"{BRIGHTDATA_API_BASE}/request",
                json=payload,
                timeout=DEFAULT_FETCH_TIMEOUT,
            )
            resp.raise_for_status()
            self.total_fetches += 1
            return resp.text
        except requests.HTTPError as e:
            raise BrightDataError(f"Fetch failed [{resp.status_code}]: {url} — {e}") from e
        except requests.RequestException as e:
            raise BrightDataError(f"Fetch error: {url} — {e}") from e

    def search(self, query: str, num_results: int = 10) -> List[Dict]:
        """
        Fetch live SERP results for a query via Bright Data SERP API.
        Returns a list of {title, url, snippet} dicts.
        """
        logger.debug(f"BrightData search: {query!r}")
        try:
            resp = self._session.get(
                f"{BRIGHTDATA_API_BASE}/serp/google/search",
                params={"q": query, "zone": self.serp_zone, "num": num_results},
                timeout=DEFAULT_SERP_TIMEOUT,
            )
            resp.raise_for_status()
            self.total_searches += 1
            data = resp.json()
            organic = data.get("organic", data.get("results", []))
            return [
                {
                    "title":   r.get("title", ""),
                    "url":     r.get("link", r.get("url", "")),
                    "snippet": r.get("snippet", r.get("description", "")),
                }
                for r in organic[:num_results]
            ]
        except requests.HTTPError as e:
            raise BrightDataError(f"Search failed [{resp.status_code}]: {query!r} — {e}") from e
        except requests.RequestException as e:
            raise BrightDataError(f"Search error: {query!r} — {e}") from e

    def get_stats(self) -> Dict:
        return {
            "total_fetches":  self.total_fetches,
            "total_searches": self.total_searches,
        }
