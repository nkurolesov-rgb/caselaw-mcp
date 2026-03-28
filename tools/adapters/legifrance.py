"""Adapter for France legal search via Légifrance API via external API.

OPERATIONAL NOTE:
- This adapter integrates with PISTE API (https://piste.gouv.fr/) for Légifrance access
- Requires OAuth2 client credentials: LEGIFRANCE_CLIENT_ID and LEGIFRANCE_CLIENT_SECRET
- Supports both statute search (LEGI) and case law search (CASS, JADE, CETAT)
- API documentation: https://piste.gouv.fr/en/ (requires registration)
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .base import AdapterError, BaseAdapter

class LegifranceAdapter(BaseAdapter):
    """FR statute/case law adapter via Légifrance PISTE API via external API.

    Supported collections (fonds):
    - LEGI: Code statutes (Code civil, Code de la propriété intellectuelle, etc.)
    - CASS: Cour de Cassation (Supreme Court) decisions
    - JADE: Administrative law database
    - CETAT: Conseil d'État (Council of State) decisions
    - CAPP: Court of Appeal decisions
    """

    TOKEN_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
    SEARCH_URL = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app/search"
    CONSULT_ARTICLE_URL = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app/consult/getArticle"

    def __init__(self, client_id: str = "", client_secret: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.client_id = client_id or os.getenv("LEGIFRANCE_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("LEGIFRANCE_CLIENT_SECRET", "")
        self._token: str | None = None

    def _get_token(self) -> str | None:
        """Obtain OAuth2 access token from PISTE API.

        Returns:
            Access token string if successful, None if credentials not configured or request fails.
        """
        if not self.client_id or not self.client_secret:
            return None

        # Cache token if already obtained
        if self._token:
            return self._token

        body = (
            f"grant_type=client_credentials&client_id={self.client_id}"
            f"&client_secret={self.client_secret}&scope=openid"
        )
        try:
            payload = self._request_json(
                "POST",
                self.TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                body=body,
            )
            self._token = payload.get("access_token")
            return self._token
        except Exception:
            return None

    def get_article_detail(self, article_id: str) -> dict[str, Any] | None:
        """Retrieve full article text by LEGIARTI identifier.

        Args:
            article_id: LEGIARTI identifier (e.g., "LEGIARTI000006418367")

        Returns:
            Article metadata and text if successful, None if failed.
        """
        token = self._get_token()
        if not token:
            return None

        headers = {
            "Authorization": f"Bearer {token}",
            "accept": "application/json",
            "Content-Type": "application/json",
        }
        body = json.dumps({"id": article_id})

        try:
            payload = self._request_json("POST", self.CONSULT_ARTICLE_URL, headers=headers, body=body)
            return payload
        except Exception:
            return None

    def search_statutes(
        self,
        query: str,
        fond: str = "LEGI",
        year_from: int | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search French statutes (Code civil, Code de la propriété intellectuelle, etc.).

        Args:
            query: Search text (e.g., "droit d'auteur")
            fond: Collection code (default: "LEGI" for statutes)
            year_from: Filter results from this year onwards
            limit: Maximum results to return

        Returns:
            List of statute results with metadata.
        """
        q = query.strip()
        cache_key = f"legifrance:statute:{fond}:{q.lower()}:{year_from}:{limit}"

        def _fetch() -> list[dict[str, Any]]:
            token = self._get_token()
            if not token:
                raise AdapterError("No Légifrance OAuth2 token - set LEGIFRANCE_CLIENT_ID and LEGIFRANCE_CLIENT_SECRET")

            headers = {
                "Authorization": f"Bearer {token}",
                "accept": "application/json",
                "Content-Type": "application/json",
            }
            body = json.dumps(
                {
                    "recherche": {
                        "champs": [{"typeChamp": "ALL", "criteres": [{"typeRecherche": "EXACTE", "valeur": q}]}],
                        "pageNumber": 1,
                        "pageSize": limit,
                        "sort": "PERTINENCE",
                        "typePagination": "ARTICLE",
                    },
                    "fond": fond,
                }
            )

            payload = self._request_json("POST", self.SEARCH_URL, headers=headers, body=body)
            items = payload.get("results", []) or payload.get("listResult", [])

            rows: list[dict[str, Any]] = []
            for item in items:
                title = item.get("titre") or item.get("title") or item.get("id") or ""
                date_str = item.get("dateTexte") or item.get("date") or ""
                year_match = re.search(r"\b(19|20)\d{2}\b", str(date_str))
                year = int(year_match.group(0)) if year_match else None
                if year_from is not None and isinstance(year, int) and year < year_from:
                    continue
                rows.append(
                    {
                        "case_name": title,
                        "jurisdiction": "FR",
                        "court": fond,
                        "year": year,
                        "result": "Unknown",
                        "summary": item.get("resume") or item.get("id") or "",
                        "domain": "external",
                        "keywords": [q.lower()],
                        "_source": "legifrance_api",
                        "_legiarti_id": item.get("id"),
                    }
                )

            if not rows:
                raise AdapterError("No Légifrance statute results")
            return rows

        return self._run_with_cache(cache_key, _fetch)

    def search_cases(
        self,
        query: str,
        year_from: int | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search French case law (Cour de Cassation, Conseil d'État, etc.).

        Args:
            query: Search text (e.g., "contrefaçon")
            court: Court collection code:
                - "CASS": Cour de Cassation (Supreme Court)
                - "CETAT": Conseil d'État (Council of State)
                - "JADE": Administrative law database
                - "CAPP": Court of Appeal
            year_from: Filter results from this year onwards
            limit: Maximum results to return

        Returns:
            List of case law results with metadata.
        """
        q = query.strip()
        court = "CASS"
        cache_key = f"legifrance:case:{court}:{q.lower()}:{year_from}:{limit}"

        def _fetch() -> list[dict[str, Any]]:
            token = self._get_token()
            if not token:
                raise AdapterError("No Légifrance OAuth2 token - set LEGIFRANCE_CLIENT_ID and LEGIFRANCE_CLIENT_SECRET")

            headers = {
                "Authorization": f"Bearer {token}",
                "accept": "application/json",
                "Content-Type": "application/json",
            }
            body = json.dumps(
                {
                    "recherche": {
                        "champs": [{"typeChamp": "ALL", "criteres": [{"typeRecherche": "EXACTE", "valeur": q}]}],
                        "pageNumber": 1,
                        "pageSize": limit,
                        "sort": "PERTINENCE",
                        "typePagination": "DOCUMENT",
                    },
                    "fond": court,
                }
            )

            payload = self._request_json("POST", self.SEARCH_URL, headers=headers, body=body)
            items = payload.get("results", []) or payload.get("listResult", [])

            rows: list[dict[str, Any]] = []
            for item in items:
                title = item.get("titre") or item.get("title") or item.get("id") or ""
                date_str = item.get("dateDecision") or item.get("dateTexte") or item.get("date") or ""
                year_match = re.search(r"\b(19|20)\d{2}\b", str(date_str))
                year = int(year_match.group(0)) if year_match else None
                if year_from is not None and isinstance(year, int) and year < year_from:
                    continue

                # Extract court chamber from metadata
                chamber = item.get("formation") or item.get("chamber") or ""

                rows.append(
                    {
                        "case_name": title,
                        "jurisdiction": "FR",
                        "court": f"{court} - {chamber}".strip(" - "),
                        "year": year,
                        "result": item.get("solution") or "Unknown",
                        "summary": item.get("resume") or item.get("sommaire") or item.get("id") or "",
                        "domain": "external",
                        "keywords": [q.lower()],
                        "_source": "legifrance_api",
                        "_document_id": item.get("id"),
                    }
                )

            if not rows:
                raise AdapterError("No Légifrance case law results")
            return rows

        return self._run_with_cache(cache_key, _fetch)
