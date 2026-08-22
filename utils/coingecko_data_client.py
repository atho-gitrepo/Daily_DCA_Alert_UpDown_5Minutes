"""CoinGecko market data client."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class CoinGeckoDataClient:
    """Simple client for public CoinGecko endpoints."""

    def __init__(self, base_url: Optional[str] = "https://api.coingecko.com/api/v3") -> None:
        self.base_url = base_url

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        query = ""
        if params:
            query = "?" + "&".join(f"{key}={value}" for key, value in params.items())
        url = f"{self.base_url}{path}{query}"
        request = Request(url, headers={"User-Agent": "daily-signal-alert"})
        try:
            with urlopen(request, timeout=10) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning("CoinGecko request failed for %s: %s", url, exc)
            return None

    def get_price(self, ids: str = "bitcoin", vs_currency: str = "usd") -> Optional[Dict[str, Any]]:
        return self._request("/simple/price", {"ids": ids, "vs_currencies": vs_currency})

    def get_market_data(self, ids: str = "bitcoin") -> Optional[List[Dict[str, Any]]]:
        data = self._request("/coins/markets", {"vs_currency": "usd", "ids": ids, "per_page": 50})
        if not isinstance(data, list):
            return None
        return data
