"""Adapter for EUR-Lex legislation search.

Fetches EU legislation via the EUR-Lex HTML search interface.
The initial request returns HTTP 302 with a ``qid`` parameter;
``_request_text()`` (urllib) follows the redirect automatically and
returns the full search-results HTML page (~200 KB).

Each search result lives inside a ``<div class="SearchResult">`` block
containing a title ``<a>`` with a CELEX document reference in the href.
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any

from .base import AdapterError, BaseAdapter

# CELEX number format: <sector-digit><4-digit-year><type-letter><sequence>
# e.g.  32001L0029  ->  sector=3, year=2001, type=L (directive), seq=0029
_CELEX_RE = re.compile(r"(\d)(\d{4})([A-Z])(\d+)")


class EurLexAdapter(BaseAdapter):
    """Fetch EU legislation data via EUR-Lex HTML search."""

    SEARCH_URL = "https://eur-lex.europa.eu/search.html"
    BASE_URL = "https://eur-lex.europa.eu"

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _clean(text: str) -> str:
        """Strip HTML tags and collapse whitespace."""
        plain = re.sub(r"<[^>]+>", " ", text)
        plain = unescape(plain)
        return re.sub(r"\s+", " ", plain).strip()

    @staticmethod
    def _extract_year(celex: str) -> int | None:
        """Extract the 4-digit year from a CELEX number.

        CELEX format: ``<sector><YYYY><type><seq>``
        e.g. ``32001L0029`` -> 2001
        """
        m = _CELEX_RE.match(celex)
        if m:
            return int(m.group(2))
        return None

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #

    def search_statutes(
        self,
        query: str,
        article: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search EUR-Lex legislation (consistent interface for statute tools)."""
        rows = self.search_legislation(query, limit=limit * 2 if article else limit)
        if article:
            article_q = article.strip().lower()
            rows = [
                row
                for row in rows
                if article_q in str(row.get("title", "")).lower()
                or article_q in str(row.get("work", "")).lower()
            ]
        return rows[:limit]

    def search_legislation(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search EUR-Lex and return structured legislation results.

        The search URL ``https://eur-lex.europa.eu/search.html?scope=EURLEX&text=<query>&type=quick``
        returns a 302 redirect to a URL with ``qid=...``; urllib follows
        this automatically.
        """
        q = query.strip()
        if not q:
            raise AdapterError("Empty query")
        cache_key = f"eurlex:search:{q.lower()}:{limit}"

        def _fetch() -> list[dict[str, Any]]:
            html = self._request_text(
                "GET",
                self.SEARCH_URL,
                params={"scope": "EURLEX", "text": q, "type": "quick"},
                headers={
                    "User-Agent": "legal-mcp/1.0",
                    "Accept": "text/html",
                    "Accept-Language": "en",
                },
            )

            rows = self._parse_search_results(html, limit)

            # Fetch full text for first few results
            for row in rows[:3]:
                celex = row.get("work", "").replace("CELEX:", "")
                if not celex:
                    continue
                try:
                    txt_url = f"{self.BASE_URL}/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}"
                    txt_html = self._request_text(
                        "GET", txt_url, headers={"User-Agent": "legal-mcp/1.0"},
                    )
                    text = self._clean(txt_html)
                    if len(text) > 5000:
                        text = text[:5000] + "..."
                    row["text"] = text
                except Exception:
                    row["text"] = ""

            return rows

        return self._run_with_cache(cache_key, _fetch)

    def get_document(self, celex: str) -> dict[str, Any] | None:
        """Fetch a specific EUR-Lex document by CELEX number."""
        celex = celex.strip()
        if not celex:
            return None
        # Remove "CELEX:" prefix if present
        if celex.startswith("CELEX:"):
            celex = celex[6:]
        cache_key = f"eurlex:doc:{celex}"

        def _fetch() -> dict[str, Any] | None:
            url = f"{self.BASE_URL}/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}"
            try:
                html = self._request_text(
                    "GET", url, headers={"User-Agent": "legal-mcp/1.0"}
                )
                text = self._clean(html)
                if len(text) > 10000:
                    text = text[:10000] + "..."
                return {
                    "law_name": f"CELEX:{celex}",
                    "jurisdiction": "EU",
                    "article": None,
                    "text": text,
                    "source_url": url,
                    "theme": "eurlex_document",
                }
            except Exception:
                return None

        return self._run_with_cache(cache_key, _fetch)

    # ------------------------------------------------------------------ #
    # HTML parsing
    # ------------------------------------------------------------------ #

    def _parse_search_results(
        self, html: str, limit: int
    ) -> list[dict[str, Any]]:
        """Parse the EUR-Lex search results page.

        Each result block is a ``<div class="SearchResult">`` containing:
        - ``<a class="title" href="./legal-content/AUTO/?uri=CELEX:XXXXX...">Title</a>``
        - ``<p class="textUnderTitle ..."><i>OJ L NNN, DD.MM.YYYY, ...</i></p>``
        - ``<div class="DocStatus">...<p class="forceIndicator">...In force...</p></div>``
        """
        # Split HTML at each SearchResult div boundary
        # Each block starts with class="SearchResult"> and ends before the next one
        blocks = re.split(r'<div[^>]*class="SearchResult"[^>]*>', html)

        if len(blocks) <= 1:
            raise AdapterError(
                "No EUR-Lex search results found in HTML response"
            )

        rows: list[dict[str, Any]] = []
        seen_celex: set[str] = set()

        # blocks[0] is the preamble before the first result; skip it
        for block in blocks[1:]:
            result = self._parse_single_result(block)
            if result is None:
                continue

            celex = result["work"].replace("CELEX:", "")
            if celex in seen_celex:
                continue
            seen_celex.add(celex)

            rows.append(result)
            if len(rows) >= limit:
                break

        if not rows:
            raise AdapterError("No EUR-Lex results parsed from HTML")
        return rows

    def _parse_single_result(self, block: str) -> dict[str, Any] | None:
        """Parse a single SearchResult block and return a result dict or None."""
        # Find the title link: <a ... href="...CELEX:<celex>..." class="title" ...>Title</a>
        # The href may use relative path: ./legal-content/AUTO/?uri=CELEX:32001L0029
        title_match = re.search(
            r'<a[^>]+href="[^"]*CELEX:(\d+[A-Z]\d+)[^"]*"[^>]*class="title"[^>]*>(.*?)</a>',
            block,
            re.DOTALL | re.IGNORECASE,
        )
        if not title_match:
            # Also try: class="title" before href (attribute order varies)
            title_match = re.search(
                r'<a[^>]+class="title"[^>]+href="[^"]*CELEX:(\d+[A-Z]\d+)[^"]*"[^>]*>(.*?)</a>',
                block,
                re.DOTALL | re.IGNORECASE,
            )
        if not title_match:
            return None

        celex = title_match.group(1)
        title = self._clean(title_match.group(2))

        # Filter out non-informative titles
        if not title or len(title) < 10:
            return None
        if re.match(r"^\d{2}/\d{2}/\d{4}$", title):
            return None
        if title.strip().lower() in ("pdf", "html"):
            return None

        # Skip consolidated-text CELEX (starts with 0) -- prefer the base act
        if celex.startswith("0"):
            return None

        # Extract year from CELEX
        year = self._extract_year(celex)

        # Extract OJ reference from textUnderTitle
        # Class attribute has textUnderTitle in the middle:
        #   class="hidden-xs hidden-sm textUnderTitle showInPdf"
        oj_ref = None
        oj_match = re.search(
            r'class="[^"]*textUnderTitle[^"]*showInPdf[^"]*"[^>]*>\s*<i>(.*?)</i>',
            block,
            re.DOTALL,
        )
        if oj_match:
            oj_text = self._clean(oj_match.group(1))
            # Extract just the OJ part: "OJ L 167, 22.6.2001, pp. 10-19"
            oj_part = re.match(r"(OJ\s+[A-Z]\s+\d+,\s+[\d.]+,\s+pp?\.\s*[\d\s\u2013–-]+)", oj_text)
            if oj_part:
                oj_ref = oj_part.group(1).strip()

        # Extract legal status (In force / No longer in force)
        status = None
        status_match = re.search(
            r'class="forceIndicator"[^>]*>(.*?)</p>',
            block,
            re.DOTALL,
        )
        if status_match:
            status = self._clean(status_match.group(1))

        source_url = f"{self.BASE_URL}/legal-content/EN/TXT/?uri=CELEX:{celex}"

        result: dict[str, Any] = {
            "title": title,
            "work": f"CELEX:{celex}",
            "date": str(year) if year else None,
            "jurisdiction": "EU",
            "source_url": source_url,
            "_source": "eurlex_html",
        }

        if oj_ref:
            result["oj_reference"] = oj_ref
        if status:
            result["status"] = status

        return result
