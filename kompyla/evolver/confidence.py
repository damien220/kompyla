"""Confidence-driven re-research helpers."""

from __future__ import annotations

import sqlite3

from ..storage.index import MetaIndex


def low_confidence_pages(index: MetaIndex, threshold: float = 0.6) -> list[sqlite3.Row]:
    return [p for p in index.all_pages() if (p["confidence"] or 0.0) < threshold]


def re_research_queries(pages: list[sqlite3.Row]) -> list[str]:
    """Generate search queries for re-researching the given pages.

    The page title is a perfectly good query for most cases.
    """
    return [p["title"] for p in pages]
