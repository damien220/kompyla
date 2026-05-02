"""URL → clean markdown via trafilatura."""

from __future__ import annotations

import httpx
import trafilatura


def extract_url(url: str, timeout: float = 20.0) -> str | None:
    """Fetch a URL and return its main content as markdown.

    Returns None if fetch or extraction fails.
    """
    try:
        response = httpx.get(
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Kompyla/0.1 (+https://github.com/kompyla)"},
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    extracted = trafilatura.extract(
        response.text,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    )
    return extracted or None


def extract_html(html: str, url: str | None = None) -> str | None:
    """Extract main content from already-fetched HTML."""
    return trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
    ) or None
