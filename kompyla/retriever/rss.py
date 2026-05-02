"""RSS / Atom feed connector — pulls recent entries from configured feeds."""

from __future__ import annotations

import feedparser

from .base import FetchedDoc, SourceConnector
from .extractor import extract_url


class RSSConnector(SourceConnector):
    """Pull entries from configured RSS feeds.

    The query argument is treated as a substring filter against entry titles
    and summaries (case-insensitive). Pass an empty query to take everything.
    """

    name = "rss"

    def __init__(self, feeds: list[str] | None = None, fetch_full_text: bool = True):
        self.feeds = feeds or []
        self.fetch_full_text = fetch_full_text

    def is_available(self) -> bool:
        return bool(self.feeds)

    def search(self, query: str, max_results: int = 10) -> list[FetchedDoc]:
        if not self.feeds:
            return []
        q = query.lower().strip()
        docs: list[FetchedDoc] = []

        for feed_url in self.feeds:
            try:
                parsed = feedparser.parse(feed_url)
            except Exception:
                continue

            for entry in parsed.entries:
                title = entry.get("title", "")
                summary = entry.get("summary", "") or entry.get("description", "")
                if q and q not in title.lower() and q not in summary.lower():
                    continue

                link = entry.get("link", "")
                content = summary
                if self.fetch_full_text and link:
                    extracted = extract_url(link)
                    if extracted:
                        content = extracted

                docs.append(
                    FetchedDoc(
                        title=title,
                        url=link,
                        content=f"# {title}\n\n{content}",
                        source_type=self.name,
                        metadata={
                            "feed": feed_url,
                            "published": entry.get("published"),
                            "author": entry.get("author"),
                        },
                    )
                )
                if len(docs) >= max_results:
                    return docs
        return docs
