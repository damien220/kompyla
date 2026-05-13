"""Web search connector with multiple backend providers.

Priority (first key present wins):
  1. Serper      — SERPER_API_KEY
  2. Brave       — BRAVE_API_KEY
  3. Exa         — EXA_API_KEY
  4. SerpAPI     — SERPAPI_API_KEY
  5. DuckDuckGo  — no key required (always available fallback)

Snippet-only backends (Serper, Brave, SerpAPI, DuckDuckGo) try to enrich each
result with full page content via trafilatura; on failure the snippet is kept.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from .base import FetchedDoc, SourceConnector
from .extractor import extract_url


# ---------------------------------------------------------------------------
# Internal backend interface
# ---------------------------------------------------------------------------

class _SearchBackend(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int) -> list[FetchedDoc]:
        ...


def _enrich(doc: FetchedDoc) -> FetchedDoc:
    """Replace snippet content with full page text when extractable."""
    if not doc.url:
        return doc
    full = extract_url(doc.url)
    if full and len(full) > len(doc.content):
        doc.content = full
    return doc


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

class _SerperBackend(_SearchBackend):
    _ENDPOINT = "https://google.serper.dev/search"

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def search(self, query: str, max_results: int) -> list[FetchedDoc]:
        try:
            resp = httpx.post(
                self._ENDPOINT,
                headers={"X-API-KEY": self._key, "Content-Type": "application/json"},
                json={"q": query, "num": max_results},
                timeout=30.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return []

        docs = []
        for r in resp.json().get("organic", []):
            content = r.get("snippet", "")
            if not content.strip():
                continue
            doc = FetchedDoc(
                title=r.get("title", r.get("link", "")),
                url=r.get("link", ""),
                content=content,
                source_type="web",
                metadata={"position": r.get("position")},
            )
            docs.append(_enrich(doc))
        return docs


class _BraveBackend(_SearchBackend):
    _ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def search(self, query: str, max_results: int) -> list[FetchedDoc]:
        try:
            resp = httpx.get(
                self._ENDPOINT,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self._key,
                },
                params={"q": query, "count": min(max_results, 20)},
                timeout=30.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return []

        docs = []
        for r in resp.json().get("web", {}).get("results", []):
            snippets = r.get("extra_snippets") or []
            content = "\n".join([r.get("description", "")] + snippets).strip()
            if not content:
                continue
            doc = FetchedDoc(
                title=r.get("title", r.get("url", "")),
                url=r.get("url", ""),
                content=content,
                source_type="web",
                metadata={"age": r.get("age")},
            )
            docs.append(_enrich(doc))
        return docs


class _ExaBackend(_SearchBackend):
    def __init__(self, api_key: str) -> None:
        try:
            from exa_py import Exa  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "exa-py is not installed. Run: pip install 'kompyla[search]'"
            ) from exc
        self._client = Exa(api_key)

    def search(self, query: str, max_results: int) -> list[FetchedDoc]:
        try:
            results = self._client.search_and_contents(
                query, num_results=max_results, text=True
            )
        except Exception:
            return []

        docs = []
        for r in results.results:
            content = getattr(r, "text", "") or ""
            if not content.strip():
                content = getattr(r, "highlights", [""])[0] if hasattr(r, "highlights") else ""
            if not content.strip():
                continue
            docs.append(
                FetchedDoc(
                    title=getattr(r, "title", "") or r.url,
                    url=r.url,
                    content=content,
                    source_type="web",
                    metadata={"score": getattr(r, "score", None)},
                )
            )
        return docs


class _SerpAPIBackend(_SearchBackend):
    def __init__(self, api_key: str) -> None:
        try:
            from serpapi import Client  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "serpapi is not installed. Run: pip install 'kompyla[search]'"
            ) from exc
        self._client = Client(api_key=api_key)

    def search(self, query: str, max_results: int) -> list[FetchedDoc]:
        try:
            results = self._client.search(
                {"engine": "google", "q": query, "num": max_results}
            )
            organic = results.get("organic_results") or []
        except Exception:
            return []

        docs = []
        for r in organic:
            content = r.get("snippet", "")
            if not content.strip():
                continue
            doc = FetchedDoc(
                title=r.get("title", r.get("link", "")),
                url=r.get("link", ""),
                content=content,
                source_type="web",
                metadata={"position": r.get("position")},
            )
            docs.append(_enrich(doc))
        return docs


class _DuckDuckGoBackend(_SearchBackend):
    def search(self, query: str, max_results: int) -> list[FetchedDoc]:
        try:
            from duckduckgo_search import DDGS  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "duckduckgo-search is not installed. Run: pip install duckduckgo-search"
            ) from exc

        try:
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=max_results))
        except Exception:
            return []

        docs = []
        for r in raw:
            content = r.get("body", "")
            if not content.strip():
                continue
            doc = FetchedDoc(
                title=r.get("title", r.get("href", "")),
                url=r.get("href", ""),
                content=content,
                source_type="web",
            )
            docs.append(_enrich(doc))
        return docs


# ---------------------------------------------------------------------------
# Public connector (backend is selected once at construction time)
# ---------------------------------------------------------------------------

class WebSearchConnector(SourceConnector):
    """Web search using the first configured API key, with DuckDuckGo fallback."""

    name = "web"

    def __init__(
        self,
        serper_api_key: str | None = None,
        brave_api_key: str | None = None,
        exa_api_key: str | None = None,
        serpapi_api_key: str | None = None,
    ) -> None:
        if serper_api_key:
            self._backend: _SearchBackend = _SerperBackend(serper_api_key)
            self._backend_name = "serper"
        elif brave_api_key:
            self._backend = _BraveBackend(brave_api_key)
            self._backend_name = "brave"
        elif exa_api_key:
            self._backend = _ExaBackend(exa_api_key)
            self._backend_name = "exa"
        elif serpapi_api_key:
            self._backend = _SerpAPIBackend(serpapi_api_key)
            self._backend_name = "serpapi"
        else:
            self._backend = _DuckDuckGoBackend()
            self._backend_name = "duckduckgo"

    def is_available(self) -> bool:
        return True  # DuckDuckGo is always available

    @property
    def backend_name(self) -> str:
        return self._backend_name

    def search(self, query: str, max_results: int = 10) -> list[FetchedDoc]:
        return self._backend.search(query, max_results)
