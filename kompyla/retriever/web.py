"""Web search via Tavily — returns docs with content already extracted."""

from __future__ import annotations

import httpx

from .base import FetchedDoc, SourceConnector

_TAVILY_ENDPOINT = "https://api.tavily.com/search"


class WebSearchConnector(SourceConnector):
    """Web search via Tavily. Requires TAVILY_API_KEY (or api_key arg)."""

    name = "web"

    def __init__(self, api_key: str | None = None, search_depth: str = "basic"):
        self.api_key = api_key
        self.search_depth = search_depth   # "basic" or "advanced"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> list[FetchedDoc]:
        if not self.is_available():
            return []
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": self.search_depth,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": True,
        }
        try:
            resp = httpx.post(_TAVILY_ENDPOINT, json=payload, timeout=30.0)
            resp.raise_for_status()
        except httpx.HTTPError:
            return []

        results = resp.json().get("results", []) or []
        docs: list[FetchedDoc] = []
        for r in results:
            content = r.get("raw_content") or r.get("content") or ""
            if not content.strip():
                continue
            docs.append(
                FetchedDoc(
                    title=r.get("title") or r.get("url", ""),
                    url=r.get("url", ""),
                    content=content,
                    source_type=self.name,
                    metadata={
                        "score": r.get("score"),
                        "published_date": r.get("published_date"),
                    },
                )
            )
        return docs
