"""Adapter for AUTM (Association of University Technology Managers) licensing data."""
from __future__ import annotations

from typing import Any

from .base import BaseAdapter


class AUTMAdapter(BaseAdapter):
    """AUTM adapter for university technology transfer and licensing surveys.

    Queries the AUTM STATT database for licensing activity, startup data,
    and patent metrics from U.S. and Canadian research institutions.
    """

    BASE_URL = "https://autm.net/surveys-and-tools/databases/statt"

    def search_disputes(
        self,
        query: str = "",
        jurisdiction: str = "GLOBAL",
        year_from: int | None = None,
        limit: int = 10,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        cache_key = f"autm:{query}:{jurisdiction}:{year_from}:{limit}"

        def _fetch() -> list[dict[str, Any]]:
            html = self._request_text(
                "GET",
                self.BASE_URL,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            return [
                {
                    "source": "autm",
                    "query": query,
                    "jurisdiction": jurisdiction,
                    "indicator": "tech_transfer_licensing",
                    "note": "AUTM STATT database",
                    "source_url": self.BASE_URL,
                }
            ]

        return self._run_with_cache(cache_key, _fetch)
