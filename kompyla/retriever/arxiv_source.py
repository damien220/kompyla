"""arXiv connector — searches arXiv and returns paper abstracts as markdown."""

from __future__ import annotations

import arxiv

from .base import FetchedDoc, SourceConnector


def _result_to_markdown(r: arxiv.Result) -> str:
    authors = ", ".join(a.name for a in r.authors)
    categories = ", ".join(r.categories)
    return (
        f"# {r.title}\n\n"
        f"**Authors:** {authors}\n\n"
        f"**Published:** {r.published.date()}\n\n"
        f"**Categories:** {categories}\n\n"
        f"**arXiv:** {r.entry_id}\n\n"
        f"**PDF:** {r.pdf_url}\n\n"
        f"## Abstract\n\n{r.summary.strip()}\n"
    )


class ArxivConnector(SourceConnector):
    """Search arXiv for papers matching a query. No API key required."""

    name = "arxiv"

    def __init__(self, sort_by: arxiv.SortCriterion = arxiv.SortCriterion.Relevance):
        self.sort_by = sort_by

    def search(self, query: str, max_results: int = 10) -> list[FetchedDoc]:
        client = arxiv.Client(page_size=max_results, delay_seconds=3.0, num_retries=3)
        search = arxiv.Search(query=query, max_results=max_results, sort_by=self.sort_by)
        try:
            results = list(client.results(search))
        except Exception:
            return []

        return [
            FetchedDoc(
                title=r.title,
                url=r.entry_id,
                content=_result_to_markdown(r),
                source_type=self.name,
                metadata={
                    "authors": [a.name for a in r.authors],
                    "published": r.published.isoformat(),
                    "pdf_url": r.pdf_url,
                    "categories": list(r.categories),
                },
            )
            for r in results
        ]
