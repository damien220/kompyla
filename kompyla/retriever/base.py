from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class FetchedDoc:
    """One document discovered by a source connector."""

    title: str
    url: str
    content: str                                  # Cleaned markdown/text body
    source_type: str                              # "web", "arxiv", "github", "rss", "youtube"
    metadata: dict = field(default_factory=dict)  # Source-specific extras (authors, stars, ...)
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    relevance_score: float | None = None          # Filled in by the relevance filter


class SourceConnector(ABC):
    """Pluggable interface every retrieval source implements.

    A connector may support search, single-URL fetch, both, or neither —
    return an empty list / None for unsupported operations.
    """

    name: str = "base"

    def search(self, query: str, max_results: int = 10) -> list[FetchedDoc]:
        """Run a query against this source. Default: not supported."""
        return []

    def fetch_url(self, url: str) -> FetchedDoc | None:
        """Fetch a single URL through this connector. Default: not supported."""
        return None

    def is_available(self) -> bool:
        """Override to advertise readiness (e.g. API key present)."""
        return True
