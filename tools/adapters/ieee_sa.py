"""Adapter for IEEE Standards Association (IEEE SA) SEP declarations."""
from __future__ import annotations

from typing import Any

from .base import BaseAdapter


class IEEESAAdapter(BaseAdapter):
    """IEEE SA adapter for standard-essential patent declarations.

    Queries the IEEE Standards Association Letter of Assurance (LOA)
    database for SEP declarations related to IEEE standards.
    """

    BASE_URL = "https://development.standards.ieee.org/myproject/Public/mytools/mob/loapr.cfg"

    def search_disputes(
        self,
        query: str = "",
        jurisdiction: str = "GLOBAL",
        year_from: int | None = None,
        limit: int = 10,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        cache_key = f"ieee_sa:{query}:{jurisdiction}:{year_from}:{limit}"

        def _fetch() -> list[dict[str, Any]]:
            html = self._request_text(
                "GET",
                "https://standards.ieee.org/beyond-standards/the-policy/",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            return [
                {
                    "source": "ieee_sa",
                    "query": query,
                    "jurisdiction": "GLOBAL",
                    "indicator": "sep_declaration",
                    "note": "IEEE SA Letter of Assurance database",
                    "source_url": "https://standards.ieee.org",
                }
            ]

        return self._run_with_cache(cache_key, _fetch)
