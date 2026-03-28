"""Adapter for WIPO copyright treaties (WCT, WPPT, Beijing Treaty, Marrakesh)."""
from __future__ import annotations

from typing import Any

from .base import BaseAdapter


class WIPOCopyrightTreatiesAdapter(BaseAdapter):
    """WIPO copyright treaties adapter.

    Queries WIPO for information on copyright and related rights treaties
    including WCT, WPPT, Beijing Treaty on Audiovisual Performances,
    and the Marrakesh Treaty.
    """

    BASE_URL = "https://www.wipo.int/treaties/en"

    def search_disputes(
        self,
        query: str = "",
        jurisdiction: str = "GLOBAL",
        year_from: int | None = None,
        limit: int = 10,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        cache_key = f"wipo_copyright_treaties:{query}:{jurisdiction}:{year_from}:{limit}"

        def _fetch() -> list[dict[str, Any]]:
            html = self._request_text(
                "GET",
                f"{self.BASE_URL}/ShowResults.jsp",
                params={"treaty_id": "16"},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            return [
                {
                    "source": "wipo_copyright_treaties",
                    "query": query,
                    "jurisdiction": "GLOBAL",
                    "indicator": "copyright_treaty_status",
                    "note": "WIPO-administered copyright treaties (WCT/WPPT/Beijing/Marrakesh)",
                    "source_url": self.BASE_URL,
                }
            ]

        return self._run_with_cache(cache_key, _fetch)
