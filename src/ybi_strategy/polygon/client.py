from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Any

import requests

from ybi_strategy.polygon.http_cache import HttpCache


class PolygonError(RuntimeError):
    pass


@dataclass(frozen=True)
class PolygonClient:
    api_key: str
    base_url: str = "https://api.polygon.io"
    timeout_s: int = 30
    cache: HttpCache | None = None

    @staticmethod
    def from_env() -> "PolygonClient":
        api_key = os.environ.get("POLYGON_API_KEY", "").strip()
        if not api_key:
            raise PolygonError("Missing POLYGON_API_KEY environment variable.")
        cache_dir = os.environ.get("YBI_HTTP_CACHE_DIR", "").strip()
        cache = HttpCache.from_dir(cache_dir) if cache_dir else None
        return PolygonClient(api_key=api_key, cache=cache)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        p = dict(params or {})
        p["apiKey"] = self.api_key

        if self.cache is not None:
            cached = self.cache.get(url=url, params={k: v for k, v in p.items() if k != "apiKey"})
            if cached is not None:
                return cached

        resp = requests.get(url, params=p, timeout=self.timeout_s)
        if resp.status_code != 200:
            raise PolygonError(f"Polygon error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        if isinstance(data, dict) and data.get("status") in {"ERROR"}:
            raise PolygonError(f"Polygon ERROR: {data}")
        if not isinstance(data, dict):
            raise PolygonError(f"Unexpected response: {type(data)}")

        if self.cache is not None:
            self.cache.put(url=url, params={k: v for k, v in p.items() if k != "apiKey"}, value=data)

        return data

    def grouped_daily(self, d: date) -> list[dict[str, Any]]:
        data = self._get(f"/v2/aggs/grouped/locale/us/market/stocks/{d.isoformat()}", params={"adjusted": "true"})
        results = data.get("results", [])
        if not isinstance(results, list):
            raise PolygonError("Unexpected grouped_daily results shape.")
        return results

    def minute_bars(self, ticker: str, d: date) -> list[dict[str, Any]]:
        # Returns 1-minute aggregates for the requested date. Polygon's behavior regarding
        # extended hours varies by entitlement and endpoint semantics; we treat whatever is returned
        # as authoritative and then filter timestamps in the strategy layer.
        path = f"/v2/aggs/ticker/{ticker}/range/1/minute/{d.isoformat()}/{d.isoformat()}"
        data = self._get(path, params={"adjusted": "true", "sort": "asc", "limit": 50000})
        results = data.get("results", [])
        if not isinstance(results, list):
            raise PolygonError("Unexpected minute_bars results shape.")
        return results

    def daily_bar(self, ticker: str, d: date) -> dict[str, Any] | None:
        """Fetch single day's OHLCV for a ticker. Returns None if no data."""
        path = f"/v2/aggs/ticker/{ticker}/range/1/day/{d.isoformat()}/{d.isoformat()}"
        data = self._get(path, params={"adjusted": "true"})
        results = data.get("results", [])
        if not isinstance(results, list) or not results:
            return None
        return results[0]

    def ticker_details(self, ticker: str) -> dict[str, Any] | None:
        """
        Fetch ticker reference data for asset type classification.

        Returns dict with fields like:
        - type: "CS" (common stock), "ETF", "WARRANT", etc.
        - market: "stocks", "otc", etc.
        - active: True/False
        """
        try:
            path = f"/v3/reference/tickers/{ticker}"
            data = self._get(path)
            return data.get("results", None)
        except PolygonError:
            return None
