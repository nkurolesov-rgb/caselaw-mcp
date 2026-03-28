"""Adapter for Korean legislation via law.go.kr search pages."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import AdapterError, BaseAdapter


class KRLegAdapter(BaseAdapter):
    """Korean statute adapter using 국가법령정보센터 HTML search results."""

    SEARCH_URL = "https://www.law.go.kr/lsSc.do"

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _extract_article(text: str) -> str | None:
        match = re.search(r"(제\s*\d+\s*조)", text)
        if match:
            return re.sub(r"\s+", "", match.group(1))
        return None

    def search_statutes(self, query: str, limit: int = 10, **kwargs: Any) -> list[dict[str, Any]]:
        q = query.strip()
        if not q:
            raise AdapterError("Empty query")

        cache_key = f"krleg:{q}:{limit}"

        def _fetch() -> list[dict[str, Any]]:
            html = self._request_text(
                "GET",
                self.SEARCH_URL,
                params={"query": q, "menuId": "1", "subMenuId": "15"},
                headers={"User-Agent": "legal-mcp/1.0"},
            )
            soup = BeautifulSoup(html, "lxml")

            rows: list[dict[str, Any]] = []
            seen: set[str] = set()
            for anchor in soup.select("a[href]"):
                href = anchor.get("href", "").strip()
                if not href or ("lsInfoP.do" not in href and "법령" not in href):
                    continue

                law_name = self._clean(anchor.get_text(" ", strip=True))
                if not law_name:
                    continue

                parent = anchor.find_parent(["li", "tr", "div"])
                context = self._clean(parent.get_text(" ", strip=True) if parent else law_name)
                source_url = urljoin("https://www.law.go.kr", href)
                if source_url in seen:
                    continue
                seen.add(source_url)

                rows.append(
                    {
                        "law_name": law_name,
                        "jurisdiction": "KR",
                        "article": self._extract_article(context),
                        "text": context,
                        "source_url": source_url,
                        "_source": "krleg",
                    }
                )
                if len(rows) >= limit:
                    break
            return rows

        return self._run_with_cache(cache_key, _fetch)
