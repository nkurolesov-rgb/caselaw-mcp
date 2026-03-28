"""Adapter for Japanese court statistics page scraping."""
from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

from .base import AdapterError, BaseAdapter


class CourtStatsAdapter(BaseAdapter):
    """Court statistics adapter via courts.go.jp public pages."""

    STATS_URL = "https://www.courts.go.jp/toukei_siryou/siryo/index.html"

    def search_disputes(
        self,
        query: str = "",
        jurisdiction: str = "GLOBAL",
        year_from: int | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        cache_key = f"court_stats:{query}:{jurisdiction}:{year_from}:{limit}"

        def _fetch() -> list[dict[str, Any]]:
            try:
                html = self._request_text(
                    "GET",
                    self.STATS_URL,
                    headers={"User-Agent": "legal-mcp/1.0"},
                )
            except AdapterError as exc:
                raise AdapterError(
                    f"Failed to fetch Japan courts statistics page ({self.STATS_URL}); the site may be unavailable or blocking automated access"
                ) from exc

            lower_html = html.lower()
            if any(token in lower_html for token in ("captcha", "cloudflare", "attention required", "access denied", "security check")):
                raise AdapterError(
                    f"Japan courts statistics page returned an anti-bot challenge at {self.STATS_URL}; cannot parse resources"
                )

            q_norm = query.strip().lower()
            rows: list[dict[str, Any]] = []

            for match in re.finditer(
                r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                html,
                flags=re.IGNORECASE | re.DOTALL,
            ):
                href, inner = match.groups()
                text = unescape(re.sub(r"<[^>]+>", " ", inner))
                text = re.sub(r"\s+", " ", text).strip()
                if not text:
                    continue
                if q_norm and q_norm not in text.lower():
                    continue
                if not any(token in text for token in ("統計", "知的財産", "工業所有権", "商標", "特許")) and not href.endswith(
                    (".pdf", ".xls", ".xlsx", ".html")
                ):
                    continue

                context = html[max(0, match.start() - 200) : min(len(html), match.end() + 200)]
                year_match = re.search(r"\b(19|20)\d{2}\b", context)
                year = int(year_match.group(0)) if year_match else None
                if year_from and year and year < year_from:
                    continue

                rows.append(
                    {
                        "indicator": "court_statistics_document",
                        "jurisdiction": jurisdiction.upper(),
                        "year": year,
                        "value": 1.0,
                        "unit": "document",
                        "source": "court_stats",
                        "note": f"{text} | {urljoin(self.STATS_URL, href)}",
                    }
                )
                if len(rows) >= limit:
                    break

            if not rows:
                raise AdapterError("No court statistics documents found")
            return rows

        return self._run_with_cache(cache_key, _fetch)
