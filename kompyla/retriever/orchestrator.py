"""Coordinates a multi-source retrieval pass with dedup and relevance filtering."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..filter.dedup import Deduplicator
from ..filter.relevance import RelevanceScorer
from ..schema.models import DomainSchema
from ..storage.index import MetaIndex
from ..storage.layout import KBLayout
from .base import FetchedDoc, SourceConnector


def _slug(text: str, limit: int = 60) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return s[:limit] or "untitled"


def _content_hash(content: str) -> str:
    """SHA-256 of normalized content (whitespace collapsed)."""
    normalized = re.sub(r"\s+", " ", content).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _save_doc(doc: FetchedDoc, layout: KBLayout) -> Path:
    """Write a FetchedDoc to raw/ as markdown with frontmatter."""
    out_dir = layout.raw / doc.source_type
    out_dir.mkdir(parents=True, exist_ok=True)

    fm = {
        "title": doc.title,
        "url": doc.url,
        "source_type": doc.source_type,
        "fetched_at": doc.fetched_at,
        "relevance_score": round(doc.relevance_score, 3) if doc.relevance_score is not None else None,
        **{k: v for k, v in doc.metadata.items() if v is not None},
    }
    frontmatter = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False).strip()
    body = doc.content if doc.content.startswith("#") else f"# {doc.title}\n\n{doc.content}"
    text = f"---\n{frontmatter}\n---\n\n{body}\n"

    name = f"{_slug(doc.title)}_{_content_hash(doc.content)[:8]}.md"
    path = out_dir / name
    path.write_text(text, encoding="utf-8")
    return path


class RetrievalOrchestrator:
    """Run queries across all enabled connectors, dedup, score, save."""

    def __init__(
        self,
        connectors: list[SourceConnector],
        layout: KBLayout,
        index: MetaIndex,
        relevance_scorer: RelevanceScorer | None = None,
        deduplicator: Deduplicator | None = None,
        min_relevance: float = 0.5,
        max_per_source: int = 5,
    ):
        self.connectors = [c for c in connectors if c.is_available()]
        self.layout = layout
        self.index = index
        self.relevance_scorer = relevance_scorer
        self.deduplicator = deduplicator or Deduplicator()
        self.min_relevance = min_relevance
        self.max_per_source = max_per_source

    def enabled_sources(self) -> list[str]:
        return [c.name for c in self.connectors]

    def search(self, queries: list[str], schema: DomainSchema | None = None) -> dict:
        """Run all queries against all enabled connectors and persist passing docs.

        Returns a summary dict: counts of fetched / deduped / accepted / saved.
        """
        if schema is None and self.relevance_scorer is not None:
            raise ValueError("RelevanceScorer requires a DomainSchema")

        # Seed dedup with already-known content hashes
        for row in self.index.all_raw_docs():
            if row["content_hash"]:
                self.deduplicator.register_hash(row["content_hash"])

        fetched: list[FetchedDoc] = []
        for q in queries:
            for connector in self.connectors:
                try:
                    fetched.extend(connector.search(q, max_results=self.max_per_source))
                except Exception:
                    continue

        # Dedup
        unique: list[FetchedDoc] = []
        for doc in fetched:
            h = _content_hash(doc.content)
            if self.deduplicator.is_duplicate(doc.content, exact_hash=h):
                continue
            self.deduplicator.add(doc.content, exact_hash=h)
            doc.metadata["_content_hash"] = h
            unique.append(doc)

        # Relevance filtering (optional)
        accepted: list[FetchedDoc] = []
        if self.relevance_scorer is not None and schema is not None:
            for doc in unique:
                doc.relevance_score = self.relevance_scorer.score(doc, schema)
                if doc.relevance_score >= self.min_relevance:
                    accepted.append(doc)
        else:
            accepted = unique

        # Persist
        saved_paths: list[Path] = []
        for doc in accepted:
            path = _save_doc(doc, self.layout)
            self.index.upsert_raw_doc(
                path,
                url=doc.url,
                source_type=doc.source_type,
                relevance_score=doc.relevance_score,
                content_hash=doc.metadata.get("_content_hash"),
                title=doc.title,
            )
            saved_paths.append(path)

        return {
            "queries": len(queries),
            "sources": len(self.connectors),
            "fetched": len(fetched),
            "after_dedup": len(unique),
            "accepted": len(accepted),
            "saved": len(saved_paths),
            "saved_paths": saved_paths,
        }
