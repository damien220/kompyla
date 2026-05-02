"""GitHub repository search — returns READMEs as markdown."""

from __future__ import annotations

import base64

import httpx

from .base import FetchedDoc, SourceConnector

_API_ROOT = "https://api.github.com"


class GitHubConnector(SourceConnector):
    """Search GitHub repos. Anonymous works (low rate limit); token raises it."""

    name = "github"

    def __init__(self, token: str | None = None, fetch_readme: bool = True):
        self.token = token
        self.fetch_readme = fetch_readme

    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github+json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def search(self, query: str, max_results: int = 10) -> list[FetchedDoc]:
        try:
            resp = httpx.get(
                f"{_API_ROOT}/search/repositories",
                params={"q": query, "per_page": max_results, "sort": "stars"},
                headers=self._headers(),
                timeout=30.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            return []

        items = resp.json().get("items", []) or []
        docs: list[FetchedDoc] = []
        for item in items:
            full_name = item.get("full_name", "")
            description = item.get("description") or ""
            stars = item.get("stargazers_count", 0)
            url = item.get("html_url", "")

            content_parts = [
                f"# {full_name}",
                "",
                f"**URL:** {url}",
                f"**Stars:** {stars}",
                f"**Language:** {item.get('language') or 'unknown'}",
                "",
                f"## Description\n\n{description}",
            ]

            if self.fetch_readme:
                readme = self._fetch_readme(full_name)
                if readme:
                    content_parts.extend(["", "## README", "", readme])

            docs.append(
                FetchedDoc(
                    title=full_name,
                    url=url,
                    content="\n".join(content_parts),
                    source_type=self.name,
                    metadata={
                        "stars": stars,
                        "language": item.get("language"),
                        "topics": item.get("topics", []),
                    },
                )
            )
        return docs

    def _fetch_readme(self, full_name: str) -> str | None:
        try:
            resp = httpx.get(
                f"{_API_ROOT}/repos/{full_name}/readme",
                headers=self._headers(),
                timeout=20.0,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if data.get("encoding") == "base64":
                try:
                    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                except Exception:
                    return None
            return data.get("content")
        except httpx.HTTPError:
            return None
